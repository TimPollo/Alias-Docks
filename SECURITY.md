# Security notes

AliasDock is a self-hosted, single-administrator, inbound-only mail application. It has not undergone an independent security audit.

- Keep `.env` private and use randomly generated credentials. Never publish secrets, inbox contents, or database backups.
- Only publish the web UI through HTTPS. Local HTTP must bind to 127.0.0.1.
- Incoming SMTP **does not offer STARTTLS by default**. Operators may enable STARTTLS by supplying a certificate and key through SMTP_TLS_CERT and SMTP_TLS_KEY. Without this, transport may be unencrypted; even with opportunistic TLS, end-to-end encryption is not assured.
- The SMTP process does not send or relay messages. Unknown and disabled recipients are rejected.
- Received MIME content is reduced to plain text; HTML scripts and attachments are not rendered.
- For administration from untrusted networks, protect your server using firewall rules, OS updates, and, where appropriate, additional network access controls.
- Protect persistent Docker volumes; stored messages are not encrypted at rest by the application.
- Keep SMTP size, storage, alias creation and login throttles enabled.
- This tool does not perform registration automation or evade third-party platform security controls.

For security reports, use GitHub's private vulnerability reporting feature if enabled on your repository, rather than publishing proof-of-concept exploit information in a public issue.

- In production, client IP forwarding is trusted only because the web backend is not exposed to the public internet and Caddy overwrites `X-Real-IP`. Do not make port 8000 public with `TRUST_PROXY=true`.
