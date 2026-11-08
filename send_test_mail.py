#!/usr/bin/env python3
"""Send a local test message to a previously created alias."""
import argparse
import smtplib
from email.message import EmailMessage

p = argparse.ArgumentParser(description="Send a demo message into your local AliasDock SMTP server")
p.add_argument("to", help="Existing alias, e.g. privat-a1b2c3d4e5@example.org")
p.add_argument("--host", default="127.0.0.1")
p.add_argument("--port", type=int, default=2525)
args = p.parse_args()
msg = EmailMessage()
msg["From"] = "demo@local.test"
msg["To"] = args.to
msg["Subject"] = "AliasDock funktioniert!"
msg.set_content("Hallo! Diese Testnachricht wurde lokal per SMTP verschickt.\n")
with smtplib.SMTP(args.host, args.port, timeout=15) as smtp:
    smtp.send_message(msg)
print("Test mail accepted for:", args.to)
