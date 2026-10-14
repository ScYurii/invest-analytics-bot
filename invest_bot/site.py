"""Static HTML dashboard: portfolio, Freedom24 ideas, market, report archive.

Pages are rebuilt from scratch into a new directory and swapped in at the end,
so a failed build leaves the previous version in place.
"""
from __future__ import annotations

import csv
import html
import json
import shutil
import statistics
from datetime import datetime
from pathlib import Path

from .report import LAG_12M, Holding, Snapshot, card_text, pct

STATIC = Path(__file__).resolve().parent / "static"

CSS = """
:root{--bg:#f6f7f9;--card:#fff;--fg:#1c1f24;--muted:#6b7280;--line:#e5e7eb;--up:#0a8f4f;--down:#c62828;--accent:#2457d6}
@media (prefers-color-scheme:dark){:root{--bg:#111418;--card:#1a1e24;--fg:#e6e8eb;--muted:#9aa1ab;--line:#2a3038;--up:#3ecf8e;--down:#ff6b6b;--accent:#6c9cff}}
*{box-sizing:border-box}a{color:var(--accent)}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
header{background:var(--card);border-bottom:1px solid var(--line);padding:10px 16px;display:flex;gap:16px;align-items:center;flex-wrap:wrap}
header b{margin-right:8px}nav a{color:var(--muted);text-decoration:none;margin-right:14px}nav a.on{color:var(--accent);font-weight:600}
main{max-width:1100px;margin:0 auto;padding:16px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-bottom:16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.card .k{color:var(--muted);font-size:13px}.card .v{font-size:22px;font-weight:600}
section{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px;margin-bottom:16px}
h2{font-size:17px;margin:0 0 10px}.muted{color:var(--muted);font-size:13px}
.tw{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:14px}
th,td{padding:6px 8px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}
th:first-child,td:first-child{text-align:left}th{color:var(--muted);font-weight:500;cursor:pointer}
.up{color:var(--up)}.down{color:var(--down)}ul.hints{margin:0;padding-left:18px}
pre{white-space:pre-wrap;font-size:13px}.filters button{margin:0 6px 8px 0;padding:4px 10px;border:1px solid var(--line);
background:var(--card);color:var(--fg);border-radius:6px;cursor:pointer}.filters button.on{border-color:var(--accent);color:var(--accent)}
canvas{max-height:340px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:12px;margin-bottom:16px}
.hc{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.hc h3{margin:0 0 4px;font-size:16px}.hc .row{display:flex;justify-content:space-between;font-size:14px;padding:2px 0}
.hc .row span:first-child{color:var(--muted)}.badge{border-radius:6px;padding:6px 8px;margin:8px 0;font-size:13px}
.badge.ok{background:color-mix(in srgb,var(--up) 14%,transparent)}.badge.warn{background:color-mix(in srgb,var(--down) 16%,transparent)}
.hc canvas{max-height:140px}
"""

SORT_JS = """
document.querySelectorAll('table.sort th').forEach((th,i)=>th.onclick=()=>{
 const tb=th.closest('table').tBodies[0],rows=[...tb.rows],asc=th.dataset.asc!=='1';th.dataset.asc=asc?'1':'0';
 const v=r=>{const t=r.cells[i].dataset.v??r.cells[i].textContent;const n=parseFloat(t);return isNaN(n)?t:n};
 rows.sort((a,b)=>{const x=v(a),y=v(b);return (x>y?1:x<y?-1:0)*(asc?1:-1)});rows.forEach(r=>tb.appendChild(r))});
"""

PAGES = [("index.html", "Портфель"), ("ideas.html", "Идеи Freedom24"), ("candidates.html", "Кандидаты"),
         ("market.html", "Рынок"), ("reports.html", "Отчёты")]


def e(x) -> str:
    return html.escape(str(x))


def money(x: float, digits: int = 0) -> str:
    """1234567.8 -> '1 234 568' (thin spaces between thousands)."""
    return f"{x:,.{digits}f}".replace(",", "\u202f")


def cls(x: float | None) -> str:
    return "" if x is None else ("up" if x > 0 else "down" if x < 0 else "")


