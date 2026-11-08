#!/usr/bin/env python3
"""Generate a secure .env file. Does not provision a server or register a domain."""
import argparse
import re
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOMAIN_RE = re.compile(r"^(?=.{4,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")

p = argparse.ArgumentParser(description="AliasDock: initial configuration")
p.add_argument("--local", action="store_true", help="Local demo with example.org")
p.add_argument("--domain", help="Mail domain, e.g. example.org")
p.add_argument("--host", help="Dashboard domain, e.g. inbox.example.org")
args = p.parse_args()

domain = ("example.org" if args.local else (args.domain or "")).lower().strip()
host = ("localhost" if args.local else (args.host or "")).lower().strip()
if not DOMAIN_RE.fullmatch(domain):
    p.error("Provide --local or a valid --domain example.org")
if not args.local and not DOMAIN_RE.fullmatch(host):
    p.error("Provide --host inbox.example.org")
path = ROOT / ".env"
if path.exists():
    p.error(".env already exists. It was not overwritten; keep your existing secrets.")
password = secrets.token_urlsafe(24)
secret = secrets.token_urlsafe(48)
contents = f"""# Private credentials. DO NOT commit this file to version control.
ALIAS_DOMAIN={domain}
PUBLIC_HOST={host}
ADMIN_USERNAME=admin
ADMIN_PASSWORD={password}
APP_SECRET={secret}
DATABASE_PATH=/data/aliasdock.sqlite3
MAX_ALIASES=25
MAX_MESSAGE_BYTES=524288
RETENTION_DAYS=14
MAX_STORED_MESSAGES=2000
SMTP_PORT=2525
ENABLE_SMTP=true
"""
path.write_text(contents, encoding="utf-8")
path.chmod(0o600)
print("\nSetup complete. Keep these credentials secure!\n")
print("Admin username: admin")
print(f"Admin password: {password}")
print(f"Alias domain:   {domain}")
print(f"Dashboard host: {host}")
print("\nCredentials are also saved locally in .env (excluded from Git).")
