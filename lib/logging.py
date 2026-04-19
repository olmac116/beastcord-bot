import asyncio
import datetime
import logging as py_logging

import discord
from pymongo import AsyncMongoClient as MongoClient

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
    mongo_client = MongoClient(env("DB_URI"))
    db = mongo_client[env("DB_MAIN_COLLECTION_NAME", "Lunaris")]
    logs_collection = db["logs"]
    server_settings_collection = db["server_settings"]


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
            title=types[type] or "Issue Log",
            description=message,
            color=discord.Color.blue(),
        )
        await channel.send(embed=embed)


async def _persist_log(guild_id: int | str, message: str):
    if loggingEnabled:
        await logs_collection.insert_one(
            {
                "guildid": guild_id,
                "message": message,
                "timestamp": datetime.datetime.now().isoformat(),
            }
        )


def log(guild_id: int | str, message: str):
    logger.info("Guild id: %s inserted a new log: %s", guild_id, message)

    if not loggingEnabled:
        return

    try:
        asyncio.get_running_loop().create_task(_persist_log(guild_id, message))
    except RuntimeError:
        asyncio.run(_persist_log(guild_id, message))
