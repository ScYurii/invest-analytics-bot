"""Weekly report: portfolio, risks, market, signals, hints. Plain text in Russian."""
from __future__ import annotations

import statistics
from collections import Counter
from dataclasses import dataclass, field
from datetime import date

from .backtest import FIXED, PER_SHARE
from .ideas import IdeaView, TrackRecord
from .portfolio import Lot, Position, Prices, yahoo_symbol
from .protection import Protection, status_line
from .protection import check as protection_check
from .protection import summary as protection_summary

INDICES = [("SPY", "S&P 500"), ("QQQ", "Nasdaq-100"), ("GLD", "Золото"),
           ("IEF", "Гособлигации 7-10 лет"), ("BIL", "Деньги (T-bills)")]
DAYS = {"1н": 5, "1м": 21, "3м": 63, "6м": 126, "12м": 252}
BACKUP_DAYS = 14       # hint when the last copy of the data is older than this
MAX_WEIGHT = 0.25      # hint when one position is above this share of the portfolio
LAG_12M = 0.15         # the sell rule: a stock trails SPY by more than this over 12 months


@dataclass
class Signals:
    price: float
    sma200: float
    rets: dict[str, float | None]
    drawdown: float     # from the 52-week high
    vol: float          # 20-day volatility, annualised


def signals(px: Prices, sym: str) -> Signals:
    _, v = px.series(sym)
    _, c = px.series(sym, "close")
    rets = {k: (v[-1] / v[-1 - n] - 1 if len(v) > n else None) for k, n in DAYS.items()}
    daily = [v[i] / v[i - 1] - 1 for i in range(len(v) - 20, len(v))]
    return Signals(
        price=c[-1],
        sma200=statistics.fmean(c[-200:]),
        rets=rets,
        drawdown=c[-1] / max(c[-252:]) - 1,
        vol=statistics.stdev(daily) * 252 ** 0.5,
    )


def trend_history(px: Prices, above: bool, horizon: int = 126) -> tuple[float, float, int]:
    """SPY return over the next `horizon` days on days when it was above/below its SMA200."""
    _, c = px.series("SPY", "close")
    _, v = px.series("SPY")
    out = []
    for i in range(200, len(c) - horizon):
        if (c[i] > statistics.fmean(c[i - 199:i + 1])) == above:
            out.append(v[i + horizon] / v[i] - 1)
    return statistics.median(out), sum(r > 0 for r in out) / len(out), len(out)


def backup_age(backup: dict | None) -> int | None:
    """Days since the last copy on the laptop, or None if there is none."""
    if not backup or not backup.get("last"):
        return None
    return (date.today() - date.fromisoformat(backup["last"][:10])).days


def spy_ret(px: Prices, days: int, curr: str) -> float:
    """SPY total return over the last `days` trading days, in USD or in EUR."""
    d, v = px.series("SPY")
    r = v[-1] / v[-1 - days]
    if curr == "EUR":
        r *= px.at("EURUSD=X", d[-1 - days], "close") / px.at("EURUSD=X", d[-1], "close")
    return r - 1


def price_chart(px: Prices, sym: str, own: list[Lot]) -> dict:
    """One year of closes with the 200-day average and the purchase days."""
    d, c = px.series(sym, "close")
    n = min(252, len(c) - 199) if len(c) > 199 else 0
    first = d[-n] if n else d[-1]
    return {
        "dates": d[-n:] if n else [],
        "close": [round(x, 2) for x in c[-n:]] if n else [],
        "sma": [round(statistics.fmean(c[i - 199:i + 1]), 2) for i in range(len(c) - n, len(c))],
        "buys": [(lot.bought, lot.price) for lot in own if lot.bought >= first],
    }


def rule_history(rule: dict | None) -> str:
    if not rule:
        return ""
    return (f"На {rule['ideas']} прошлых идеях Freedom24 в таких случаях переложить бумагу в S&P 500 было "
            f"выгоднее в {rule['switch_better']:.0%} случаев, в среднем на {rule['switch_gain'] * 100:+.0f} п.п.")


def spy_growth(px: Prices, a: str, b: str, curr: str) -> float:
    """How many times money in SPY grew from a to b, in the currency of the lot."""
    g = px.at("SPY", b) / px.at("SPY", a)
    if curr == "EUR":
        g *= px.at("EURUSD=X", a, "close") / px.at("EURUSD=X", b, "close")
    return g


