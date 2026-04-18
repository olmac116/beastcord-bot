# BeastcordBot

A basic `discord.py` bot project with Docker Compose and MongoDB.

## Project structure

- `src/bot.py`: bot entry point
- `src/db.py`: MongoDB connection helpers
- `docker-compose.yml`: bot + MongoDB stack
- `scripts/build_test.sh`: simple build/start helper

## Quick start

1. Copy `.env.example` to `.env` and set your token and guild id:
   - `cp .env.example .env`
2. Build and start the stack:
   - `./scripts/build_test.sh`
3. View logs if needed:
   - `docker compose logs -f bot`

## Bot commands

- `!ping`: replies with `Pong!`

## Notes

- MongoDB data is persisted in the named volume `mongo_data`.
- If MongoDB is unavailable, the bot still starts and runs without DB features.
- The bot reads `.env` variables such as `DISCORD_TOKEN`, `MAIN_GUILD_ID`, `MONGO_URI`, and `BOT_PREFIX`.
