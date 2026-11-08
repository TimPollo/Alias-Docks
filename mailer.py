"""Inbound SMTP handler. No SMTP relay, no outgoing mail, allowlisted recipients only."""
from __future__ import annotations

import re
from email import policy
from email.header import decode_header, make_header
from email.parser import BytesParser
from html.parser import HTMLParser

from .config import Settings
from .db import Database

LOCAL_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,29}$")
RESERVED = {"postmaster", "abuse", "root", "admin", "mailer-daemon", "security", "support", "hostmaster"}


def local_from_address(address: str, domain: str) -> str | None:
    """Strict ASCII mailbox matching. Only our exact domain is accepted."""
    if not isinstance(address, str) or address.count("@") != 1:
        return None
    local, received_domain = address.rsplit("@", 1)
    local = local.lower()
    if (received_domain.lower() != domain or not LOCAL_RE.fullmatch(local)
            or local.endswith(".") or ".." in local):
        return None
    return local


def decode_text_header(value: str | None, max_len: int = 250) -> str:
    if not value:
        return ""
    try:
        text = str(make_header(decode_header(str(value))))
    except (UnicodeError, LookupError, ValueError):
        text = str(value)
    return " ".join(text.split())[:max_len]


class HTMLToText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "svg", "iframe", "object"):
            self.skip += 1
        elif tag in ("p", "br", "li", "div", "tr"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "svg", "iframe", "object") and self.skip:
            self.skip -= 1
        elif tag in ("p", "div", "li", "tr"):
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)

    def output(self) -> str:
        return "".join(self.parts)


def extract_message(raw: bytes) -> tuple[str, str, str, str]:
    msg = BytesParser(policy=policy.default).parsebytes(raw)
    sender = decode_text_header(msg.get("From"), 250) or "Unbekannter Absender"
    subject = decode_text_header(msg.get("Subject"), 250) or "(Ohne Betreff)"
    message_id = decode_text_header(msg.get("Message-ID"), 250)
    body = ""
    html_body = ""
    parts = msg.walk() if msg.is_multipart() else [msg]
    for part in parts:
        if part.is_multipart() or part.get_content_disposition() == "attachment":
            continue
        content_type = part.get_content_type()
        if content_type not in ("text/plain", "text/html"):
            continue
        try:
            text = part.get_content()
            if not isinstance(text, str):
                continue
        except (UnicodeError, LookupError, ValueError, TypeError):
            continue
        if content_type == "text/plain" and len(body) < 20000:
            body += text + "\n"
        elif content_type == "text/html" and not html_body:
            html_body = text
    if not body.strip() and html_body:
        parser = HTMLToText()
        parser.feed(html_body[:150000])
        body = parser.output()
    body = body.replace("\x00", "").strip()[:20000] or "(Keine Textansicht verfügbar; Anhänge werden nicht gespeichert.)"
    return sender, subject, body, message_id


class InboundHandler:
    def __init__(self, db: Database, settings: Settings):
        self.db = db
        self.settings = settings

    async def handle_MAIL(self, server, session, envelope, address, mail_options):
        # Never relay or send messages. Sender <> is a legitimate null reverse path.
        envelope.mail_from = address
        envelope.mail_options.extend(mail_options)
        return "250 2.1.0 Sender OK"

    async def handle_RCPT(self, server, session, envelope, address, rcpt_options):
        if len(envelope.rcpt_tos) >= 10:
            return "452 4.5.3 Too many recipients"
        local = local_from_address(address, self.settings.alias_domain)
        if not local or self.db.recipient_alias_id(local) is None:
            return "550 5.1.1 Unknown or disabled recipient"
        envelope.rcpt_tos.append(address)
        return "250 2.1.5 Recipient OK"

    async def handle_DATA(self, server, session, envelope):
        raw = envelope.content
        if not isinstance(raw, bytes) or len(raw) > self.settings.max_message_bytes:
            return "552 5.3.4 Message too large"
        ids = []
        for addr in envelope.rcpt_tos:
            local = local_from_address(addr, self.settings.alias_domain)
            if local:
                alias_id = self.db.recipient_alias_id(local)
                if alias_id is not None:
                    ids.append(alias_id)
        if not ids:
            return "550 5.1.1 No valid recipients"
        try:
            sender, subject, body, message_id = extract_message(raw)
            saved = self.db.save_messages(ids, sender, subject, body, message_id,
                retention_days=self.settings.retention_days,
                max_stored_messages=self.settings.max_stored_messages)
        except Exception:
            # Don't acknowledge mail which was not safely stored; SMTP client can retry.
            return "451 4.3.0 Temporary storage failure"
        return "250 2.0.0 Accepted" if saved else "550 5.1.1 Recipients no longer available"
