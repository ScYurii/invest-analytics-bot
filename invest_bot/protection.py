"""Crash protection: S&P 500 against its 200-day average at month ends.

The rule (tested since 2007, see ROADMAP.md): when SPY closes a month below its
200-day average, leave stocks for T-bills (BIL); come back when a month closes
above. Since 2007 it cut the worst fall about in half for under 2 points a year,
but most signals were false alarms: it truly helped once (2008). Shown as a hint
only; the numbers are computed anew for every report.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from .portfolio import Prices

START = "2007-06-01"   # BIL exists from 2007-05-30
WARN = 0.02            # warn when SPY is closer than this to its average


@dataclass
class Signal:
    out: str            # month-end when the rule left the market
    back: str | None    # month-end when it came back (None: still out)
    spy: float          # SPY over that time
    bil: float          # T-bills over that time
    worst: float        # the deepest SPY fall after leaving
    verdict: str        # "helped", "false alarm", "even"


@dataclass
class Protection:
    gap: float                  # SPY close against its 200-day average, today
    month_end: str              # the last completed month-end
    month_gap: float            # the gap at that month-end
    fired: bool                 # the rule says: out of the market
    level: str                  # "ok", "warn", "fired"
    signals: list[Signal] = field(default_factory=list)
    cost: float = 0.0           # mean of (SPY - BIL) over false alarms
    cagr: tuple[float, float] = (0.0, 0.0)   # per year: holding SPY, following the rule
    worst: tuple[float, float] = (0.0, 0.0)  # deepest fall: holding SPY, following the rule


def _month_end(dates: list[str], i: int) -> bool:
    return i + 1 < len(dates) and dates[i][:7] != dates[i + 1][:7]


def check(px: Prices) -> Protection:
    dates, close = px.series("SPY", "close")
    _, adj = px.series("SPY")
    bil_d = dict(zip(*px.series("BIL")))

    def gap(i: int) -> float:
        return close[i] / statistics.fmean(close[i - 199:i + 1]) - 1

    signals, out_at, last_end = [], None, None
    i0 = next(i for i, d in enumerate(dates) if d >= START)
    for i in range(i0, len(dates)):
        if not _month_end(dates, i):
            continue
        last_end = i
        g = gap(i)
        if out_at is None and g < 0:
            out_at = i
        elif out_at is not None and g > 0:
            signals.append(_signal(dates, adj, bil_d, out_at, i))
            out_at = None
    if out_at is not None:
        signals.append(_signal(dates, adj, bil_d, out_at, None))

    # The rule against holding, day by day; switches happen at month-end closes
    hold = rule = 1.0
    peak_h = peak_r = 1.0
    dd_h = dd_r = 0.0
    out = False
    for i in range(i0, len(dates) - 1):
        d, n = dates[i], dates[i + 1]
        hold *= adj[i + 1] / adj[i]
        if out and bil_d.get(d) and bil_d.get(n):
            rule *= bil_d[n] / bil_d[d]
        elif not out:
            rule *= adj[i + 1] / adj[i]
        peak_h, peak_r = max(peak_h, hold), max(peak_r, rule)
        dd_h, dd_r = min(dd_h, hold / peak_h - 1), min(dd_r, rule / peak_r - 1)
        if _month_end(dates, i):
            out = gap(i) < 0
    years = (len(dates) - 1 - i0) / 252

    now, month_gap = gap(len(close) - 1), gap(last_end)
    fired = month_gap < 0
    level = "fired" if fired else ("warn" if now < WARN else "ok")
    false = [s.spy - s.bil for s in signals if s.verdict == "false alarm"]
    return Protection(now, dates[last_end], month_gap, fired, level, signals,
                      statistics.fmean(false) if false else 0.0,
                      (hold ** (1 / years) - 1, rule ** (1 / years) - 1), (dd_h, dd_r))


def _signal(dates, adj, bil_d, i, j) -> Signal:
    end = j if j is not None else len(dates) - 1
    spy = adj[end] / adj[i] - 1
    b0, b1 = bil_d.get(dates[i]), bil_d.get(dates[end])
    bil = b1 / b0 - 1 if b0 and b1 else 0.0
    worst = min(adj[i:end + 1]) / adj[i] - 1
    verdict = "helped" if spy < bil - 0.02 else ("false alarm" if spy > bil + 0.02 else "even")
    return Signal(dates[i], dates[j] if j is not None else None, spy, bil, worst, verdict)


def summary(p: Protection) -> str:
    n = len(p.signals)
    helped = [s for s in p.signals if s.verdict == "helped"]
    false = sum(s.verdict == "false alarm" for s in p.signals)
    big = ", ".join(f"{s.out[:7]}…{(s.back or 'сейчас')[:7]}: S&P 500 {s.spy:+.0%}" for s in helped)
    return (f"С {START[:4]} г. правило срабатывало {n} раз: спасло от падения {len(helped)} ({big}), "
            f"ложная тревога {false} раз (рынок за время выхода в среднем рос на {p.cost:+.0%}). "
            f"В сумме худшее падение {p.worst[1]:.0%} вместо {p.worst[0]:.0%}, ценой "
            f"{(p.cagr[1] - p.cagr[0]) * 100:+.1f} п.п. доходности в год.")


def status_line(p: Protection) -> str:
    if p.level == "fired":
        return (f"🔴 Защита от обвала: на конец месяца ({p.month_end}) S&P 500 ниже 200-дневной средней на "
                f"{-p.month_gap:.1%} — правило сработало")
    if p.level == "warn":
        return (f"🟡 Защита от обвала: S&P 500 близко к 200-дневной средней ({p.gap:+.1%}); правило проверяется "
                f"по закрытию месяца")
    return f"🟢 Защита от обвала: сигнала нет, S&P 500 выше 200-дневной средней на {p.gap:.1%}"
