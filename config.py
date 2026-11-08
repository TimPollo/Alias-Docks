"""Configuration with strict startup validation."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

DOMAIN_RE = re.compile(r"^(?=.{4,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")


@dataclass(frozen=True)
class Settings:
    alias_domain: str
    admin_username: str
    admin_password: str
    app_secret: str
    database_path: str
    cookie_secure: bool = True
    smtp_host: str = "0.0.0.0"
    smtp_port: int = 2525
    max_aliases: int = 25
    max_message_bytes: int = 512 * 1024
    retention_days: int = 14
    max_stored_messages: int = 2000
    enable_smtp: bool = True
    smtp_tls_cert: str = ""
    smtp_tls_key: str = ""
    trust_proxy: bool = False

    def validate(self) -> None:
        if not DOMAIN_RE.fullmatch(self.alias_domain):
            raise ValueError("ALIAS_DOMAIN must be a public-looking DNS domain (for example example.org)")
        if not self.admin_username or len(self.admin_username) > 100:
            raise ValueError("Invalid ADMIN_USERNAME")
        if len(self.admin_password) < 16:
            raise ValueError("ADMIN_PASSWORD must contain at least 16 characters")
        if len(self.app_secret) < 32:
            raise ValueError("APP_SECRET must contain at least 32 characters")
        if bool(self.smtp_tls_cert) != bool(self.smtp_tls_key):
            raise ValueError("SMTP_TLS_CERT and SMTP_TLS_KEY must be set together")
        if not (1 <= self.smtp_port <= 65535):
            raise ValueError("SMTP_PORT is out of range")
        if not (1 <= self.max_aliases <= 250):
            raise ValueError("MAX_ALIASES must be between 1 and 250")
        if not (1024 <= self.max_message_bytes <= 5 * 1024 * 1024):
            raise ValueError("MAX_MESSAGE_BYTES is outside the supported range")
        if not (1 <= self.retention_days <= 365):
            raise ValueError("RETENTION_DAYS is outside the supported range")
        if not (10 <= self.max_stored_messages <= 10000):
            raise ValueError("MAX_STORED_MESSAGES is outside the supported range")


def from_env() -> Settings:
    def as_int(key: str, default: int) -> int:
        try:
            return int(os.getenv(key, str(default)))
        except ValueError as exc:
            raise ValueError(f"{key} must be an integer") from exc

    settings = Settings(
        alias_domain=os.getenv("ALIAS_DOMAIN", "").lower().strip(),
        admin_username=os.getenv("ADMIN_USERNAME", "admin"),
        admin_password=os.getenv("ADMIN_PASSWORD", ""),
        app_secret=os.getenv("APP_SECRET", ""),
        database_path=os.getenv("DATABASE_PATH", "/data/aliasdock.sqlite3"),
        cookie_secure=os.getenv("COOKIE_SECURE", "true").lower() == "true",
        smtp_host=os.getenv("SMTP_HOST", "0.0.0.0"),
        smtp_port=as_int("SMTP_PORT", 2525),
        max_aliases=as_int("MAX_ALIASES", 25),
        max_message_bytes=as_int("MAX_MESSAGE_BYTES", 512 * 1024),
        retention_days=as_int("RETENTION_DAYS", 14),
        max_stored_messages=as_int("MAX_STORED_MESSAGES", 2000),
        enable_smtp=os.getenv("ENABLE_SMTP", "true").lower() == "true",
        smtp_tls_cert=os.getenv("SMTP_TLS_CERT", ""),
        smtp_tls_key=os.getenv("SMTP_TLS_KEY", ""),
        trust_proxy=os.getenv("TRUST_PROXY", "false").lower() == "true",
    )
    settings.validate()
    Path(settings.database_path).parent.mkdir(parents=True, exist_ok=True)
    return settings
