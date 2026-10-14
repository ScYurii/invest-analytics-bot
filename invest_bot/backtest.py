"""A small daily backtester for "hold one asset at a time" strategies.

Rules that matter for a 100-1000 EUR account:
- whole shares only. At the start of a run one share costs what the cheap twin
  costs today (SPY -> SPYM, QQQ -> QQQM, GLD -> GLDM), so the budget buys as many
  shares as it would now; after that the price follows the total-return series
  of the long-history fund;
- every order pays the Freedom24 "Smart" fee: FIXED + PER_SHARE * shares,
  plus SLIPPAGE of the traded value;
- a decision is taken on the close of an evaluation day and executed on the
  close of the next trading day (no look-ahead);
- money that is not invested earns nothing.
"""
from __future__ import annotations

import math
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date

FIXED = 2.0        # per order
PER_SHARE = 0.02   # per share
SLIPPAGE = 0.0005  # of traded value, each side
CASH = "CASH"      # not invested
BIL_PROXY = "BIL"  # T-bill fund, used as the "cash" asset where it has data

# Share prices of what would really be traded; filled from the database
TWINS = {"SPY": "SPYM", "QQQ": "QQQM", "GLD": "GLDM", "VTI": "SCHB"}


class Data:
    """Total-return prices (adj_close) aligned on the SPY calendar."""

    def __init__(self, con: sqlite3.Connection, symbols: list[str]) -> None:
        self.dates = [d for (d,) in con.execute(
            "SELECT date FROM bars WHERE symbol = 'SPY' ORDER BY date")]
        self.px: dict[str, list[float | None]] = {}
        self.today: dict[str, float] = {}  # today's price of the tradable twin
        self.scale: dict[str, float] = {}
        for s in symbols:
            rows = dict(con.execute("SELECT date, adj_close FROM bars WHERE symbol = ?", (s,)))
            self.px[s] = [rows.get(d) for d in self.dates]
            twin = TWINS.get(s, s)
            (self.today[s],) = con.execute(
                "SELECT close FROM bars WHERE symbol = ? ORDER BY date DESC LIMIT 1", (twin,)
            ).fetchone()

    def anchor(self, i0: int) -> None:
        """Make one share cost today's twin price on day i0 (or the first day with data)."""
        for s, series in self.px.items():
            first = next(p for p in series[i0:] if p is not None)
            self.scale[s] = self.today[s] / first

    def index(self, d: str) -> int:
        return next(i for i, x in enumerate(self.dates) if x >= d)

    def price(self, s: str, i: int) -> float | None:
        """Price of one tradable share (twin scale) on day i."""
        p = self.px[s][i]
        return None if p is None else p * self.scale[s]

    def ret(self, s: str, i: int, lookback: int) -> float | None:
        a, b = self.px[s][i - lookback], self.px[s][i]
        return None if a is None or b is None else b / a - 1


# A strategy looks at data up to day i (inclusive) and names the asset to hold
Strategy = Callable[[Data, int], str]


def is_eval_day(dates: list[str], i: int, freq: str) -> bool:
    """Last trading day of the week or month."""
    if i + 1 >= len(dates):
        return False
    a, b = date.fromisoformat(dates[i]), date.fromisoformat(dates[i + 1])
    if freq == "weekly":
        return a.isocalendar()[:2] != b.isocalendar()[:2]
    if freq == "monthly":
        return (a.year, a.month) != (b.year, b.month)
    raise ValueError(freq)


@dataclass
class Result:
    equity: list[float]
    dates: list[str]
    orders: int = 0
    fees: float = 0.0
    days_invested: int = 0
    unaffordable: int = 0  # evaluations where the target was too expensive
    holdings: list[str] = field(default_factory=list)


def run(data: Data, strategy: Strategy, freq: str, budget: float, start: str) -> Result:
    i0 = data.index(start)
    data.anchor(i0)
    cash, held, shares = budget, CASH, 0
    pending: str | None = strategy(data, i0 - 1)  # buy on the first day
    res = Result([], data.dates[i0:])

    for i in range(i0, len(data.dates)):
        if pending is not None and pending != held:
            if held != CASH:  # sell everything
                value = shares * data.price(held, i)
                fee = FIXED + PER_SHARE * shares + SLIPPAGE * value
                cash += value - fee
                res.orders += 1
                res.fees += fee
                held, shares = CASH, 0
            if pending != CASH:
                p = data.price(pending, i)
                n = math.floor((cash - FIXED) / (p * (1 + SLIPPAGE) + PER_SHARE)) if p else 0
                if n >= 1:
                    value = n * p
                    fee = FIXED + PER_SHARE * n + SLIPPAGE * value
                    cash -= value + fee
                    res.orders += 1
                    res.fees += fee
                    held, shares = pending, n
                else:
                    res.unaffordable += 1
        pending = None

        res.equity.append(cash + (shares * data.price(held, i) if held != CASH else 0.0))
        res.holdings.append(held)
        res.days_invested += held != CASH
        if is_eval_day(data.dates, i, freq):
            target = strategy(data, i)
            if target != held:
                pending = target
    return res


def cagr(equity: list[float], dates: list[str]) -> float:
    years = (date.fromisoformat(dates[-1]) - date.fromisoformat(dates[0])).days / 365.25
    return (equity[-1] / equity[0]) ** (1 / years) - 1 if equity[0] > 0 else float("nan")


def max_drawdown(equity: list[float]) -> float:
    peak, worst = equity[0], 0.0
    for v in equity:
        peak = max(peak, v)
        worst = min(worst, v / peak - 1)
    return worst


def period(res: Result, a: str, b: str) -> tuple[list[float], list[str]]:
    idx = [k for k, d in enumerate(res.dates) if a <= d <= b]
    return [res.equity[k] for k in idx], [res.dates[k] for k in idx]
