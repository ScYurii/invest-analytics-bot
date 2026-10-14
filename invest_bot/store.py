"""Local SQLite store for daily prices."""
from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from .yahoo import History

DB = Path(__file__).resolve().parent.parent / "data" / "prices.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS bars (
    symbol TEXT NOT NULL, date TEXT NOT NULL,
    open REAL, high REAL, low REAL, close REAL, adj_close REAL, volume INTEGER,
    PRIMARY KEY (symbol, date)
);
CREATE TABLE IF NOT EXISTS dividends (
    symbol TEXT NOT NULL, date TEXT NOT NULL, amount REAL,
    PRIMARY KEY (symbol, date)
);
CREATE TABLE IF NOT EXISTS splits (
    symbol TEXT NOT NULL, date TEXT NOT NULL, numerator REAL, denominator REAL,
    PRIMARY KEY (symbol, date)
);
CREATE TABLE IF NOT EXISTS symbols (
    symbol TEXT PRIMARY KEY, source TEXT, currency TEXT, timezone TEXT,
    first_date TEXT, last_date TEXT, updated_at TEXT
);
"""


def connect(path: Path = DB) -> sqlite3.Connection:
    path.parent.mkdir(exist_ok=True)
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    return con


def save(con: sqlite3.Connection, h: History) -> None:
    """Replace the whole history of a symbol.

    adj_close of every past bar changes with each new dividend or split,
    so a full refresh is simpler and safer than appending new days.
    """
    with con:
        for table in ("bars", "dividends", "splits"):
            con.execute(f"DELETE FROM {table} WHERE symbol = ?", (h.symbol,))
        con.executemany("INSERT INTO bars VALUES (?,?,?,?,?,?,?,?)", [(h.symbol, *b) for b in h.bars])
        con.executemany("INSERT INTO dividends VALUES (?,?,?)", [(h.symbol, *d) for d in h.dividends])
        con.executemany("INSERT INTO splits VALUES (?,?,?,?)", [(h.symbol, *s) for s in h.splits])
        con.execute(
            "INSERT OR REPLACE INTO symbols VALUES (?,?,?,?,?,?,?)",
            (
                h.symbol, "yahoo", h.currency, h.timezone,
                h.bars[0][0] if h.bars else None, h.bars[-1][0] if h.bars else None,
                datetime.now(UTC).isoformat(timespec="seconds"),
            ),
        )
