#!/bin/sh
# Install the latest release on the phone (run by cron every 15 minutes).
#
# The release is the image ghcr.io/scyurii/invest-analytics-bot:stable, signed by
# the release workflow (cosign, keyless). The image also carries the files this
# directory needs (compose.yaml, deploy/nginx.conf, update.sh), so one artifact
# is the whole release. Steps:
#   1. skip while the bot runs a job (data/busy) or a hand-built image is held;
#   2. pull :stable; nothing to do if its digest is the one in .env;
#   3. verify the signature: built by this repository's workflow from a v* tag;
#   4. take the files from the image, pin the digest in .env, restart;
#   5. wait for the healthcheck; if it fails, put the previous version back
#      and remember the bad digest, so it is not tried again.
# The owner gets a Telegram message after 4-5 (sent by the bot that runs then).
#
# Usage: update.sh [--force]   (--force: also when the bot is busy or held)
set -eu
IMAGE=ghcr.io/scyurii/invest-analytics-bot
IDENTITY='^https://github\.com/ScYurii/invest-analytics-bot/\.github/workflows/ci\.yml@refs/tags/v'
ISSUER=https://token.actions.githubusercontent.com
DIR=${DIR:-$HOME/invest-analytics-bot}
HEALTH_WAIT=${HEALTH_WAIT:-300}

cd "$DIR"
log() { echo "$(date -Iseconds) $*" >> update.log; }
notify() { docker compose exec -T bot python -m invest_bot.notify "$1" >/dev/null 2>&1 || log "notify failed"; }
current() { sed -n 's/^INVBOT_IMAGE=//p' .env 2>/dev/null; }
# Replace by rename: sh reads this very script as it runs, a copy over it would break that
put() { cp -p "$1" "$2.tmp" && mv "$2.tmp" "$2"; }
FILES=".env compose.yaml update.sh deploy/nginx.conf"

# Keep the log short
[ -f update.log ] && tail -n 500 update.log > update.log.tmp && mv update.log.tmp update.log

if [ "${1:-}" != "--force" ]; then
	[ -e data/busy ] && exit 0
	grep -qx 'INVBOT_HOLD=1' .env 2>/dev/null && exit 0
fi

docker pull -q "$IMAGE:stable" >/dev/null 2>>update.log || { log "pull failed"; exit 1; }
new=$(docker image inspect -f '{{index .RepoDigests 0}}' "$IMAGE:stable")
old=$(current)
[ "$new" = "$old" ] && exit 0
grep -qxF "$new" .failed 2>/dev/null && exit 0

version=$(docker image inspect -f '{{index .Config.Labels "org.opencontainers.image.version"}}' "$new")
log "new release $version ($new)"
if ! cosign verify --certificate-identity-regexp "$IDENTITY" --certificate-oidc-issuer "$ISSUER" \
	"$new" >/dev/null 2>>update.log; then
	log "signature check failed, skipped"
	echo "$new" >> .failed
	notify "⚠️ Обновление $version не поставлено: подпись образа не прошла проверку."
	exit 1
fi

# Files from the image; the current ones go to .prev for a rollback
rm -rf .next .prev && mkdir -p .next .prev/deploy deploy data public
c=$(docker create "$new")
docker cp "$c:/app/deploy/." .next/ && docker rm "$c" >/dev/null
for f in $FILES; do
	if [ -e "$f" ]; then cp -p "$f" ".prev/$f"; fi
done
put .next/compose.yaml compose.yaml && put .next/update.sh update.sh && put .next/nginx.conf deploy/nginx.conf
printf 'INVBOT_IMAGE=%s\n' "$new" > .env

healthy() {
	i=0
	while [ "$i" -lt "$HEALTH_WAIT" ]; do
		s=$(docker inspect -f '{{.State.Health.Status}}' "$(docker compose ps -q bot)" 2>/dev/null || true)
		[ "$s" = healthy ] && return 0
		sleep 10
		i=$((i + 10))
	done
	return 1
}

if docker compose up -d --remove-orphans >>update.log 2>&1 && healthy; then
	log "running $version"
	rm -rf .prev .next
	docker image prune -f >/dev/null
	notify "✅ Бот обновлён до $version."
	exit 0
fi

log "$version unhealthy, rolling back"
echo "$new" >> .failed
if [ -e .prev/.env ]; then
	for f in $FILES; do
		if [ -e ".prev/$f" ]; then put ".prev/$f" "$f"; fi
	done
	if docker compose up -d --remove-orphans >>update.log 2>&1 && healthy; then
		notify "↩️ Обновление $version не запустилось (healthcheck), вернул прежнюю версию."
	else
		log "rollback is unhealthy too"
	fi
fi
exit 1
