#!/usr/bin/env python3
"""Consistent SQLite online backup from inside running application container."""
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

src = Path(os.getenv("DATABASE_PATH", "/data/aliasdock.sqlite3"))
if not src.is_file():
    sys.exit("Database does not exist")
outdir = Path("/data/backups")
outdir.mkdir(parents=True, exist_ok=True)
outfile = outdir / ("aliasdock-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + ".sqlite3")
with sqlite3.connect(src) as source, sqlite3.connect(outfile) as destination:
    source.backup(destination)
print("Backup saved to", outfile)
