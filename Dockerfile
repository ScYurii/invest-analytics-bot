# The bot: weekly refresh, Telegram commands, dashboard pages into /app/public/site
FROM python:3.14-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TZ=Europe/Zagreb
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY invest_bot invest_bot
COPY scripts scripts
COPY tickers.txt .
# The files the phone needs next to the image; deploy/update.sh takes them from here
COPY compose.yaml deploy/nginx.conf deploy/update.sh deploy/
# The owner of the key files on the phone (user, uid 10000), so mode 600 is enough
USER 10000:10000
# The first loop needs the network (Telegram, Yahoo): give it two minutes
HEALTHCHECK --interval=60s --timeout=10s --start-period=120s --retries=3 \
	CMD ["python", "-m", "invest_bot.health"]
CMD ["python", "-m", "invest_bot.daemon"]
