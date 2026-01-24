import sqlite3
from datetime import datetime, timezone

DB_PATH = "alerts.db"

def connect():
    return sqlite3.connect(DB_PATH)

def init_db():
    with connect() as c:
        c.execute("""
        CREATE TABLE IF NOT EXISTS seen (
          mls_id TEXT PRIMARY KEY,
          first_seen_utc TEXT NOT NULL
        )
        """)
        c.execute("""
        CREATE TABLE IF NOT EXISTS alerted (
          mls_id TEXT PRIMARY KEY,
          alerted_at_utc TEXT NOT NULL,
          listing_ppsf REAL NOT NULL,
          baseline_ppsf REAL NOT NULL,
          threshold_ppsf REAL NOT NULL
        )
        """)

def mark_seen(c: sqlite3.Connection, mls_id: str) -> bool:
    """
    Returns True if this MLS id was newly seen in this run.
    """
    cur = c.execute("SELECT 1 FROM seen WHERE mls_id=?", (mls_id,))
    if cur.fetchone():
        return False
    c.execute(
        "INSERT INTO seen(mls_id, first_seen_utc) VALUES(?,?)",
        (mls_id, datetime.now(timezone.utc).isoformat()),
    )
    return True

def already_alerted(c: sqlite3.Connection, mls_id: str) -> bool:
    return c.execute("SELECT 1 FROM alerted WHERE mls_id=?", (mls_id,)).fetchone() is not None

def save_alert(c: sqlite3.Connection, mls_id: str, listing_ppsf: float, baseline_ppsf: float, threshold_ppsf: float):
    c.execute(
        """
        INSERT OR IGNORE INTO alerted(mls_id, alerted_at_utc, listing_ppsf, baseline_ppsf, threshold_ppsf)
        VALUES(?,?,?,?,?)
        """,
        (mls_id, datetime.now(timezone.utc).isoformat(), listing_ppsf, baseline_ppsf, threshold_ppsf),
    )
