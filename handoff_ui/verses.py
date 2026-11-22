"""Public-domain World English Bible verses, rotated by local calendar day."""
from datetime import date
import json
from pathlib import Path

CATALOG = json.loads((Path(__file__).resolve().parent.parent / 'assets/verses.json').read_text())

def daily_verse(day=None):
    day = day or date.today()
    return dict(CATALOG[(day - date(2026, 1, 1)).days % len(CATALOG)])
