"""The bot's main loop in the container.

- Every Saturday at 09:00 Europe/Zagreb: refresh ideas, prices and statistics,
  build the dashboard, send the report. A run missed while the phone was off is
  done at the next start.
- Telegram commands from the owner's chat: /report (fresh report now), /help.
- A failed run is reported to Telegram.
- Health for Docker: data/heartbeat is touched on every loop (at most ~70 s
  apart), data/busy exists while a job runs. The updater on the phone does not
  restart the bot while data/busy exists.

Every step is a script run as a subprocess, the same as on the laptop.
"""
from __future__ import annotations

import json
import logging
import subprocess
import sys
import time
import traceback
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from . import store
from .portfolio import Prices
from .protection import check as protection_check
from .protection import status_line
from .protection import summary as protection_summary
from .telegram import Telegram, TelegramError
from .yahoo import YahooError, fetch

PROTECTION_HOUR = 8            # daily crash-protection check after this hour

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "data" / "state.json"
HEARTBEAT = ROOT / "data" / "heartbeat"
BUSY = ROOT / "data" / "busy"
TZ = ZoneInfo("Europe/Zagreb")
WEEKDAY, HOUR = 5, 9          # Saturday 09:00
RETRY = timedelta(hours=3)     # wait after a failed weekly run
PY = sys.executable

WEEKLY = [
    (["scripts/fetch_ideas.py"], 3 * 3600),
    (["scripts/analyze_ideas.py"], 600),
    (["scripts/test_exit_rules.py"], 600),
    (["scripts/update_universe.py"], 2 * 3600),
    (["scripts/test_candidates.py"], 600),
    (["scripts/build_site.py"], 1800),
    (["scripts/report.py", "--no-update", "--telegram"], 900),
]
ON_DEMAND = [
    (["scripts/build_site.py"], 1800),
    (["scripts/report.py", "--no-update", "--telegram"], 900),
]

log = logging.getLogger("invest_bot")


def last_slot(now: datetime) -> datetime:
    """The most recent Saturday 09:00 not later than now."""
    slot = now.replace(hour=HOUR, minute=0, second=0, microsecond=0)
    slot -= timedelta(days=(slot.weekday() - WEEKDAY) % 7)
    return slot if slot <= now else slot - timedelta(days=7)


def load_state() -> dict:
    try:
        return json.loads(STATE.read_text())
    except (OSError, ValueError):
        return {}


def save_state(state: dict) -> None:
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=1))
    tmp.replace(STATE)


def run_steps(steps: list[tuple[list[str], int]]) -> None:
    for args, timeout in steps:
        log.info("running %s", " ".join(args))
        out = ROOT / "data" / "ideas" / "summary.txt" if args[0].endswith("analyze_ideas.py") else None
        p = subprocess.run([PY, *args], cwd=ROOT, capture_output=True, text=True, timeout=timeout)
        if out is not None and p.returncode == 0:
            out.write_text(p.stdout)
        if p.returncode != 0:
            tail = "\n".join((p.stderr or p.stdout).strip().splitlines()[-15:])
            raise RuntimeError(f"{args[0]} exited with {p.returncode}:\n{tail}")


