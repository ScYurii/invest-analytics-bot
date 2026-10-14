# invest-analytics-bot

[![ci](https://github.com/ScYurii/invest-analytics-bot/actions/workflows/ci.yml/badge.svg)](https://github.com/ScYurii/invest-analytics-bot/actions/workflows/ci.yml)

Weekly analytics for a [Freedom24](https://freedom24.com) brokerage account: a report in
Telegram and a static dashboard, served from an old phone running postmarketOS.
**The bot never places orders** — it reads the account (read-only API wrapper) and
explains what simple, backtested rules say; the owner decides.

> **RU:** Аналитика счёта Freedom24 раз в неделю: отчёт в Telegram и дашборд на старом
> телефоне с postmarketOS. Бот **не отправляет заявки** — только читает счёт и показывает,
> что говорят простые правила, проверенные на истории. Решения принимает человек.
> Это не инвестиционный совет.

What it shows:

- **Portfolio** — every holding against the S&P 500 over the same dates, in EUR and in the
  holding's currency; concentration and USD share; a "lagging the index for 12 months"
  hint with the cost of selling under the broker's tariff.
- **Market** — S&P 500 against its 200-day average and a crash-protection status
  (🟢/🟡/🔴) with every past signal of the rule and whether it helped.
- **Freedom24 investment ideas** — new ideas of the week next to the track record of all
  ~1200 past ideas against the index.
- **Candidates** — S&P 500 stocks passing a momentum + trend screen, as a reason to study
  a company, with the screen's backtest.
- **Summary** — 5–8 plain-language bullets written by Claude from the report's own
  numbers (optional; forbidden to give advice or to invent facts).

The rules and what the backtests showed: [docs/research.md](docs/research.md).

## Architecture

```
GitHub ── push main ──► CI: ruff, pytest, shellcheck ──► arm64 image :edge
       └─ tag vX.Y.Z ─► same ──► :X.Y.Z + :stable, cosign signature, GitHub release
                                          │
            phone (postmarketOS, Docker)  ▼  pulled every 15 min by deploy/update.sh
   ┌──────────────────────────────────────────────────────────────┐
   │ bot  (python -m invest_bot.daemon)                           │
   │   Saturday 09:00: ideas → statistics → prices → site → report │──► Telegram
   │   daily: crash-protection check, alert on a status change    │
   │   /report command                                            │
   │ web  (nginx, static public/site, home network only) :8081    │──► browser
   └──────────────────────────────────────────────────────────────┘
        data/ (SQLite prices, reports, state) ── weekly copy ──► laptop
```

- **Pull, not push.** The phone sits behind NAT; nothing reaches into it. A cron job checks
  for a new `:stable` image, verifies its cosign signature (built by this repository's
  workflow from a `v*` tag), pins the digest in `.env`, restarts, waits for the Docker
  healthcheck and rolls back on failure. It never restarts the bot mid-job
  (`data/busy`). The image carries `compose.yaml` and its own updater, so one artifact is
  the whole release.
- **No secrets in CI or in the image.** Keys live on the phone in `~/.config` (mode 600)
  and are mounted read-only.
- **Native arm64 build** on GitHub's arm runners: the phone's 4.19 kernel cannot run
  BuildKit (its runc needs `openat2`), and emulation is slow.

## Layout

| Path | What |
|---|---|
| `invest_bot/broker.py` | Tradernet API, **read-only** (no order methods; errors that come as HTTP 200 become exceptions) |
| `invest_bot/yahoo.py`, `store.py` | Daily history from Yahoo (prices, dividends, splits) into SQLite |
| `invest_bot/portfolio.py` | Positions and FIFO lots from the trade history |
| `invest_bot/report.py`, `site.py` | The weekly report text and the static dashboard |
| `invest_bot/ideas.py`, `candidates.py`, `protection.py` | Freedom24 ideas, buy candidates, crash protection |
| `invest_bot/summary.py` | Optional summary via the Anthropic API |
| `invest_bot/daemon.py`, `health.py` | The container's main loop and its healthcheck |
| `scripts/` | Every step as a command: the daemon runs the same scripts |
| `deploy/update.sh` | The updater on the phone (cron) |
| `deploy/deploy.sh`, `backup.sh` | From the laptop: try unreleased code on the phone; copy the data back |
| `tests/` | Unit tests on synthetic prices (no network, no keys) |

## Development (laptop)

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-dev.txt
.venv/bin/ruff check . && .venv/bin/pytest -q
```

Keys (directory 700, files 600; never in git):

```ini
# ~/.config/tradernet/tradernet.ini
[auth]
public = ...
private = ...

# ~/.config/invest-bot/telegram.ini
[telegram]
token = ...
chat_id = ...

# ~/.config/invest-bot/anthropic.ini   (optional)
[anthropic]
key = ...
```

```sh
.venv/bin/python scripts/check_api.py        # do the keys work? (prints no personal data)
.venv/bin/python scripts/update_prices.py    # Yahoo history into data/prices.db + checks
.venv/bin/python scripts/report.py           # the weekly report in the terminal
.venv/bin/python scripts/build_site.py       # the dashboard into public/site
```

## The phone

One-time setup (postmarketOS / Alpine, as the user that runs Docker):

```sh
doas apk add cosign
doas rc-update add crond default && doas rc-service crond start
mkdir -p ~/invest-analytics-bot && cd ~/invest-analytics-bot
docker run --rm --entrypoint cat ghcr.io/scyurii/invest-analytics-bot:stable deploy/update.sh > update.sh
chmod +x update.sh && ./update.sh --force && tail update.log
( crontab -l 2>/dev/null; echo '*/15 * * * * $HOME/invest-analytics-bot/update.sh' ) | crontab -
```

Releasing is tagging: `git tag v1.2.0 && git push origin v1.2.0` — the phone installs it within
15 minutes and reports to Telegram ("✅ updated to 1.2.0" or "↩️ rolled back").

```sh
deploy/deploy.sh          # unreleased code: build on the phone, hold updates until update.sh --force
deploy/backup.sh          # copy data/ to ~/backups/invest-analytics-bot (systemd timer in deploy/systemd)
ssh $PHONE 'cd ~/invest-analytics-bot && docker compose logs --tail 50 bot; tail update.log'
```

`deploy/local.env` (not in git, see `deploy/local.env.example`) holds the phone's address.
The dashboard port is closed to everything but the home network by the phone's firewall
(Docker-published ports bypass `INPUT`, so the rule sits in `DOCKER-USER`).

## License

MIT, see [LICENSE](LICENSE). Bundles [Chart.js](https://www.chartjs.org) 4.4.1 (MIT).
