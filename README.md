# AliasDock

**Dein privater E-Mail-Alias-Manager – mit echtem Posteingang, einfacher Weboberfläche und Docker-Installation.**

![Lizenz](https://img.shields.io/badge/Lizenz-MIT-167e6e) ![Python](https://img.shields.io/badge/Python-3.12-blue) ![Speicher](https://img.shields.io/badge/Speicher-SQLite-245e72)

AliasDock ist ein **Open-Source-Projekt für eigene E-Mail-Adressen**, zum Beispiel für Datenschutz, Newsletter, Softwaretests und die getrennte Nutzung persönlicher Online-Konten. Die Anwendung ist **kein Dienst zum Umgehen von Registrierungs-, Spam- oder Bot-Schutzmaßnahmen**. Eine Akzeptanz durch Drittplattformen wird nicht versprochen.

## Das bekommst du

- Eine responsive Web-App (deutsch, auch auf dem Smartphone)
- Individuelle oder zufällig erzeugte E-Mail-Adressen **unter deiner eigenen Domain**
- Echten E-Mail-Empfang per SMTP, einschließlich Bestätigungscodes
- Einen Posteingang mit Suche, Lesestatus, Detailansicht und Filter nach Adresse
- Aktivierung, Deaktivierung und Löschung von Alias-Adressen
- Keine Weiterleitung an private Drittanbieter-Postfächer
- Passwortgeschützten Administratorzugang mit zeitlich begrenzten, widerrufbaren Sitzungen
- Automatische Löschung alter Nachrichten (Standard: 14 Tage)
- Begrenzungen für Aliasse, Speicher und Nachrichtengröße
- Docker-Setups für lokale Tests und öffentlich erreichbaren Betrieb
- HTTPS für das Web-Dashboard über Caddy

**Wichtig:** AliasDock empfängt E-Mails, versendet aber keine. Es ist **kein offenes SMTP-Relay**. Anhänge werden nicht gespeichert; HTML wird ausschließlich als ungefährlicher Text angezeigt. Externe Absenderbilder, Trackingpixel und JavaScript werden nicht geladen.

## Schnellstart: lokal testen (ohne Domain)

Du benötigst **Docker Desktop** (Windows/macOS) oder Docker Engine mit Compose (Linux), außerdem Python 3 für die einmalige Einrichtung.

```bash
# Projektordner öffnen
cd aliasdock

# Erstellt .env und zeigt dein Admin-Passwort an
python3 scripts/setup.py --local

# Container bauen und starten
docker compose -f compose.local.yaml up -d --build
```

Öffne **http://127.0.0.1:8000**. Melde dich mit `admin` und dem von `setup.py` angezeigten Passwort an. Erstelle über **Neue Adresse** einen Alias.

Zum Testen des E-Mail-Empfangs benötigst du noch keine öffentliche Domain:

```bash
python3 scripts/send_test_mail.py deine-adresse@example.org
```

Der SMTP-Testserver ist im lokalen Setup ausschließlich unter `127.0.0.1:2525` erreichbar. Nach **Aktualisieren** sollte die Nachricht im Posteingang erscheinen. `example.org` ist hier **nur eine Test-Domain** – öffentlich erreichbare E-Mails können so nicht empfangen werden.

Lokale Container stoppen:

```bash
docker compose -f compose.local.yaml down
```

`down` **ohne** `-v` erhält die gespeicherten Nachrichten. `down -v` würde die lokalen Datenvolumes löschen.

## Echt aus dem Internet E-Mails empfangen

Dafür brauchst du eine **eigene registrierte Domain**, einen **öffentlich erreichbaren Server** und **eingehenden TCP-Port 25**. Viele kostenlosen Cloud-Angebote und private Internetanschlüsse blockieren Port 25 – das musst du vorab beim Hosting-Anbieter prüfen. Ein kostenloser und garantiert dauerhaft funktionierender öffentlicher Betrieb wird nicht angeboten oder versprochen.

Beispiel: E-Mail-Adressen `...@meinedomain.de`; Dashboard `inbox.meinedomain.de`; Server-IP `203.0.113.10` (**nur Dokumentationsbeispiel**, keine nutzbare IP).

### 1. DNS beim Domainanbieter einrichten

| Typ | Name/Host | Wert | Zweck |
| --- | --- | --- | --- |
| A | `mail.meinedomain.de` | `DEINE_SERVER_IP` | Mailserver erreichbar |
| A | `inbox.meinedomain.de` | `DEINE_SERVER_IP` | Dashboard erreichbar |
| MX | `meinedomain.de` | `10 mail.meinedomain.de` | Eingangspost an Server |

- DNS-Benennungen unterscheiden sich je nach Anbieter: bei manchen genügt `mail` bzw. `inbox` als Host.
- Die MX-Domain muss exakt mit `ALIAS_DOMAIN` übereinstimmen.
- IPv6 (AAAA) nur setzen, wenn der Server über IPv6 tatsächlich erreichbar ist.
- SPF, DKIM und DMARC werden insbesondere für **ausgehende** Mail relevant; AliasDock sendet keine E-Mails.

### 2. Auf dem Server konfigurieren und starten

```bash
python3 scripts/setup.py --domain meinedomain.de --host inbox.meinedomain.de

docker compose -f compose.prod.yaml up -d --build
```

Auf dem Server müssen eingehende TCP-Ports **25, 80 und 443** erreichbar sein (für HTTPS zusätzlich UDP 443 optional). Caddy stellt das Dashboard über HTTPS bereit, sofern der DNS-Eintrag korrekt ist und eine TLS-Zertifikatsausstellung möglich ist.

Öffne dann **https://inbox.meinedomain.de** und melde dich an.

### 3. Empfang verifizieren

- Per Terminal: `docker compose -f compose.prod.yaml logs --tail=50 app`
- Prüfe, ob dein MX-Record erreichbar ist und Port 25 von außen offen ist.
- Sende von einer normalen E-Mail-Adresse eine Nachricht an einen **in der App angelegten, aktiven Alias**.
- Klicke im Dashboard auf **Aktualisieren**. Unbekannte bzw. deaktivierte Empfänger werden am SMTP-Eingang abgewiesen.

### Achtung: Verschlüsselung der E-Mail-Übertragung

**Das enthaltene Empfangs-SMTP bietet ohne zusätzliche Konfiguration kein STARTTLS.** Das HTTPS-Zertifikat von Caddy schützt **nur das Web-Dashboard**, nicht automatisch eingehende SMTP-Verbindungen. Manche sendenden Mailserver können deshalb die Nachricht auf dem Transportweg unverschlüsselt zustellen oder sie aufgrund eigener Sicherheitsrichtlinien ablehnen. Für sensible Postfächer oder einen streng gehärteten Produktionsbetrieb sollte man zusätzlich einen etablierten SMTP-Eingangsserver mit STARTTLS und geeigneten Zertifikaten davorschalten oder die optionale STARTTLS-Konfiguration verwenden. **Optionaler STARTTLS-Betrieb:** Wenn du ein gültiges Zertifikat für `mail.meinedomain.de` samt privatem Schlüssel hast, kannst du beide Dateien lesbar in den App-Container einbinden (z. B. `./certs:/certs:ro` unter `app.volumes` in `compose.prod.yaml`) und in `.env` `SMTP_TLS_CERT=/certs/fullchain.pem` sowie `SMTP_TLS_KEY=/certs/privkey.pem` setzen. Ein Neustart ist erforderlich. STARTTLS ist opportunistisch; es erzwingt keine verschlüsselte Verbindung für alle sendenden Mailserver. Zertifikate müssen rechtzeitig erneuert werden. Verwende für hochvertrauliche Zugangsdaten vorzugsweise einen professionell betriebenen Mailanbieter.

## Konfiguration

Die Datei `.env` wird von `scripts/setup.py` erzeugt. **Nie öffentlich teilen, niemals auf GitHub hochladen.**

| Variable | Bedeutung | Standard |
| --- | --- | --- |
| `ALIAS_DOMAIN` | Domain deiner E-Mail-Adressen | erforderlich |
| `PUBLIC_HOST` | Domain des HTTPS-Dashboards | erforderlich (Produktion) |
| `ADMIN_USERNAME` | Admin-Benutzername | `admin` |
| `ADMIN_PASSWORD` | Admin-Passwort (mind. 16 Zeichen) | zufällig erzeugt |
| `APP_SECRET` | Geheimnis für Session-Token-Hashes | zufällig erzeugt |
| `MAX_ALIASES` | Maximale Zahl gespeicherter Aliasse | `25` |
| `MAX_MESSAGE_BYTES` | Maximale Größe je Mail | `524288` (512 KiB) |
| `RETENTION_DAYS` | Automatische Aufbewahrung | `14` |
| `MAX_STORED_MESSAGES` | Maximale Gesamtzahl Nachrichten | `2000` |
| `DATABASE_PATH` | SQLite-Datei im Container | `/data/aliasdock.sqlite3` |
| `ENABLE_SMTP` | Empfangsserver starten | `true` |
| `SMTP_TLS_CERT` / `SMTP_TLS_KEY` | Optionale TLS-Zertifikatsdateien im Container | leer |

Zusätzlich gibt es eine Begrenzung von **10 neuen Adressen pro Stunde**. Sie ist bewusst als Missbrauchsschutz eingebaut.

### Backup

Ein konsistentes Datenbankbackup lässt sich über Python erstellen:

```bash
# Backup-Script wird bewusst nicht im Produktionsimage eingebaut.
# Alternative: Datenbank via SQLite-Online-Backup aus dem laufenden Container:
docker compose -f compose.prod.yaml exec -T app python -c "import sqlite3; a=sqlite3.connect('/data/aliasdock.sqlite3'); b=sqlite3.connect('/data/aliasdock-backup.sqlite3'); a.backup(b); b.close(); a.close()"
```

**Wichtig:** Eine Backupdatei im selben Docker-Volume ist noch kein echtes externes Backup. Kopiere sie anschließend gesichert auf ein anderes Speichermedium. Backups enthalten möglicherweise vertrauliche E-Mails und müssen geschützt werden.

### Updates

```bash
docker compose -f compose.prod.yaml up -d --build
```

Vor Updates ist ein Backup empfehlenswert.

## Tests

```bash
python3 -m pip install -r requirements-dev.txt
pytest -q
```

GitHub Actions führt die Tests bei Pushes und Pull Requests aus. Der Quellcode enthält keine externen Trackingdienste, CDN-Abhängigkeiten oder Drittanbieter-Skripte für die Oberfläche.

## Sicherheitsmodell und Grenzen

- **Single-Admin-App:** für einen privaten Nutzer, kein Mehrbenutzerdienst.
- Sessions sind zufällig generiert, serverseitig gespeichert, nach 12 Stunden abgelaufen und beim Logout widerrufbar; Cookies sind im Produktionsmodus `HttpOnly`, `Secure` und `SameSite=Strict`.
- Änderungen benötigen CSRF-Token; Authentifizierung ist gegen wiederholte Fehlversuche gedrosselt.
- Nachrichten sind nur als **Text** sichtbar; unsicheres Mail-HTML, aktive Inhalte und Anhänge werden nicht angezeigt.
- Keine öffentliche REST-API ohne Anmeldung; keine SMTP-Weiterleitung/Versandfunktion.
- Standardmäßig max. 25 Aliasse, 10 Neuanlagen/Stunde, max. 2.000 Nachrichten und 14 Tage Aufbewahrung.
- Rate Limits sind für eine **Single-Instance-Installation** konzipiert. Verteile den Dienst nicht auf mehrere App-Worker. Im Produktions-Compose wird die echte Client-IP ausschließlich über den vorgeschalteten Caddy-Proxy übernommen. Port 8000 darf dabei nicht zusätzlich öffentlich erreichbar sein.
- SQLite und Authentifizierungsgeheimnisse liegen auf deinem Server; **keine Verschlüsselung gespeicherter Daten auf Applikationsebene**. Schütze Server, Volume und Backups.
- Es gibt noch keine Spam-Filterung, Virenscans oder Attachment-Archivierung. STARTTLS muss mit eigenem Zertifikat aktiviert werden.
- Das Projekt ist ein technisch nutzbares **MVP**, aber kein fertig auditiertes Enterprise-Mailprodukt.

Weitere Hinweise stehen in [SECURITY.md](SECURITY.md).

## Häufige Fragen

**Kann ich damit beliebige `@gmail.com`-Adressen erzeugen?** Nein. Die App verwaltet nur Adressen unter einer Domain, die du selbst kontrollierst.

**Kann ich mit der lokalen Demo echte öffentliche Mails empfangen?** Nein. Dazu müssen die Domain, MX-Record und der erreichbare SMTP-Server zusammenpassen.

**Sind E-Mail-Adressen automatisch bei Instagram oder anderen Plattformen gültig?** Es sind technisch echte Empfangsadressen, wenn DNS/SMTP funktioniert. Ob eine Drittplattform sie für neue Konten akzeptiert, entscheidet sie selbst. Kein System garantiert diese Akzeptanz.

**Kann ich mehrere Aliasse in einem Postfach sehen?** Ja. Im Dashboard werden alle Nachrichten einer einzigen lokalen Datenbank zugeordnet.

**Warum existieren die Aliasse nicht als eigene Systembenutzer?** AliasDock prüft Empfänger direkt in SQLite. Alle erlaubten Empfänger werden an die App zugestellt. Dadurch benötigt nicht jede Adresse ein eigenes Betriebssystem-Postfach.

## Lizenz

MIT – siehe [LICENSE](LICENSE).
