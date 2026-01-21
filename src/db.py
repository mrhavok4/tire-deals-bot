import sqlite3
from typing import Dict, Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS deals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  url TEXT NOT NULL,
  title TEXT NOT NULL,
  price_cents INTEGER,
  source TEXT,
  first_seen_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  last_seen_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(url, price_cents)
);
"""

def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute(SCHEMA)
    return conn

def upsert_deal(conn: sqlite3.Connection, deal: Dict[str, Any]) -> bool:
    try:
        conn.execute(
            "INSERT INTO deals (url, title, price_cents, source) VALUES (?, ?, ?, ?)",
            (deal["url"], deal["title"], deal.get("price_cents"), deal.get("source")),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        conn.execute(
            "UPDATE deals SET last_seen_at=CURRENT_TIMESTAMP WHERE url=? AND price_cents IS ?",
            (deal["url"], deal.get("price_cents")),
        )
        conn.commit()
        return False
