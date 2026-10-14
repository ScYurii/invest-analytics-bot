#!/bin/sh
# Pull a copy of the bot's data from the phone to the laptop (run on the laptop).
#
# The phone has no rsync or sqlite3: the database is snapshotted with Python's
# SQLite backup inside the bot container (consistent even while the bot writes),
# then data/ comes over ssh as one tar.gz. The archive and the database in it are
# checked, the last KEEP archives are kept, and the phone is told the date so the
# weekly report can warn when copies stop.
#
# Usage: deploy/backup.sh [--force]   (without --force: only if the last copy is
#        older than MIN_DAYS, so a daily timer gives one copy a week)
# shellcheck disable=SC2012  # archive names are ours: invest-bot-data-YYYY-MM-DD.tar.gz
set -eu
cd "$(dirname "$0")/.."
# shellcheck source=/dev/null
[ -f deploy/local.env ] && . deploy/local.env
PHONE=${PHONE:?set PHONE=user@host in deploy/local.env}
DEST=${DEST:-$HOME/backups/invest-analytics-bot}
KEEP=${KEEP:-8}
MIN_DAYS=${MIN_DAYS:-6}
SSH="ssh -o BatchMode=yes -o ConnectTimeout=10 $PHONE"

mkdir -p "$DEST"
last=$(ls -1 "$DEST"/invest-bot-data-*.tar.gz 2>/dev/null | tail -1 || true)
if [ "${1:-}" != "--force" ] && [ -n "$last" ] &&
	[ -n "$(find "$last" -mtime -"$MIN_DAYS")" ]; then
	echo "last copy is recent: $(basename "$last")"
	exit 0
fi

stamp=$(date +%Y-%m-%d)
out="$DEST/invest-bot-data-$stamp.tar.gz"

$SSH 'cd ~/invest-analytics-bot && docker compose exec -T bot python -c "
import sqlite3
src = sqlite3.connect(\"data/prices.db\")
dst = sqlite3.connect(\"data/prices.backup.db\")
src.backup(dst)
dst.close()
"'
$SSH 'tar -C ~/invest-analytics-bot -czf - --exclude=data/prices.db --exclude=data/backup.json data' > "$out.part"

# Check: the archive reads, the database in it is intact
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
tar -xzf "$out.part" -C "$tmp" data/prices.backup.db data/state.json
python3 -I -c "
import sqlite3, sys
con = sqlite3.connect(sys.argv[1])
ok = con.execute('PRAGMA integrity_check').fetchone()[0]
n = con.execute('SELECT COUNT(*) FROM bars').fetchone()[0]
assert ok == 'ok' and n > 0, (ok, n)
print(f'database ok, {n} bars')
" "$tmp/data/prices.backup.db"
mv "$out.part" "$out"
size=$(stat -c %s "$out")
echo "saved $out ($((size / 1024 / 1024)) MB)"

# Keep the newest KEEP archives
ls -1 "$DEST"/invest-bot-data-*.tar.gz | head -n -"$KEEP" | xargs -r rm -v

$SSH "cd ~/invest-analytics-bot && rm -f data/prices.backup.db &&
	printf '{\"last\": \"%s\", \"file\": \"%s\", \"bytes\": %s}\n' \
	'$(date -Iseconds)' '$(basename "$out")' '$size' > data/backup.json"
