"""Daily value of the portfolio against the same money put into SPY.

Only the invested part is followed: cash on the account is left out on both
sides. On every purchase the benchmark buys SPY for the same amount, on every
sale it sells SPY for the amount received. Values in EUR.
"""
from __future__ import annotations

from .portfolio import Lot, Prices, yahoo_symbol


def split_factor(px: Prices, sym: str, d: str) -> float:
    """Shares held on day d per share in today's (split-adjusted) terms."""
    f = 1.0
    for num, den in px.con.execute(
            "SELECT numerator, denominator FROM splits WHERE symbol = ? AND date > ?", (sym, d)):
        f *= num / den
    return f


def series(px: Prices, lots: list[Lot]) -> dict[str, list]:
    dates = [d for d in px.series("SPY")[0] if d >= min(lot.bought for lot in lots)]
    events = sorted([(lot.bought, +1, lot) for lot in lots] +
                    [(lot.sold, -1, lot) for lot in lots if lot.sold], key=lambda e: (e[0], e[1]))
    value, bench, cost = [], [], []
    spy_units, k = 0.0, 0
    for d in dates:
        while k < len(events) and events[k][0] <= d:
            when, sign, lot = events[k]
            price = lot.price if sign > 0 else lot.sell_price
            amount = px.eur(lot.qty * price, lot.curr, when)
            spy_units += sign * amount / spy_eur(px, when)
            k += 1
        held = [lot for lot in lots if lot.bought <= d and (lot.sold is None or lot.sold > d)]
        v = 0.0
        for lot in held:
            ys = yahoo_symbol(lot.instr)
            close = px.at(ys, d, "close")
            v += px.eur(lot.qty * close * split_factor(px, ys, d), lot.curr, d)
        value.append(round(v, 2))
        bench.append(round(spy_units * spy_eur(px, d), 2))
        cost.append(round(sum(px.eur(lot.qty * lot.price, lot.curr, lot.bought) for lot in held), 2))
    return {"dates": dates, "value": value, "spy": bench, "cost": cost}


def spy_eur(px: Prices, d: str) -> float:
    """SPY total-return price in EUR."""
    return px.at("SPY", d) / px.at("EURUSD=X", d, "close")