def num(x: float | None, fmt: str = "pct") -> str:
    """A table cell with the raw value for sorting."""
    if x is None:
        return '<td data-v="-999">—</td>'
    text = pct(x) if fmt == "pct" else f"{x:{fmt}}"
    return f'<td class="{cls(x) if fmt == "pct" else ""}" data-v="{x:.6f}">{text}</td>'


def page(name: str, title: str, body: str, updated: str, charts: bool = False) -> str:
    nav = "".join(f'<a href="{f}" class="{"on" if f == name else ""}">{t}</a>' for f, t in PAGES)
    js = '<script src="chart.umd.min.js"></script>' if charts else ""
    return f"""<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(title)} — портфель</title>
<style>{CSS}</style>{js}</head><body><header><b>📊 Портфель</b><nav>{nav}</nav>
<span class="muted">обновлено {e(updated)}</span></header><main>{body}</main>
<script>{SORT_JS}</script></body></html>"""


def line_chart(cid: str, labels: list[str], datasets: list[tuple[str, list, str]], percent: bool = False) -> str:
    ds = [{"label": n, "data": d, "borderColor": c, "backgroundColor": c, "pointRadius": 0,
           "borderWidth": 2, "tension": 0.1} for n, d, c in datasets]
    fmt = "v=>v.toFixed(0)+'%'" if percent else "v=>v.toLocaleString('ru-RU')+' €'"
    return f"""<canvas id="{cid}"></canvas><script>new Chart(document.getElementById('{cid}'),{{type:'line',
data:{{labels:{json.dumps(labels)},datasets:{json.dumps(ds)}}},options:{{animation:false,interaction:{{mode:'index',intersect:false}},
scales:{{x:{{ticks:{{maxTicksLimit:8}}}},y:{{ticks:{{callback:{fmt}}}}}}}}}}});</script>"""


# --- Pages ---------------------------------------------------------------------

def holding_card(h: Holding, s: Snapshot, k: int) -> str:
    lines = card_text(h, s)
    rule_line = next(x for x in lines if "правило" in x).strip()
    warn = h.rule_fired
    c = h.chart
    chart = ""
    if c["dates"]:
        buys = [{"x": d, "y": p} for d, p in c["buys"]]
        ds = [{"label": "Цена", "data": c["close"], "borderColor": "#2457d6", "pointRadius": 0, "borderWidth": 2},
              {"label": "200-дн. средняя", "data": c["sma"], "borderColor": "#e08a00", "pointRadius": 0, "borderWidth": 1.5},
              {"label": "Покупки", "type": "scatter", "data": buys, "backgroundColor": "#0a8f4f", "pointRadius": 5}]
        chart = (f"<canvas id='h{k}'></canvas><script>new Chart(document.getElementById('h{k}'),{{type:'line',"
                 f"data:{{labels:{json.dumps(c['dates'])},datasets:{json.dumps(ds)}}},options:{{animation:false,"
                 f"plugins:{{legend:{{display:false}}}},interaction:{{mode:'index',intersect:false}},"
                 f"scales:{{x:{{display:false}},y:{{ticks:{{maxTicksLimit:4}}}}}}}}}});</script>")
    trend = "↑ выше 200-дн. средней" if h.sig.price > h.sig.sma200 else "↓ ниже 200-дн. средней"
    fee_eur = h.sell_fee * h.value_eur / (h.qty * h.price)
    cur = "долларах" if h.curr == "USD" else "евро" if h.curr == "EUR" else h.curr
    rows = [
        ("Вложено → сейчас", f"{money(h.cost_eur)} € → {money(h.value_eur)} €"),
        ("Доход в евро", f"<b class='{cls(h.profit_eur)}'>{h.profit_eur:+.0f} € ({h.profit_eur / h.cost_eur:+.0%})</b>"
         + (f" <span class='muted'>вкл. дивиденды {h.divs_eur:.0f} €</span>" if h.divs_eur >= 0.5 else "")),
        (f"В {cur} / S&amp;P 500", f"<span class='{cls(h.gain)}'>{pct(h.gain)}</span> / {pct(h.spy)} "
         f"(<span class='{cls(h.gain - h.spy)}'>{pct(h.gain - h.spy)}</span>)"),
        ("Тренд", trend),
        ("Против S&amp;P 500: 3м / 12м", f"<span class='{cls(h.rel3)}'>{pct(h.rel3)}</span> / "
         f"<span class='{cls(h.rel12)}'>{pct(h.rel12)}</span>"),
        ("От максимума за год", f"<span class='{cls(h.sig.drawdown)}'>{pct(h.sig.drawdown)}</span>"),
        ("Продать всё", f"комиссия {h.sell_fee:.2f} {e(h.curr)}, прибыль после ≈ {h.profit_eur - fee_eur:+.0f} €"),
    ]
    hist = ""
    if warn and s.rule:
        hist = (f"<br><span class='muted'>На {s.rule['ideas']} прошлых идеях Freedom24 в таких случаях переложить "
                f"бумагу в S&amp;P 500 было выгоднее в {s.rule['switch_better']:.0%} случаев, в среднем на "
                f"{s.rule['switch_gain'] * 100:+.0f} п.п. Решение за вами.</span>")
    return (f"<div class='hc'><h3>{e(h.instr)} <span class='muted'>{e(h.name)} · {h.weight:.0%} портфеля · "
            f"{h.qty:g} шт по {money(h.price, 2)} {e(h.curr)}</span></h3>{chart}"
            + "".join(f"<div class='row'><span>{a}</span><span>{b}</span></div>" for a, b in rows)
            + f"<div class='badge {'warn' if warn else 'ok'}'>{e(rule_line)}{hist}</div></div>")


