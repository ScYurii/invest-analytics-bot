"""A short plain-language summary of the weekly report, written by Claude.

The report text (and last week's, for comparison) goes to the Anthropic API.
No keys or account numbers are in the report; holdings and sums are.
Optional: without ~/.config/invest-bot/anthropic.ini the report goes out as before.
"""
from __future__ import annotations

import configparser
import hashlib
import logging
import os
import time
from pathlib import Path

import requests

CONFIG = os.environ.get("INVBOT_ANTHROPIC_INI", os.path.expanduser("~/.config/invest-bot/anthropic.ini"))
URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = "claude-opus-5-5"

SYSTEM = """Ты помогаешь частному инвестору быстро понять еженедельный отчёт о его портфеле.
Пиши по-русски, коротко и просто: 5–8 пунктов, каждый в одну-две строки, без вступления.

Порядок:
1. Что изменилось за неделю (портфель против S&P 500; если дан прошлый отчёт — что поменялось
   по сравнению с ним: стоимость, сработавшие правила, новые подсказки).
2. Что требует внимания: сработавшие правила, концентрация, риски — и почему это важно.
3. Новые идеи Freedom24 и кандидаты: что в них заметного (тренд, сила, концентрация в одной теме),
   с учётом приведённой в отчёте статистики того, как такие идеи срабатывали в прошлом.
4. Обстановка на рынке одной строкой.

Правила:
- Используй только факты и цифры из отчёта. Ничего не придумывай: ни новостей, ни причин движения цен,
  ни прогнозов. Если чего-то нет в отчёте — не упоминай.
- Не считай сам: не пересчитывай количество строк, не складывай доли и суммы. Бери только готовые
  числа из отчёта; если нужного числа в отчёте нет — опиши без числа.
- Не давай советов купить, продать или держать. Пиши наблюдения: «правило сработало», «доля выросла
  до…», «бумага отстаёт от индекса на…». Решения принимает человек.
- Если всё спокойно и ничего не требует внимания — так и скажи коротко.
- Без Markdown-таблиц и заголовков; можно эмодзи в начале пунктов."""

log = logging.getLogger(__name__)


def configured(config: str = CONFIG) -> bool:
    return os.path.isfile(config)


def _load(config: str) -> tuple[str, str]:
    if os.stat(config).st_mode & 0o077:
        raise RuntimeError(f"{config} is readable by others, chmod 600")
    c = configparser.ConfigParser()
    c.read(config)
    sec = c["anthropic"]
    return sec["key"].strip(), sec.get("model", DEFAULT_MODEL).strip()


def summarize(report: str, previous: str | None, config: str = CONFIG) -> str:
    key, model = _load(config)
    user = f"Отчёт этой недели:\n\n{report}"
    if previous:
        user += f"\n\n---\nОтчёт прошлой недели (для сравнения):\n\n{previous}"
    try:
        r = requests.post(URL, timeout=180, headers={
            "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json",
        }, json={
            "model": model, "max_tokens": 1500, "system": SYSTEM,
            "messages": [{"role": "user", "content": user}],
        })
    except requests.RequestException as e:
        raise RuntimeError(f"Anthropic API: {type(e).__name__}") from None
    if r.status_code != 200:
        # The error body has a type and a message, never the key
        raise RuntimeError(f"Anthropic API: HTTP {r.status_code} {r.text[:300]}")
    return "".join(b.get("text", "") for b in r.json().get("content", [])).strip()


def for_report(reports: Path, day: str, report: str, reuse: int = 3600) -> str | None:
    """The summary for this report: cached in reports/<day>.summary.txt and reused
    while the report text is the same, or for `reuse` seconds (the dashboard and
    the Telegram report are built a minute apart and live prices may move in
    between). None if not configured or the API failed: the report goes out
    without it."""
    if not configured():
        return None
    digest = hashlib.sha256(report.encode()).hexdigest()[:16]
    f = reports / f"{day}.summary.txt"
    if f.exists():
        head, _, body = f.read_text().partition("\n")
        if head == digest or time.time() - f.stat().st_mtime < reuse:
            return body
    older = sorted(p for p in reports.glob("*.txt") if not p.name.endswith(".summary.txt") and p.stem < day)
    previous = older[-1].read_text() if older else None
    try:
        text = summarize(report, previous)
    except (RuntimeError, OSError, KeyError) as e:
        log.warning("summary skipped: %s", e)
        return None
    f.write_text(f"{digest}\n{text}")
    return text