class Bot:
    def __init__(self) -> None:
        self.tg = Telegram()
        self.offset = load_state().get("offset", 0)

    def say(self, text: str) -> None:
        try:
            self.tg.send_text(text)
        except TelegramError as e:
            log.error("telegram: %s", e)

    def job(self, steps, label: str) -> bool:
        started = time.monotonic()
        BUSY.write_text(label)
        try:
            run_steps(steps)
        except Exception as e:  # noqa: BLE001 - every failure must reach the owner
            log.error("%s failed: %s", label, e)
            self.say(f"❌ {label} не удался:\n{e}"[:3500])
            return False
        finally:
            BUSY.unlink(missing_ok=True)
        log.info("%s done in %.0f s", label, time.monotonic() - started)
        return True

    def weekly_if_due(self) -> None:
        state = load_state()
        now = datetime.now(TZ)
        slot = last_slot(now).isoformat()
        if state.get("weekly_done", "") >= slot:
            return
        # After a failure wait before trying again, or every loop would retry and alert
        failed = state.get("weekly_failed_at")
        if failed and now - datetime.fromisoformat(failed) < RETRY:
            return
        ok = self.job(WEEKLY, "Еженедельный прогон")
        state = load_state()
        if ok:
            state["weekly_done"] = slot
            state.pop("weekly_failed_at", None)
        else:
            state["weekly_failed_at"] = now.isoformat()
            self.say(f"Следующая попытка через {RETRY.seconds // 3600} ч.")
        save_state(state)

    def protection_if_due(self) -> None:
        """Once a day: refresh SPY and BIL, and tell the owner at once when the
        month-end status of the crash-protection rule changes."""
        state = load_state()
        now = datetime.now(TZ)
        today = now.date().isoformat()
        if state.get("protection_checked") == today or now.hour < PROTECTION_HOUR:
            return
        con = store.connect()
        try:
            for sym in ("SPY", "BIL"):
                store.save(con, fetch(sym, date(2005, 1, 1)))
                time.sleep(1)
        except YahooError as e:
            log.warning("protection: %s", e)
            return                      # try again on the next loop
        p = protection_check(Prices(con))
        prev = state.get("protection")
        current = {"month_end": p.month_end, "fired": p.fired}
        if prev and prev.get("fired") != p.fired:
            if p.fired:
                self.say(f"{status_line(p)}\n\nПо правилу — выйти из акций в краткосрочные гособлигации до "
                         f"закрытия месяца выше средней.\n{protection_summary(p)}\nРешение за вами.")
            else:
                self.say(f"🟢 Защита от обвала: отбой. На конец месяца ({p.month_end}) S&P 500 снова выше "
                         f"200-дневной средней на {p.month_gap:.1%} — по правилу можно возвращаться в акции.")
        state = load_state()
        state["protection"] = current
        state["protection_checked"] = today
        save_state(state)
        log.info("protection: %s, month end %s %+.1f%%", p.level, p.month_end, p.month_gap * 100)

    def poll(self, timeout: int = 50) -> None:
        """One long-poll request for commands; returns after `timeout` seconds at most."""
        try:
            updates = self.tg._post("getUpdates", http_timeout=timeout + 15, offset=self.offset,
                                    timeout=timeout, allowed_updates='["message"]')
        except TelegramError as e:
            log.warning("getUpdates: %s", e)
            time.sleep(10)
            return
        for u in updates:
            self.offset = u["update_id"] + 1
            msg = u.get("message") or {}
            if msg.get("chat", {}).get("id") != self.tg.chat_id:
                continue                    # only the owner's chat
            cmd = (msg.get("text") or "").split()[0].split("@")[0] if msg.get("text") else ""
            if cmd == "/report":
                self.say("⏳ Собираю отчёт, это займёт пару минут…")
                self.job(ON_DEMAND, "Отчёт по запросу")
            elif cmd in ("/start", "/help"):
                self.say("Команды:\n/report — свежий отчёт и обновление дашборда\n"
                         "Еженедельный отчёт приходит по субботам в 9:00.")
        state = load_state()
        state["offset"] = self.offset
        save_state(state)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    BUSY.unlink(missing_ok=True)           # left by a job that was killed
    bot = Bot()
    log.info("started, next weekly slot after %s", last_slot(datetime.now(TZ)).isoformat())
    while True:
        HEARTBEAT.touch()
        try:
            bot.weekly_if_due()
            bot.protection_if_due()
            bot.poll()
        except requests.RequestException as e:
            log.warning("network: %s", type(e).__name__)
            time.sleep(30)
        except Exception:  # noqa: BLE001 - keep the loop alive, tell the owner
            log.error("loop: %s", traceback.format_exc())
            bot.say(f"❌ Ошибка в цикле бота:\n{traceback.format_exc()[-1500:]}")
            time.sleep(300)


if __name__ == "__main__":
    main()