def portfolio_page(s: Snapshot, hist: dict) -> str:
    gain = hist["value"][-1] / hist["spy"][-1] - 1 if hist["spy"][-1] else 0
    cards = f"""<div class="cards">
<div class="card"><div class="k">Портфель</div><div class="v">{money(s.total)} €</div><div class="muted">бумаги {money(s.stocks)} € + деньги {money(s.cash)} €</div></div>
<div class="card"><div class="k">За неделю</div><div class="v {cls(s.week)}">{pct(s.week)}</div><div class="muted">S&amp;P 500: {pct(s.spy_week)}</div></div>
<div class="card"><div class="k">Против тех же денег в S&amp;P 500</div><div class="v {cls(gain)}">{pct(gain)}</div><div class="muted">{money(hist['value'][-1])} € против {money(hist['spy'][-1])} €</div></div>
<div class="card"><div class="k">В долларах</div><div class="v">{s.usd_share:.0%}</div><div class="muted">USD к EUR за 3 мес: {pct(s.usd_3m)}</div></div>
</div>"""
    rows = "".join(
        f"<tr><td><b>{e(h.instr)}</b> <span class='muted'>{e(h.name)}</span></td>{num(h.weight * 100, '.0f')}"
        f"<td>{h.qty:g}</td><td>{money(h.price, 2)} {e(h.curr)}</td><td data-v='{h.value_eur:.2f}'>{money(h.value_eur)} €</td>"
        f"{num(h.gain)}{num(h.spy)}{num(h.gain - h.spy)}"
        f"<td>{'↑' if h.sig.price > h.sig.sma200 else '↓'}</td>{num(h.rel3)}{num(h.rel12)}{num(h.sig.drawdown)}"
        f"<td data-v='{h.sell_fee:.2f}'>{h.sell_fee:.2f} ({h.sell_fee / (h.qty * h.price):.2%})</td></tr>"
        for h in s.holdings)
    table = f"""<section><h2>Сводная таблица</h2><div class="tw"><table class="sort"><thead><tr>
<th>Бумага</th><th>Доля %</th><th>Шт</th><th>Цена</th><th>Стоимость</th><th>С покупки</th><th>S&amp;P 500 за тот же срок</th>
<th>Разница</th><th>Тренд</th><th>3м vs SPY</th><th>12м vs SPY</th><th>От макс. 52н</th><th>Комиссия продажи</th>
</tr></thead><tbody>{rows}</tbody></table></div>
<p class="muted">«С покупки» — с дивидендами, по каждой покупке отдельно. «Тренд» — цена выше (↑) или ниже (↓) 200-дневной средней.</p></section>"""
    hints = "".join(f"<li>{e(h)}</li>" for h in s.hints) or "<li>Ничего не требует внимания.</li>"
    chart = line_chart("hist", hist["dates"], [
        ("Портфель", hist["value"], "#2457d6"), ("Те же деньги в S&P 500", hist["spy"], "#e08a00"),
        ("Вложено", hist["cost"], "#9aa1ab")])
    grid = ("<h2 style='margin:4px 0 10px'>Бумаги</h2><div class='grid'>"
            + "".join(holding_card(h, s, k) for k, h in enumerate(s.holdings)) + "</div>"
            + f"<p class='muted'>Правило: бумага отстаёт от S&amp;P 500 больше чем на {LAG_12M:.0%} за 12 месяцев "
            f"(для евро-бумаг — от S&amp;P 500 в евро). Это сигнал правила, а не совет; график — цена за год, "
            f"оранжевая — 200-дневная средняя, зелёные точки — ваши покупки.</p>")
    return (cards + f"<section><h2>Пора проверить</h2><ul class='hints'>{hints}</ul></section>" + grid
            + f"<section><h2>Стоимость вложенного (EUR)</h2>{chart}<p class='muted'>Синяя — ваши бумаги; оранжевая — "
            f"если бы каждую покупку и продажу делали в S&amp;P 500 (SPY) на те же суммы в те же дни; серая — "
            f"сколько вложено в бумаги, которые сейчас в портфеле. Деньги на счёте не учитываются.</p></section>"
            + table
            + (f"<p class='muted'>💾 Копия базы на ноутбуке: {e(s.backup['last'][:16].replace('T', ' '))}, "
               f"{e(s.backup.get('file', ''))}</p>" if s.backup else ""))


