"""How well did the existing positions do, compared with buying SPY instead?

Every purchase (lot) is followed to its sale (FIFO) or to today. The result
includes dividends (gross, by ex-date). The benchmark is the same money put
into SPY (total return) on the same day for the same time; for EUR lots SPY is
converted to EUR. Currency conversions and fees are not counted.
"""
import logging
import sqlite3
import sys
from bisect import bisect_right
from collections import defaultdict, deque
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from invest_bot.broker import ReadOnlyBroker  # noqa: E402
from invest_bot.portfolio import yahoo_symbol  # noqa: E402

logging.basicConfig(level=logging.WARNING)
con = sqlite3.connect(ROOT / "data" / "prices.db")


def series(sym: str, col: str = "adj_close"):
    rows = con.execute(f"SELECT date, {col} FROM bars WHERE symbol = ? ORDER BY date", (sym,)).fetchall()
    return [d for d, _ in rows], [v for _, v in rows]


def at(s, d: str) -> float:
    """Value on date d or the last trading day before it."""
    dates, vals = s
    return vals[bisect_right(dates, d) - 1]


SPY, FX = series("SPY"), series("EURUSD=X", "close")  # FX: USD per 1 EUR


def dividends(sym: str, a: str, b: str) -> float:
    (x,) = con.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM dividends WHERE symbol = ? AND date > ? AND date <= ?",
        (sym, a, b)).fetchone()
    return x


def main() -> None:
    b = ReadOnlyBroker()
    today = SPY[0][-1]
    trades = b.trades("2015-01-01", date.today().isoformat())["trades"]["trade"]
    live = {p["i"]: p for p in b.positions()["result"]["ps"]["pos"]}

    lots = defaultdict(deque)   # instrument -> open lots [date, qty, price, curr]
    done = []                   # (instr, buy date, qty, buy price, end date, end price, curr, open?)
    skipped = set()
    for t in sorted(trades, key=lambda x: x["date"]):
        instr, d = t["instr_nm"], t["date"][:10]
        if "/" in instr:                       # currency exchange
            continue
        if not instr.endswith((".US", ".EU")):
            skipped.add(instr)
            continue
        q, p = float(t["q"]), float(t["p"])
        if t["type"] == "1":
            lots[instr].append([d, q, p, t["curr_c"]])
            continue
        while q > 1e-9:                        # sale: close the oldest lots first
            lot = lots[instr][0]
            n = min(q, lot[1])
            done.append((instr, lot[0], n, lot[2], d, p, lot[3], False))
            lot[1] -= n
            q -= n
            if lot[1] <= 1e-9:
                lots[instr].popleft()
    for instr, rest in lots.items():
        for d, q, p, curr in rest:
            done.append((instr, d, q, p, today, float(live[instr]["mkt_price"]), curr, True))

    print(f"{'instrument':9} {'bought':10} {'qty':>4} {'price':>8} {'sold/now':10} {'price':>8} "
          f"{'result':>7} {'per yr':>7} {'SPY':>7} {'vs SPY':>7}")
    tot = defaultdict(float)
    for instr, d0, q, p0, d1, p1, curr, is_open in sorted(done, key=lambda x: x[1]):
        ysym = yahoo_symbol(instr)
        cost = q * p0
        value = q * (p1 + dividends(ysym, d0, d1))
        spy = at(SPY, d1) / at(SPY, d0)
        if curr == "EUR":                      # SPY bought with euros
            spy *= at(FX, d0) / at(FX, d1)
        years = max((date.fromisoformat(d1) - date.fromisoformat(d0)).days, 1) / 365.25
        r = value / cost - 1
        print(f"{instr:9} {d0} {q:4.0f} {p0:8.2f} {d1 + ('*' if is_open else ' '):11}{p1:8.2f} "
              f"{r:+7.1%} {(1 + r) ** (1 / years) - 1:+7.1%} {spy - 1:+7.1%} {r - (spy - 1):+7.1%}")
        # Totals in EUR at the rates of the buy and end dates
        to_eur0 = 1 if curr == "EUR" else 1 / at(FX, d0)
        to_eur1 = 1 if curr == "EUR" else 1 / at(FX, d1)
        tot["cost"] += cost * to_eur0
        tot["value"] += value * to_eur1
        tot["spy"] += cost * to_eur0 * spy * (at(FX, d0) / at(FX, d1) if curr == "USD" else 1)
    print(f"\n* still held, valued at today's price. Dividends gross. Not included: {', '.join(sorted(skipped)) or '-'}")
    print(f"\nIn EUR (with the USD/EUR rate change): invested {tot['cost']:.0f}, "
          f"now/received {tot['value']:.0f} ({tot['value'] / tot['cost'] - 1:+.1%}); "
          f"same money in SPY: {tot['spy']:.0f} ({tot['spy'] / tot['cost'] - 1:+.1%})")


if __name__ == "__main__":
    main()