def pct(x: float | None, sign: bool = True) -> str:
    return "—" if x is None else (f"{x:+.1%}" if sign else f"{x:.1%}")


@dataclass
class Holding:
    instr: str
    name: str
    qty: float
    price: float
    curr: str
    value_eur: float
    weight: float
    gain: float          # since purchase, with dividends
    spy: float           # SPY over the same time, same money
    sig: Signals
    rel3: float | None   # 3-month return minus SPY
    rel12: float | None
    sell_fee: float
    cost_eur: float      # what the shares held now cost
    profit_eur: float    # value + dividends - cost, before the sale fee
    divs_eur: float      # dividends received on the shares held now (gross)
    rule_fired: bool     # trails SPY by more than LAG_12M over 12 months
    chart: dict          # one year of prices, the 200-day average, purchases
    since: str           # date of the first purchase still held


@dataclass
class Snapshot:
    today: str
    total: float         # positions + cash, EUR
    stocks: float
    cash: float
    week: float          # change of the positions over a week (no deposits)
    spy_week: float
    usd_share: float
    usd_3m: float        # change of USD against EUR over 3 months
    holdings: list[Holding]
    spy: Signals
    above: bool
    trend_median: float
    trend_up_share: float
    trend_days: int
    long_vol: float
    strength: list[tuple[str, str, Signals]]
    hints: list[str]
    ideas: list[IdeaView]
    track: TrackRecord | None
    track_trend: dict[bool, TrackRecord | None]   # by the stock's trend on the idea day
    rule: dict | None                              # how the sell rule did on past ideas
    share_eur: dict[int, float]   # idea id -> one share in EUR
    backup: dict | None = None    # the last copy of the data on the laptop (backup.sh)
    candidates: list = field(default_factory=list)   # (Metrics, S&P 500 member, one share in EUR)
    cand_stats: dict | None = None                   # how the screen did since 2010
    protection: Protection | None = None             # S&P 500 against its 200-day average