def protection_block(s: Snapshot) -> str:
    p = s.protection
    if not p:
        return ""
    names = {"helped": "спасло", "false alarm": "ложная тревога", "even": "≈ без разницы"}
    rows = "".join(
        f"<tr><td>{e(x.out)}</td><td>{e(x.back or 'ещё вне рынка')}</td>{num(x.spy)}{num(x.bil)}{num(x.worst)}"
        f"<td class='{'up' if x.verdict == 'helped' else 'down' if x.verdict == 'false alarm' else ''}'>"
        f"{names[x.verdict]}</td></tr>" for x in reversed(p.signals))
    from .protection import status_line, summary
    return f"""<section><h2>🛡️ Защита от обвала</h2><p><b>{e(status_line(p))}</b></p>
<p>Правило: если S&amp;P 500 закрывает месяц ниже своей 200-дневной средней — выйти из акций в краткосрочные
гособлигации (BIL), вернуться после месяца выше средней. {e(summary(p))}</p>
<div class="tw"><table><thead><tr><th>Выход</th><th>Возврат</th><th>S&amp;P 500 за это время</th><th>Гособлигации</th>
<th>Худшее падение после выхода</th><th>Итог</th></tr></thead><tbody>{rows}</tbody></table></div>
<p class="muted">Страховка от редкого затяжного обвала: чаще всего сигнал оказывался ложной тревогой, и возврат
был дороже выхода. Подсказка, не совет.</p></section>"""


def market_page(s: Snapshot, spy: tuple[list[str], list[float]]) -> str:
    dates, close = spy
    n = 504  # two years
    sma = [statistics.fmean(close[i - 199:i + 1]) for i in range(len(close) - n, len(close))]
    chart = line_chart("spy", dates[-n:], [("S&P 500 (SPY)", [round(x, 2) for x in close[-n:]], "#2457d6"),
                                           ("200-дневная средняя", [round(x, 2) for x in sma], "#e08a00")])
    chart = chart.replace("+' €'", "+' $'")
    rows = "".join(f"<tr><td>{k}. {e(name)}</td>{num(sig.rets['12м'])}{num(sig.rets['6м'])}{num(sig.rets['3м'])}"
                   f"{num(sig.rets['1м'])}{num(sig.drawdown)}</tr>"
                   for k, (_, name, sig) in enumerate(s.strength, 1))
    calm = "спокойнее обычного" if s.spy.vol < s.long_vol else "неспокойнее обычного"
    return f"""<div class="cards">
<div class="card"><div class="k">Тренд S&amp;P 500</div><div class="v {'up' if s.above else 'down'}">{'восходящий' if s.above else 'нисходящий'}</div>
<div class="muted">{'выше' if s.above else 'ниже'} 200-дневной средней на {abs(s.spy.price / s.spy.sma200 - 1):.1%}</div></div>
<div class="card"><div class="k">Что бывало дальше (6 мес)</div><div class="v">{pct(s.trend_median)}</div>
<div class="muted">медиана; рост в {s.trend_up_share:.0%} из {s.trend_days} похожих дней с 2005 г.</div></div>
<div class="card"><div class="k">Колебания за месяц</div><div class="v">{s.spy.vol:.0%}</div><div class="muted">{calm} (среднее {s.long_vol:.0%})</div></div>
</div>{protection_block(s)}<section><h2>S&amp;P 500 за 2 года</h2>{chart}</section>
<section><h2>Сила активов (с дивидендами)</h2><div class="tw"><table class="sort"><thead><tr><th>Актив</th><th>12 мес</th>
<th>6 мес</th><th>3 мес</th><th>1 мес</th><th>От макс. 52н</th></tr></thead><tbody>{rows}</tbody></table></div>
<p class="muted">Отсортировано по 12 месяцам. Исторически сильный за год актив чаще остаётся сильным ещё несколько месяцев, но гарантий нет.</p></section>"""


