#!/bin/sh
# Try unreleased code on the phone: copy it from the laptop, build the image there
# and run it. The updater then holds this build until the next release is
# installed by hand: ssh $PHONE '~/invest-analytics-bot/update.sh --force'.
# Usage: deploy/deploy.sh [user@host]   (data/ and the keys are not touched)
#
# BuildKit cannot build on the phone: its runc needs openat2 (Linux 5.6) and the
# phone runs 4.19; the legacy builder uses the daemon's crun.
set -e
cd "$(dirname "$0")/.."
# shellcheck source=/dev/null
[ -f deploy/local.env ] && . deploy/local.env
PHONE=${1:-${PHONE:?set PHONE=user@host in deploy/local.env}}
tar --exclude=.venv --exclude=.git --exclude=public --exclude=data --exclude='__pycache__' -czf - . |
	ssh "$PHONE" 'rm -rf ~/invest-analytics-bot/src && mkdir -p ~/invest-analytics-bot/src && tar -C ~/invest-analytics-bot/src -xzf -'
# data/ and public/ must belong to the user the container runs as (uid 10000);
# a directory Docker creates for a missing bind mount belongs to root
ssh "$PHONE" 'cd ~/invest-analytics-bot && mkdir -p data public deploy &&
	DOCKER_BUILDKIT=0 docker build -q -t invest-analytics-bot:dev src &&
	cp src/compose.yaml . && cp src/deploy/nginx.conf deploy/ && cp src/deploy/update.sh . &&
	printf "INVBOT_IMAGE=invest-analytics-bot:dev\nINVBOT_HOLD=1\n" > .env &&
	docker compose up -d && docker compose ps'