def snapshot(px: Prices, positions: list[Position], cash: dict[str, float], lots: list[Lot],
             ideas: list[IdeaView] | None = None, track: TrackRecord | None = None,
             track_trend: dict[bool, TrackRecord | None] | None = None,
             rule: dict | None = None, backup: dict | None = None,
             candidates: list | None = None, cand_stats: dict | None = None) -> Snapshot:
    dates = px.series("SPY")[0]
    today, week_ago = dates[-1], dates[-6]
    spy_sig = signals(px, "SPY")
    hints: list[str] = []

    raw = []
    for p in positions:
        ys = yahoo_symbol(p.instr)
        own = [lot for lot in lots if lot.instr == p.instr and lot.sold is None]
        cost = sum(lot.qty * lot.price for lot in own)
        divs = sum(lot.qty * px.dividends(ys, lot.bought, today) for lot in own)
        gain = (p.qty * p.price + divs) / cost - 1 if cost else 0.0
        spy = sum(lot.qty * lot.price * spy_growth(px, lot.bought, today, lot.curr) for lot in own) / cost - 1
        value = px.eur(p.qty * p.price, p.curr, today)
        value_week = px.eur(p.qty * px.at(ys, week_ago, "close"), p.curr, week_ago)
        cost_eur = sum(px.eur(lot.qty * lot.price, lot.curr, lot.bought) for lot in own)
        raw.append((p, ys, value, value_week, gain, spy, own, cost_eur, px.eur(divs, p.curr, today)))
    stocks = sum(r[2] for r in raw)
    cash_eur = sum(px.eur(v, c, today) for c, v in cash.items())
    total = stocks + cash_eur

    holdings = []
    for p, ys, value, _, gain, spy, own, cost_eur, divs_eur in sorted(raw, key=lambda r: -r[2]):
        sig = signals(px, ys)
        # Against SPY in the currency of the stock, so a euro stock is not judged by the dollar
        rel3 = None if sig.rets["3м"] is None else sig.rets["3м"] - spy_ret(px, 63, p.curr)
        rel12 = None if sig.rets["12м"] is None else sig.rets["12м"] - spy_ret(px, 252, p.curr)
        holdings.append(Holding(
            p.instr, p.name, p.qty, p.price, p.curr, value, value / total, gain, spy, sig, rel3, rel12,
            FIXED + PER_SHARE * p.qty, cost_eur, value + divs_eur - cost_eur, divs_eur,
            rel12 is not None and rel12 < -LAG_12M, price_chart(px, ys, own),
            min(lot.bought for lot in own) if own else today))

    heavy = [h for h in holdings if h.weight > MAX_WEIGHT]
    if heavy:
        hints.append(f"⚠️ Концентрация: {', '.join(f'{h.instr} {h.weight:.0%}' for h in heavy)} — больше "
                     f"{MAX_WEIGHT:.0%} портфеля каждая, вместе {sum(h.weight for h in heavy):.0%}. "
                     f"Результат почти целиком зависит от {'этой бумаги' if len(heavy) == 1 else 'этих бумаг'}.")
    above = spy_sig.price > spy_sig.sma200
    if not above:
        hints.append("⚠️ S&P 500 ниже 200-дневной средней: в такие периоды исторически чаще бывают "
                     "затяжные падения. Повод проверить, комфортна ли доля акций.")
    for h in holdings:
        if h.rule_fired:
            hints.append(f"⚠️ {h.instr}: сработало правило — отстаёт от S&P 500 за 12 мес на {-h.rel12:.0%} "
                         f"(порог {LAG_12M:.0%}). {rule_history(rule)}")

    med, share_up, n = trend_history(px, above)
    v = px.series("SPY")[1]
    long_vol = statistics.stdev([v[i] / v[i - 1] - 1 for i in range(1, len(v))]) * 252 ** 0.5
    strength = sorted(((sym, name, signals(px, sym)) for sym, name in INDICES),
                      key=lambda x: -(x[2].rets["12м"] or -9))
    usd = sum(h.value_eur for h in holdings if h.curr == "USD") + px.eur(cash.get("USD", 0), "USD", today)
    fx_3m = px.at("EURUSD=X", dates[-64], "close") / px.at("EURUSD=X", today, "close") - 1
    prot = protection_check(px)
    if prot.level == "fired":
        fees = sum(h.sell_fee for h in holdings)
        hints.append(f"🔴 Защита от обвала: на конец месяца S&P 500 ниже 200-дневной средней. По правилу — выйти "
                     f"из акций в краткосрочные гособлигации до закрытия месяца выше средней. "
                     f"{protection_summary(prot)} Продать все бумаги стоило бы ≈ {fees:.0f} в комиссиях. "
                     f"Решение за вами.")
    elif prot.level == "warn":
        hints.append(f"🟡 S&P 500 в {prot.gap:+.1%} от 200-дневной средней: если месяц закроется ниже, сработает "
                     f"правило защиты от обвала.")
    days = backup_age(backup)
    if days is None or days > BACKUP_DAYS:
        hints.append("💾 Копии базы на ноутбуке нет" if days is None else
                     f"💾 Копия базы на ноутбуке старая: {days} дн. Запустите deploy/backup.sh на ноутбуке.")
    ideas = ideas or []
    share_eur = {i.id: px.eur(i.price, i.curr, today) for i in ideas if i.curr in ("USD", "EUR")}
    return Snapshot(
        today, total, stocks, cash_eur, stocks / sum(r[3] for r in raw) - 1,
        px.at("SPY", today) / px.at("SPY", week_ago) - 1, usd / total, fx_3m, holdings,
        spy_sig, above, med, share_up, n, long_vol, strength, hints, ideas, track, track_trend or {}, rule, share_eur,
        backup,
        [(m, member, px.eur(m.close, "USD", today)) for m, member in (candidates or [])],
        cand_stats,
        prot,
    )