def new_ideas(s: Snapshot) -> str:
    if not s.ideas:
        return "<section><h2>Новые идеи за неделю</h2><p>Новых идей нет.</p></section>"
    rows = []
    for i in s.ideas:
        trend = "—" if i.trend_up is None else ("↑" if i.trend_up else "↓")
        similar = s.track_trend.get(i.trend_up) if i.trend_up is not None else None
        sim = (f"{num(similar.mean - similar.spy)}<td>{similar.beat:.0%}</td>" if similar
               else "<td>—</td><td>—</td>")
        one = s.share_eur.get(i.id)
        size = f"<td>{one:.0f} € ({one / s.total:.1%})</td>" if one else "<td>—</td>"
        rows.append(f"<tr><td><a href='{e(i.url)}' target='_blank' rel='noopener'><b>{e(i.ticker)}</b></a> "
                    f"<span class='muted'>{e(i.company)}</span></td><td>{e(i.date)}</td>"
                    f"<td>{i.price:g} {e(i.curr)}</td>{num(i.upside)}<td>{e(i.horizon)}</td><td>{e(i.risk or '—')}</td>"
                    f"<td>{trend}</td>{num(i.rel3)}{num(i.rel12)}{num(i.drawdown)}{sim}{size}</tr>")
    return f"""<section><h2>Новые идеи за неделю</h2><div class="tw"><table class="sort"><thead><tr>
<th>Бумага</th><th>Дата</th><th>Цена</th><th>До цели</th><th>Срок</th><th>Риск</th><th>Тренд</th><th>3м vs SPY</th>
<th>12м vs SPY</th><th>От макс. 52н</th><th>Похожие идеи к S&amp;P</th><th>Похожие лучше S&amp;P</th><th>1 акция</th>
</tr></thead><tbody>{''.join(rows)}</tbody></table></div>
<p class="muted">«Похожие идеи» — прошлые закрытые идеи на бумаги в том же тренде (выше или ниже 200-дневной средней
в день идеи): насколько в среднем они отстали или обогнали S&amp;P 500 и какая доля обогнала.</p></section>"""


