"""Buy candidates: S&P 500 stocks that pass simple, tested rules.

Rules, chosen with scripts/test_candidates.py (see ROADMAP.md):
- strength: ranked by the return over 12 months without the last one
  ("12-1 momentum"); the top names are always stronger than SPY;
- uptrend: close above its 200-day average.
A "near the 52-week high" filter cut the return in the test and was dropped.
A reason to study a company, not a recommendation.
"""
from __future__ import annotations

import statistics
from bisect import bisect_right
from dataclasses import dataclass

from .portfolio import Prices

TOP = 10


@dataclass
class Metrics:
    symbol: str
    close: float
    mom: float          # 12-1 momentum (adjusted for dividends)
    above: bool         # close above the 200-day average
    drawdown: float     # from the 52-week high
    r1m: float


def metrics(dates: list[str], close: list[float], adj: list[float], i: int, symbol: str) -> Metrics | None:
    """Metrics on day i, using data up to day i only."""
    if i < 252:
        return None
    return Metrics(
        symbol, close[i],
        adj[i - 21] / adj[i - 252] - 1,
        close[i] > statistics.fmean(close[i - 199:i + 1]),
        close[i] / max(close[i - 251:i + 1]) - 1,
        adj[i] / adj[i - 21] - 1,
    )


def passes(m: Metrics, spy_mom: float) -> bool:
    return m.above and m.mom > spy_mom


def screen(px: Prices, members: list[dict], day: str | None = None, top: int = TOP) -> tuple[list[Metrics], float]:
    """Top candidates on `day` (default: the last day with data) and SPY's 12-1 momentum."""
    sd, _ = px.series("SPY")
    day = day or sd[-1]
    j = bisect_right(sd, day) - 1
    _, sa = px.series("SPY")
    spy_mom = sa[j - 21] / sa[j - 252] - 1
    out = []
    for m in members:
        sym = m["symbol"].replace(".", "-")
        d, c = px.series(sym, "close")
        if not d:
            continue
        _, a = px.series(sym)
        i = bisect_right(d, day) - 1
        if i < 0 or d[i] < sd[j]:          # no bar on that day: stale or delisted
            continue
        x = metrics(d, c, a, i, sym)
        if x and passes(x, spy_mom):
            out.append(x)
    return sorted(out, key=lambda x: -x.mom)[:top], spy_mom
