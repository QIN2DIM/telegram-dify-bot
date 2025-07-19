docker compose pull telegram-dify-bot
docker compose up telegram-dify-bot --force-recreate --no-deps -d
docker compose logs telegram-dify-bot -f --no-log-prefix