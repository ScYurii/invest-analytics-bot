"""Sanity checks for the stored daily bars."""
from __future__ import annotations

import sqlite3

REFERENCE = "SPY"   # its trading days are the calendar for US symbols
JUMP = 0.25         # a daily move of adj_close above this is suspicious
TOLERANCE = 0.002   # rounding slack for open/close vs high/low


def check(con: sqlite3.Connection, symbol: str) -> list[str]:
    rows = con.execute(
        "SELECT date, open, high, low, close, adj_close, volume FROM bars"
        " WHERE symbol = ? ORDER BY date", (symbol,)
    ).fetchall()
    if not rows:
        return ["no bars"]
    problems = []

    calendar = [d for (d,) in con.execute(
        "SELECT date FROM bars WHERE symbol = ? AND date BETWEEN ? AND ? ORDER BY date",
        (REFERENCE, rows[0][0], rows[-1][0]),
    )]
    have = {r[0] for r in rows}
    missing = [d for d in calendar if d not in have]
    if missing:
        problems.append(f"{len(missing)} missing days vs {REFERENCE}, e.g. {', '.join(missing[:3])}")
    extra = len(have - set(calendar)) if calendar else 0
    if extra:
        problems.append(f"{extra} days that {REFERENCE} does not have")

    bad = [
        d for d, o, h, lo, c, a, v in rows
        if min(o, h, lo, c, a) <= 0 or h < lo
        or not lo * (1 - TOLERANCE) <= o <= h * (1 + TOLERANCE)
        or not lo * (1 - TOLERANCE) <= c <= h * (1 + TOLERANCE)
    ]
    if bad:
        problems.append(f"{len(bad)} inconsistent bars (OHLC), e.g. {', '.join(bad[:3])}")

    jumps = [
        f"{rows[i][0]} {rows[i][5] / rows[i - 1][5] - 1:+.0%}"
        for i in range(1, len(rows))
        if abs(rows[i][5] / rows[i - 1][5] - 1) > JUMP
    ]
    if jumps:
        problems.append(f"{len(jumps)} daily moves over {JUMP:.0%}: {', '.join(jumps[:3])}")

    zero_vol = sum(1 for r in rows if not r[6])
    if zero_vol:
        problems.append(f"{zero_vol} days with zero volume")

    (last_ref,) = con.execute("SELECT MAX(date) FROM bars WHERE symbol = ?", (REFERENCE,)).fetchone()
    if last_ref and rows[-1][0] < last_ref:
        problems.append(f"stale: last bar {rows[-1][0]}, {REFERENCE} has {last_ref}")
    return problems