def ideas_page(ideas_dir: Path, s: Snapshot) -> str:
    f = ideas_dir / "results.csv"
    if not f.exists():
        return new_ideas(s) + "<section><h2>Идеи Freedom24</h2><p>Анализ прошлых идей ещё не готов.</p></section>"
    rows = list(csv.DictReader(f.open()))
    for r in rows:
        for k in ("ret", "spy", "excess", "target_pct"):
            r[k] = float(r[k])
        r["hit"] = r["hit"] == "True"

    def stats(label: str, rs: list[dict]) -> str:
        if not rs:
            return ""
        ex = [r["excess"] for r in rs]
        return (f"<tr><td>{e(label)}</td><td>{len(rs)}</td>{num(statistics.fmean(r['ret'] for r in rs))}"
                f"{num(statistics.median(r['ret'] for r in rs))}{num(statistics.fmean(r['spy'] for r in rs))}"
                f"{num(statistics.fmean(ex))}<td>{sum(x > 0 for x in ex) / len(rs):.0%}</td>"
                f"<td>{sum(r['hit'] for r in rs) / len(rs):.0%}</td><td>{sum(r['ret'] < 0 for r in rs) / len(rs):.0%}</td></tr>")

    closed = [r for r in rows if r["status"].startswith("closed")]
    opened = [r for r in rows if r["status"].startswith("open")]
    groups = [stats("Все закрытые", closed), stats("Открытые (на сегодня)", opened)]
    groups += [stats("Закрытые, бумага росла (↑)", [r for r in closed if r.get("trend_up") == "True"]),
               stats("Закрытые, бумага падала (↓)", [r for r in closed if r.get("trend_up") == "False"])]
    groups += [stats(f"Закрытые {y} г.", [r for r in closed if r["date"][:4] == y])
               for y in sorted({r["date"][:4] for r in closed})]
    summary = f"""<section><h2>Как идеи сработали против S&amp;P 500</h2><div class="tw"><table><thead><tr><th>Группа</th><th>Идей</th>
<th>Средний итог</th><th>Медиана</th><th>S&amp;P 500</th><th>Разница</th><th>Лучше S&amp;P</th><th>Цель достигнута</th>
<th>В минусе</th></tr></thead><tbody>{''.join(groups)}</tbody></table></div>
<p class="muted">Итог — цена в конце срока идеи (или в последний день торгов, если бумага ушла с биржи) против цены
перед публикацией, без дивидендов; S&amp;P 500 за те же даты тоже без дивидендов. «Цель достигнута» — цена хотя бы раз
касалась цели в течение срока.</p></section>"""

    def row(r: dict) -> str:
        progress = r["ret"] / r["target_pct"] if r["target_pct"] > 0 else 0
        return (f"<tr data-s='{e(r['status'].split(',')[0])}'><td><b>{e(r['ticker'])}</b> <span class='muted'>"
                f"{e(r['title'][:70])}</span></td><td>{e(r['date'])}</td><td>{e(r['status'])}</td>"
                f"{num(r['target_pct'])}{num(r['ret'])}{num(r['spy'])}{num(r['excess'])}"
                f"<td data-v='{progress:.4f}'>{'✅' if r['hit'] else f'{progress:.0%}'}</td>"
                f"<td>{e(r['risk'])}</td><td>{e(r['author'])}</td></tr>")

    table = f"""<section><h2>Все идеи</h2><div class="filters">
<button class="on" onclick="flt(this,'')">Все</button><button onclick="flt(this,'open')">Открытые</button>
<button onclick="flt(this,'closed')">Закрытые</button></div><div class="tw"><table class="sort" id="ideas"><thead><tr>
<th>Бумага</th><th>Дата</th><th>Статус</th><th>Цель</th><th>Итог</th><th>S&amp;P 500</th><th>Разница</th>
<th>Путь к цели</th><th>Риск</th><th>Автор</th></tr></thead><tbody>
{''.join(row(r) for r in sorted(rows, key=lambda r: r['date'], reverse=True))}</tbody></table></div></section>
<script>function flt(b,s){{document.querySelectorAll('.filters button').forEach(x=>x.classList.remove('on'));b.classList.add('on');
document.querySelectorAll('#ideas tbody tr').forEach(r=>r.style.display=!s||r.dataset.s===s?'':'none')}}</script>"""
    return new_ideas(s) + summary + table