def candidates_text(s: Snapshot) -> list[str]:
    out = ["", "🔭 Кандидаты для изучения — S&P 500: сила за 12 мес (без последнего) + восходящий тренд"]
    c = s.cand_stats
    if c:
        out.append(f"   Для справки: такой отбор с {c['since'][:4]} г. (топ-10, пересмотр раз в квартал) — "
                   f"{c['cagr']:+.0%}/год против {c['basket']:+.0%} у корзины тех же компаний и {c['spy']:+.0%} "
                   f"у S&P 500; комиссии при {c['account']:.0f} € ≈ {c['fees']:.1%}/год; хуже S&P 500 в "
                   f"{c['worse_years']} годах из {c['years']}. Проверка завышает результат: в сегодняшнем "
                   f"списке нет компаний, выбывших из индекса.")
    held = {h.instr.removesuffix(".US") for h in s.holdings}
    for k, (m, member, one) in enumerate(s.candidates, 1):
        mark = " — уже в портфеле" if m.symbol in held else ""
        if one > 0.10 * s.total:
            mark += " — 1 акция дороже 10 % портфеля"
        out.append(f"   {k:2}. {m.symbol:6} {member['name'][:28]:28} {member['sector'][:22]:22} сила {m.mom:+5.0%}, "
                   f"от макс. {m.drawdown:+4.0%}, 1 акция ≈ {one:.0f} € ({one / s.total:.1%}){mark}")
    pricey = [m.symbol for m, _, one in s.candidates if one > 0.10 * s.total]
    if pricey:
        out.append(f"   1 акция дороже 10 % портфеля: {len(pricey)} из {len(s.candidates)} — {', '.join(pricey)}")
    sectors = Counter(member["sector"] for _, member, _ in s.candidates)
    if sectors:
        top, n = sectors.most_common(1)[0]
        if n >= len(s.candidates) / 2:
            out.append(f"   ⚠️ {n} из {len(s.candidates)} — {top}: список сильных бумаг часто сбивается в одну тему, "
                       f"и она может развернуться вся сразу (так было в 2023 г.).")
    return out


