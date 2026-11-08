"""AliasDock FastAPI dashboard; authentication required for every mailbox action."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import ipaddress
import secrets
import ssl
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import Settings, from_env
from .db import Database
from .mailer import LOCAL_RE, RESERVED, InboundHandler

ROOT = Path(__file__).resolve().parent.parent
SESSION_COOKIE = "aliasdock_session"
SESSION_SECONDS = 12 * 3600


class LoginPayload(BaseModel):
    username: str = Field(max_length=100)
    password: str = Field(max_length=256)


class AliasPayload(BaseModel):
    local_part: str | None = Field(default=None, max_length=30)


class AliasStatePayload(BaseModel):
    active: bool


class LoginGuard:
    """Simple login throttle for the single-admin deployment."""
    def __init__(self):
        self.failed: dict[str, deque[int]] = defaultdict(deque)

    def allowed(self, key: str) -> bool:
        now = int(time.time())
        if len(self.failed) > 2500:
            self.failed.clear()
        attempts = self.failed[key]
        while attempts and attempts[0] < now - 900:
            attempts.popleft()
        return len(attempts) < 6

    def add_failure(self, key: str) -> None:
        self.failed[key].append(int(time.time()))

    def success(self, key: str) -> None:
        self.failed.pop(key, None)


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        cfg = settings if settings is not None else from_env()
        cfg.validate()
        db = Database(cfg.database_path)
        db.init()
        db.cleanup(cfg.retention_days, cfg.max_stored_messages)
        app.state.cfg = cfg
        app.state.db = db
        app.state.guard = LoginGuard()
        async def cleanup_loop():
            while True:
                await asyncio.sleep(3600)
                await asyncio.to_thread(db.cleanup, cfg.retention_days, cfg.max_stored_messages)

        janitor = asyncio.create_task(cleanup_loop())
        controller = None
        try:
            if cfg.enable_smtp:
                # Established SMTP implementation; allowlisted inbound recipients only.
                from aiosmtpd.controller import Controller
                tls_context = None
                if cfg.smtp_tls_cert:
                    tls_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
                    tls_context.minimum_version = ssl.TLSVersion.TLSv1_2
                    tls_context.load_cert_chain(cfg.smtp_tls_cert, cfg.smtp_tls_key)
                controller = Controller(InboundHandler(db, cfg), hostname=cfg.smtp_host,
                                        port=cfg.smtp_port, decode_data=False,
                                        enable_SMTPUTF8=False, tls_context=tls_context,
                                        data_size_limit=cfg.max_message_bytes,
                                        ready_timeout=15.0)
                controller.start()
            yield
        finally:
            janitor.cancel()
            try:
                await janitor
            except asyncio.CancelledError:
                pass
            if controller is not None:
                controller.stop()

    app = FastAPI(title="AliasDock", version="1.0.0", docs_url=None,
                  redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; script-src 'self'; style-src 'self'; "
            "connect-src 'self'; img-src 'self' data:; base-uri 'none'; "
            "object-src 'none'; frame-ancestors 'none'; form-action 'self'"
        )
        if hasattr(request.app.state, "cfg") and request.app.state.cfg.cookie_secure:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Cache-Control"] = "no-store"
        return response

    def cfg(request: Request) -> Settings:
        return request.app.state.cfg

    def db(request: Request) -> Database:
        return request.app.state.db

    def token_hash(raw: str, secret: str) -> str:
        return hmac.new(secret.encode(), raw.encode(), hashlib.sha256).hexdigest()

    def require_auth(request: Request) -> dict:
        raw = request.cookies.get(SESSION_COOKIE, "")
        if not (16 <= len(raw) <= 150):
            raise HTTPException(status_code=401, detail="Nicht angemeldet")
        session = db(request).get_session(token_hash(raw, cfg(request).app_secret))
        if not session:
            raise HTTPException(status_code=401, detail="Sitzung abgelaufen")
        return session

    def require_csrf(request: Request, session: dict = Depends(require_auth)) -> None:
        header = request.headers.get("X-CSRF-Token", "")
        if not hmac.compare_digest(header, session["csrf"]):
            raise HTTPException(status_code=403, detail="Ungültiger Sicherheitstoken")

    @app.get("/", include_in_schema=False)
    def homepage():
        return FileResponse(ROOT / "static" / "index.html", headers={"Cache-Control": "no-store"})

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    @app.get("/api/config")
    def configuration(request: Request):
        c = cfg(request)
        return {"alias_domain": c.alias_domain, "max_aliases": c.max_aliases,
                "retention_days": c.retention_days, "max_message_bytes": c.max_message_bytes}

    @app.post("/api/login")
    def login(data: LoginPayload, request: Request, response: Response):
        c = cfg(request)
        key = (request.client.host if request.client else "unknown")
        if c.trust_proxy:
            # Caddy explicitly replaces this header. Never trust it with direct public HTTP.
            forwarded_ip = request.headers.get("X-Real-IP", "")
            try:
                key = str(ipaddress.ip_address(forwarded_ip))
            except ValueError:
                pass
        guard: LoginGuard = request.app.state.guard
        if not guard.allowed(key):
            raise HTTPException(status_code=429, detail="Zu viele Anmeldeversuche. Bitte später erneut versuchen.")
        user_ok = hmac.compare_digest(data.username.encode(), c.admin_username.encode())
        password_ok = hmac.compare_digest(data.password.encode(), c.admin_password.encode())
        if not (user_ok and password_ok):
            guard.add_failure(key)
            raise HTTPException(status_code=401, detail="Benutzername oder Passwort falsch")
        guard.success(key)
        raw = secrets.token_urlsafe(40)
        csrf = secrets.token_urlsafe(32)
        db(request).create_session(token_hash(raw, c.app_secret), csrf, int(time.time()) + SESSION_SECONDS)
        response.set_cookie(SESSION_COOKIE, raw, max_age=SESSION_SECONDS,
                            secure=c.cookie_secure, httponly=True, samesite="strict", path="/")
        return {"ok": True}

    @app.get("/api/me")
    def me(request: Request, session: dict = Depends(require_auth)):
        return {"username": cfg(request).admin_username, "csrf": session["csrf"]}

    @app.post("/api/logout", dependencies=[Depends(require_csrf)])
    def logout(request: Request, response: Response):
        raw = request.cookies.get(SESSION_COOKIE, "")
        db(request).delete_session(token_hash(raw, cfg(request).app_secret))
        response.delete_cookie(SESSION_COOKIE, path="/")
        return {"ok": True}

    @app.get("/api/aliases", dependencies=[Depends(require_auth)])
    def aliases(request: Request):
        return {"aliases": db(request).list_aliases(cfg(request).alias_domain)}

    @app.post("/api/aliases", status_code=201, dependencies=[Depends(require_csrf)])
    def create_alias(request: Request, data: AliasPayload):
        c = cfg(request)
        requested = (data.local_part or "").lower().strip()
        if requested and (not LOCAL_RE.fullmatch(requested) or requested in RESERVED
                          or requested.endswith(".") or ".." in requested):
            raise HTTPException(status_code=422, detail="3–30 Zeichen: a–z, 0–9, Punkt, Minus oder Unterstrich")
        for _ in range(5 if not requested else 1):
            local = requested or ("privat-" + secrets.token_hex(5))
            ident, result = db(request).create_alias(local, c.max_aliases)
            if result == "ok":
                return {"id": ident, "address": f"{local}@{c.alias_domain}"}
            if result == "limit":
                raise HTTPException(status_code=409, detail="Adresslimit erreicht")
            if result == "rate":
                raise HTTPException(status_code=429, detail="Maximal 10 neue Adressen pro Stunde")
            if requested:
                raise HTTPException(status_code=409, detail="Diese Adresse existiert bereits")
        raise HTTPException(status_code=503, detail="Konnte keine freie Adresse erstellen")

    @app.patch("/api/aliases/{alias_id}", dependencies=[Depends(require_csrf)])
    def toggle_alias(alias_id: int, data: AliasStatePayload, request: Request):
        if alias_id < 1 or not db(request).set_alias_active(alias_id, data.active):
            raise HTTPException(status_code=404, detail="Adresse nicht gefunden")
        return {"ok": True}

    @app.delete("/api/aliases/{alias_id}", dependencies=[Depends(require_csrf)])
    def remove_alias(alias_id: int, request: Request):
        if alias_id < 1 or not db(request).delete_alias(alias_id):
            raise HTTPException(status_code=404, detail="Adresse nicht gefunden")
        return {"ok": True}

    @app.get("/api/messages", dependencies=[Depends(require_auth)])
    def messages(request: Request, alias_id: int | None = Query(default=None, ge=1),
                 q: str = Query(default="", max_length=120),
                 unread_only: bool = False, before_id: int | None = Query(default=None, ge=1)):
        rows = db(request).list_messages(alias_id, q.strip(), unread_only, before_id, limit=51)
        return {"messages": rows[:50], "has_more": len(rows) > 50}

    @app.get("/api/messages/{message_id}", dependencies=[Depends(require_auth)])
    def message(request: Request, message_id: int):
        found = db(request).get_message(message_id)
        if not found:
            raise HTTPException(status_code=404, detail="Nachricht nicht gefunden")
        return found

    @app.post("/api/messages/{message_id}/read", dependencies=[Depends(require_csrf)])
    def mark_read(request: Request, message_id: int):
        if not db(request).set_read(message_id, True):
            raise HTTPException(status_code=404, detail="Nachricht nicht gefunden")
        return {"ok": True}

    @app.delete("/api/messages/{message_id}", dependencies=[Depends(require_csrf)])
    def delete_message(request: Request, message_id: int):
        if not db(request).delete_message(message_id):
            raise HTTPException(status_code=404, detail="Nachricht nicht gefunden")
        return {"ok": True}

    @app.get("/api/stats", dependencies=[Depends(require_auth)])
    def stats(request: Request):
        return db(request).stats()

    return app


app = create_app()
