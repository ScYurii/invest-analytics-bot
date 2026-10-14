"""Portfolio data: positions from the broker, purchase lots from the trade history."""
from __future__ import annotations

import sqlite3
from bisect import bisect_right
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .broker import ReadOnlyBroker

# Tradernet ticker -> Yahoo ticker, where they differ beyond the ".US" suffix:
# European listings need the exchange, e.g. "SAP.EU SAP.DE" (Xetra) or "ENI.EU ENI.MI"
# (Milan). One pair per line; kept in data/ with the account's own data.
SYMBOLS = Path(__file__).resolve().parent.parent / "data" / "symbols.txt"


def _load_symbols(path: Path = SYMBOLS) -> dict[str, str]:
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return {}
    pairs = (line.split("#")[0].split() for line in lines)
    return {p[0]: p[1] for p in pairs if len(p) == 2}


YAHOO = _load_symbols()


def yahoo_symbol(instr: str) -> str:
    return YAHOO.get(instr, instr.removesuffix(".US"))


@dataclass
class Lot:
    instr: str
    bought: str          # date
    qty: float
    price: float
    curr: str
    sold: str | None = None
    sell_price: float | None = None


@dataclass
class Position:
    instr: str
    name: str
    qty: float
    price: float         # last price
    avg_price: float     # broker's average purchase price
    curr: str


class Prices:
    """Read access to data/prices.db."""

    def __init__(self, con: sqlite3.Connection) -> None:
        self.con = con
        self._cache: dict[tuple[str, str], tuple[list[str], list[float]]] = {}

    def series(self, sym: str, col: str = "adj_close") -> tuple[list[str], list[float]]:
        key = (sym, col)
        if key not in self._cache:
            rows = self.con.execute(
                f"SELECT date, {col} FROM bars WHERE symbol = ? ORDER BY date", (sym,)).fetchall()
            self._cache[key] = ([d for d, _ in rows], [v for _, v in rows])
        return self._cache[key]

    def at(self, sym: str, d: str, col: str = "adj_close") -> float:
        """Value on date d or on the last trading day before it."""
        dates, vals = self.series(sym, col)
        return vals[bisect_right(dates, d) - 1]

    def dividends(self, sym: str, after: str, until: str) -> float:
        (x,) = self.con.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM dividends"
            " WHERE symbol = ? AND date > ? AND date <= ?", (sym, after, until)).fetchone()
        return x

    def eur(self, amount: float, curr: str, d: str) -> float:
        """Convert USD or EUR to EUR at the rate of date d."""
        return amount if curr == "EUR" else amount / self.at("EURUSD=X", d, "close")


def load(broker: ReadOnlyBroker) -> tuple[list[Position], dict[str, float], list[Lot], set[str]]:
    """Positions, cash by currency, all lots (open and closed), skipped instruments."""
    ps = broker.positions()["result"]["ps"]
    positions = [
        Position(p["i"], p["name"], float(p["q"]), float(p["mkt_price"]),
                 float(p["bal_price_a"]), p["curr"])
        for p in ps["pos"]
    ]
    cash = {a["curr"]: float(a["s"]) for a in ps["acc"]}

    trades = broker.trades("2015-01-01", date.today().isoformat())["trades"]["trade"]
    open_lots: dict[str, deque[Lot]] = defaultdict(deque)
    lots: list[Lot] = []
    skipped = set()
    for t in sorted(trades, key=lambda x: x["date"]):
        instr, d = t["instr_nm"], t["date"][:10]
        if "/" in instr:                   # currency exchange
            continue
        if not instr.endswith((".US", ".EU")):
            skipped.add(instr)             # structured products and the like
            continue
        q, p = float(t["q"]), float(t["p"])
        if t["type"] == "1":
            lot = Lot(instr, d, q, p, t["curr_c"])
            open_lots[instr].append(lot)
            lots.append(lot)
            continue
        while q > 1e-9:                    # a sale closes the oldest lots first
            lot = open_lots[instr][0]
            n = min(q, lot.qty)
            if n < lot.qty:                # split the lot: the sold part is closed
                closed = Lot(instr, lot.bought, n, lot.price, lot.curr, d, p)
                lots.append(closed)
                lot.qty -= n
            else:
                lot.sold, lot.sell_price = d, p
                open_lots[instr].popleft()
            q -= n
    return positions, cash, lots, skipped