def ideas_text(s: Snapshot) -> list[str]:
    out = ["", f"🆕 Идеи Freedom24 за неделю: {len(s.ideas)}"]
    if s.track:
        t = s.track
        out.append(f"   Для справки: из {t.n} прошлых идей средний итог {t.mean:+.0%} против {t.spy:+.0%} у S&P 500 "
                   f"за те же сроки; лучше индекса {t.beat:.0%}, цель достигнута в {t.hit:.0%}, в минусе {t.loss:.0%}.")
    for i in s.ideas:
        out.append("")
        out.append(f"• {i.ticker} — {i.company} ({i.date})")
        out.append(f"  Цена {i.price:g} {i.curr}, цель {i.target:g} ({i.upside:+.0%}) за {i.horizon}, риск: {i.risk or '—'}")
        trend = "—" if i.trend_up is None else ("↑ выше 200-дн. средней" if i.trend_up else "↓ ниже 200-дн. средней")
        out.append(f"  Тренд {trend}; против S&P 500: 3м {pct(i.rel3)}, 12м {pct(i.rel12)}; от макс. за год {pct(i.drawdown)}")
        similar = s.track_trend.get(i.trend_up) if i.trend_up is not None else None
        if similar:
            kind = "на растущие бумаги" if i.trend_up else "на бумаги в нисходящем тренде"
            out.append(f"  Похожие прошлые идеи ({kind}, {similar.n}): в среднем {similar.mean - similar.spy:+.0%} "
                       f"к S&P 500, лучше индекса {similar.beat:.0%}")
        if i.id in s.share_eur:
            one = s.share_eur[i.id]
            n10 = int(0.10 * s.total // one)
            out.append(f"  1 акция ≈ {one:.0f} € = {one / s.total:.1%} портфеля; на 10 % портфеля — {n10} шт, "
                       f"комиссия ≈ {FIXED + PER_SHARE * max(n10, 1):.2f}")
        out.append(f"  {i.url}")
    return out


def card_text(h: Holding, s: Snapshot) -> list[str]:
    trend = "↑ выше 200-дн. средней" if h.sig.price > h.sig.sma200 else "↓ ниже 200-дн. средней"
    if h.rel12 is None:
        rule = "правило: нет истории за 12 мес"
    elif h.rule_fired:
        rule = f"⚠️ правило сработало: отстаёт от S&P 500 за 12 мес на {-h.rel12:.0%} (порог {LAG_12M:.0%})"
        months = (date.fromisoformat(s.today) - date.fromisoformat(h.since)).days // 30
        if months < 12:
            rule += (f". Бумага у вас {months} мес — правило смотрит на 12 мес целиком, "
                     f"включая время до покупки")
    else:
        rule = f"✅ правило не сработало: до порога {(h.rel12 + LAG_12M) * 100:.0f} п.п."
    fee_eur = h.sell_fee * h.value_eur / (h.qty * h.price)
    return [
        f"• {h.instr} — {h.name}, {h.weight:.0%} портфеля",
        f"  Вложено {h.cost_eur:.0f} € → сейчас {h.value_eur:.0f} € ({h.profit_eur:+.0f} €, "
        f"{h.profit_eur / h.cost_eur:+.0%} в евро" + (f", дивиденды {h.divs_eur:.0f} €" if h.divs_eur >= 0.5 else "") + ")",
        f"  В {'долларах' if h.curr == 'USD' else 'евро' if h.curr == 'EUR' else h.curr}: {h.gain:+.1%}, "
        f"S&P 500 за тот же срок {h.spy:+.1%} ({h.gain - h.spy:+.1%})",
        f"  Тренд {trend}; против S&P 500: 3м {pct(h.rel3)}, 12м {pct(h.rel12)}; от макс. за год {pct(h.sig.drawdown)}",
        f"  {rule}",
        f"  Продать всё: комиссия {h.sell_fee:.2f} {h.curr}, прибыль после неё ≈ {h.profit_eur - fee_eur:+.0f} €",
    ]


def text(s: Snapshot) -> str:
    out = [f"📊 Отчёт по портфелю — данные на закрытие {s.today}", ""]
    out.append(f"💼 Портфель: {s.total:,.0f} €  (бумаги {s.stocks:,.0f} € + деньги {s.cash:,.0f} €)".replace(",", " "))
    out.append(f"   За неделю: {s.week:+.1%} (без учёта пополнений), S&P 500: {s.spy_week:+.1%}")
    out += ["", "Бумага      Доля  Цена       С покупки  S&P500 за тот же срок  Разница"]
    for h in s.holdings:
        out.append(f"{h.instr:10} {h.weight:5.0%}  {h.price:9.2f}  {h.gain:+8.1%}   {h.spy:+8.1%}"
                   f"              {h.gain - h.spy:+7.1%}")
    out.append(f"\nВ долларах: {s.usd_share:.0%} портфеля — курс USD/EUR влияет на результат в евро "
               f"(за 3 мес доллар к евро: {s.usd_3m:+.1%}).")

    out += ["", "🌍 Рынок"]
    out.append(f"S&P 500 {'выше' if s.above else 'ниже'} 200-дневной средней на "
               f"{abs(s.spy.price / s.spy.sma200 - 1):.1%} — {'восходящий тренд' if s.above else 'нисходящий тренд'}.")
    out.append(f"   В истории с 2005 г. в такой ситуации ({s.trend_days} дней) следующие 6 мес: медиана "
               f"{s.trend_median:+.1%}, рост в {s.trend_up_share:.0%} случаев.")
    calm = "спокойнее обычного" if s.spy.vol < s.long_vol else "неспокойнее обычного"
    out.append(f"   Колебания S&P 500 за месяц: {s.spy.vol:.0%} годовых — {calm} (среднее с 2005 г. {s.long_vol:.0%}).")
    if s.protection:
        out.append("   " + status_line(s.protection))
    out.append("\nСила за 12 месяцев (с дивидендами):")
    for k, (_, name, sig) in enumerate(s.strength, 1):
        out.append(f"   {k}. {name:22} {pct(sig.rets['12м'])}   (3м {pct(sig.rets['3м'])})")

    out += ["", "📋 По бумагам"]
    for h in s.holdings:
        out += [""] + card_text(h, s)

    if s.ideas or s.track:
        out += ideas_text(s)
    if s.candidates:
        out += candidates_text(s)
    out += ["", "💡 Пора проверить"]
    out += s.hints or ["Ничего не требует внимания."]
    days = backup_age(s.backup)
    if days is not None:
        out += ["", f"💾 Копия базы на ноутбуке: {s.backup['last'][:10]} ({days} дн. назад)"]
    out += ["", "Отчёт — повод подумать, а не совет. Решение за вами."]
    return "\n".join(out)


def build(px: Prices, positions: list[Position], cash: dict[str, float], lots: list[Lot]) -> str:
    return text(snapshot(px, positions, cash, lots))
