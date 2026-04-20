import asyncio
import datetime
import logging as py_logging

import discord
from pymongo import AsyncMongoClient, MongoClient

from lib.envLoader import env

logger = py_logging.getLogger("beastcord")
if not logger.handlers:
    handler = py_logging.StreamHandler()
    handler.setFormatter(py_logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(py_logging.INFO)
    logger.propagate = False

loggingEnabled = env("DB_URI", None) is not None

if loggingEnabled:
    db_uri = env("DB_URI")
    db_name = env("DB_MAIN_COLLECTION_NAME", "bot")

    async_mongo_client = AsyncMongoClient(db_uri)
    async_db = async_mongo_client[db_name]
    logs_collection = async_db["logs"]
    server_settings_collection = async_db["server_settings"]

    sync_mongo_client = MongoClient(db_uri)
    sync_db = sync_mongo_client[db_name]
    sync_logs_collection = sync_db["logs"]


async def log_message(guild_id: int, client: discord.Client, message: str, type: str):
    settings = await server_settings_collection.find_one({"guild_id": guild_id})
    if not settings:
        logger.warning("No server settings found for guild %s", guild_id)
        return

    channel_id = settings.get("log_channel_id")
    if not channel_id:
        logger.warning("No log channel configured for guild %s", guild_id)
        return

    channel = client.get_channel(channel_id)
    types = {
        "cmd": "Command Log",
        "msg": "Message Log",
        "err": "Error Log",
        "info": "Info Log",
    }

    if channel:
        embed = discord.Embed(
            title=types[type] or types["info"],
            description=message,
            color=discord.Color.blue(),
        )
        await channel.send(embed=embed)


async def _persist_log(guild_id: int | str, message: str):
    if loggingEnabled:
        try:
            await logs_collection.insert_one(
                {
                    "guildid": guild_id,
                    "message": message,
                    "timestamp": datetime.datetime.now().isoformat(),
                }
            )
        except Exception:
            logger.exception("Failed to persist async log for guild %s", guild_id)


def _persist_log_sync(guild_id: int | str, message: str):
    if loggingEnabled:
        try:
            sync_logs_collection.insert_one(
                {
                    "guildid": guild_id,
                    "message": message,
                    "timestamp": datetime.datetime.now().isoformat(),
                }
            )
        except Exception:
            logger.exception("Failed to persist sync log for guild %s", guild_id)


def log(guild_id: int | str, message: str):
    logger.info("Guild id: %s inserted a new log: %s", guild_id, message)

    if not loggingEnabled:
        return

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        _persist_log_sync(guild_id, message)
        return

    loop.create_task(_persist_log(guild_id, message))