def candidates_page(s: Snapshot) -> str:
    if not s.candidates:
        return "<section><h2>Кандидаты</h2><p>Список ещё не собран: нет цен по S&amp;P 500.</p></section>"
    held = {h.instr.removesuffix(".US") for h in s.holdings}
    rows = []
    for k, (m, member, one) in enumerate(s.candidates, 1):
        note = []
        if m.symbol in held:
            note.append("уже в портфеле")
        if one > 0.10 * s.total:
            note.append("1 акция дороже 10 % портфеля")
        rows.append(f"<tr><td>{k}. <b>{e(m.symbol)}</b> <span class='muted'>{e(member['name'])}</span></td>"
                    f"<td>{e(member['sector'])}</td>{num(m.mom)}{num(m.r1m)}{num(m.drawdown)}"
                    f"<td>{money(m.close, 2)} $</td><td data-v='{one:.2f}'>{one:.0f} € ({one / s.total:.1%})</td>"
                    f"<td>{e(', '.join(note))}</td></tr>")
    c = s.cand_stats
    track = ""
    if c:
        track = (f"<div class='cards'><div class='card'><div class='k'>Отбор с {c['since'][:4]} г.</div>"
                 f"<div class='v up'>{c['cagr']:+.0%}/год</div><div class='muted'>топ-10, пересмотр раз в квартал</div></div>"
                 f"<div class='card'><div class='k'>Корзина тех же компаний</div><div class='v'>{c['basket']:+.0%}/год</div>"
                 f"<div class='muted'>S&amp;P 500: {c['spy']:+.0%}/год</div></div>"
                 f"<div class='card'><div class='k'>Комиссии при {c['account']:.0f} €</div><div class='v'>{c['fees']:.1%}/год</div>"
                 f"<div class='muted'>хуже S&amp;P 500 в {c['worse_years']} годах из {c['years']}</div></div></div>")
    return track + f"""<section><h2>Кандидаты для изучения</h2><div class="tw"><table class="sort"><thead><tr>
<th>Компания</th><th>Сектор</th><th>Сила 12–1 мес</th><th>За месяц</th><th>От макс. 52н</th><th>Цена</th><th>1 акция</th><th></th>
</tr></thead><tbody>{''.join(rows)}</tbody></table></div>
<p class="muted">Отбор из S&amp;P 500: самые сильные за 12 месяцев (без последнего) среди бумаг выше своей 200-дневной
средней. Проверка на истории завышает результат: в сегодняшнем списке S&amp;P 500 нет компаний, которые выбыли из
индекса (в том числе после обвала). Сильные бумаги часто сбиваются в одну тему — она может развернуться вся сразу,
как в 2023 г. Это повод изучить компанию, не совет купить.</p></section>"""


def summary_block(summary: str | None) -> str:
    if not summary:
        return ""
    return (f"<section><h2>🧠 Кратко за неделю</h2><pre style='font:inherit'>{e(summary)}</pre>"
            f"<p class='muted'>Написано Claude только по цифрам отчёта; это наблюдения, не советы.</p></section>")


def reports_page(reports_dir: Path, out: Path) -> str:
    files = sorted((f for f in reports_dir.glob("*.txt") if not f.name.endswith(".summary.txt")), reverse=True)
    (out / "reports").mkdir(exist_ok=True)
    items = []
    for f in files:
        (out / "reports" / f"{f.stem}.html").write_text(
            f"<!doctype html><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>Отчёт {f.stem}</title><style>{CSS}</style><main><p><a href='../reports.html'>← все отчёты</a></p>"
            + (f"<section><h2>🧠 Кратко</h2><pre style='font:inherit'>{e(sm.read_text().partition(chr(10))[2])}</pre></section>"
               if (sm := f.with_name(f.stem + ".summary.txt")).exists() else "")
            + f"<section><pre>{e(f.read_text())}</pre></section></main>")
        items.append(f"<li><a href='reports/{f.stem}.html'>{f.stem}</a></li>")
    return f"<section><h2>Недельные отчёты</h2><ul>{''.join(items) or '<li>Пока нет.</li>'}</ul></section>"


def build(out: Path, s: Snapshot, hist: dict, spy: tuple, ideas_dir: Path, reports_dir: Path,
          summary: str | None = None) -> None:
    tmp = out.with_name(out.name + ".new")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    shutil.copy(STATIC / "chart.umd.min.js", tmp)
    updated = f"{datetime.now():%Y-%m-%d %H:%M}, данные на {s.today}"
    pages = {
        "index.html": ("Портфель", summary_block(summary) + portfolio_page(s, hist), True),
        "ideas.html": ("Идеи Freedom24", ideas_page(ideas_dir, s), False),
        "candidates.html": ("Кандидаты", candidates_page(s), False),
        "market.html": ("Рынок", market_page(s, spy), True),
        "reports.html": ("Отчёты", reports_page(reports_dir, tmp), False),
    }
    for name, (title, body, charts) in pages.items():
        (tmp / name).write_text(page(name, title, body, updated, charts))
    old = out.with_name(out.name + ".old")
    shutil.rmtree(old, ignore_errors=True)
    if out.exists():
        out.rename(old)
    tmp.rename(out)
    shutil.rmtree(old, ignore_errors=True)
