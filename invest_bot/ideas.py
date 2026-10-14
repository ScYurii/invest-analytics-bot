"""This week's Freedom24 investment ideas, with signals and the track record."""
from __future__ import annotations

import csv
import statistics
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .broker import BrokerError, ReadOnlyBroker

MSK = timezone(timedelta(hours=3))  # Tradernet bar timestamps are midnight Moscow time


@dataclass
class IdeaView:
    id: int
    date: str
    ticker: str
    company: str
    title: str
    price: float          # current price
    curr: str
    target: float
    upside: float         # target against the current price
    horizon: str
    risk: str | None
    trend_up: bool | None
    rel3: float | None    # 3-month return minus SPY (prices only)
    rel12: float | None
    drawdown: float | None
    url: str


@dataclass
class TrackRecord:
    n: int
    mean: float
    median: float
    spy: float
    beat: float
    hit: float
    loss: float


def track_record(results: Path, trend_up: bool | None = None) -> TrackRecord | None:
    """Closed ideas from analyze_ideas.py; optionally only those whose stock was
    in an uptrend (True) or a downtrend (False) on the day of the idea."""
    if not results.exists():
        return None
    rows = [r for r in csv.DictReader(results.open()) if r["status"].startswith("closed")
            and (trend_up is None or r.get("trend_up") == str(trend_up))]
    if not rows:
        return None
    ret = [float(r["ret"]) for r in rows]
    spy = [float(r["spy"]) for r in rows]
    return TrackRecord(
        len(rows), statistics.fmean(ret), statistics.median(ret), statistics.fmean(spy),
        sum(a > b for a, b in zip(ret, spy)) / len(rows),
        sum(r["hit"] == "True" for r in rows) / len(rows),
        sum(x < 0 for x in ret) / len(rows),
    )


def _closes(broker: ReadOnlyBroker, ticker: str) -> list[float]:
    c = broker.candles(ticker, datetime.now() - timedelta(days=400), datetime.now())
    k = next(iter(c.get("hloc") or {}), None)
    return [x[3] for x in c["hloc"][k]] if k else []


def _ret(c: list[float], n: int) -> float | None:
    return c[-1] / c[-1 - n] - 1 if len(c) > n else None


def _details(broker: ReadOnlyBroker, idea_id: int) -> dict:
    """The server sometimes answers with empty details; ask a few times."""
    for attempt in range(3):
        try:
            d = broker._call("getInvestIdeaDetails", {"id": idea_id})
            if isinstance(d.get("details"), dict):
                return d["details"]
        except BrokerError:
            pass
        time.sleep(3 * (attempt + 1))
    return {}


def this_week(broker: ReadOnlyBroker, days: int = 7) -> list[IdeaView]:
    since = (date.today() - timedelta(days=days)).isoformat()
    ideas = [i for i in broker._call("getInvestIdeas", {})["list"]
             if i["rawDate"][:10] >= since and i["investIdeaType"] == 1
             and i["instr_type_c"] == 1 and i.get("ticker")]
    spy = _closes(broker, "SPY.US")
    out = []
    for i in sorted(ideas, key=lambda x: x["rawDate"], reverse=True):
        c = _closes(broker, i["ticker"])
        det = _details(broker, i["id"])
        sma = statistics.fmean(c[-200:]) if len(c) >= 200 else None
        r3, r12 = _ret(c, 63), _ret(c, 252)
        price = float(i.get("quotesCurrentPrice") or i["currentPrice"])
        target = float(i["targetPrice"])
        out.append(IdeaView(
            id=i["id"], date=i["rawDate"][:10], ticker=i["ticker"], company=i.get("company") or "",
            title=i["title"], price=price, curr=i.get("currency") or "", target=target,
            upside=target / price - 1, horizon=i.get("targetText") or "", risk=det.get("risk"),
            trend_up=None if sma is None else c[-1] > sma,
            rel3=None if r3 is None else r3 - _ret(spy, 63),
            rel12=None if r12 is None else r12 - _ret(spy, 252),
            drawdown=c[-1] / max(c[-252:]) - 1 if c else None,
            url=f"https://freedom24.com/ideas/{i['url']}" if i.get("url") else "",
        ))
    return out
