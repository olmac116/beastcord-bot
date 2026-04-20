import asyncio
import datetime
import logging as py_logging

import discord
from pymongo import MongoClient

from lib.envLoader import env

logger = py_logging.getLogger("beastcord")
if not logger.handlers:
    handler = py_logging.StreamHandler()
    handler.setFormatter(py_logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(py_logging.INFO)
    logger.propagate = False

db_uri = env("DB_URI", None)
dbEnabled = db_uri is not None
loggingEnabled = dbEnabled

if dbEnabled:
    mongo_client = MongoClient(db_uri)
    db = mongo_client[env("DB_MAIN_COLLECTION_NAME", "bot")]
    moderationLogs = db["modLogs"]
    logs_collection = db["logsCollection"]
    server_settings_collection = db["server_settings"]
else:
    mongo_client = None
    db = None
    moderationLogs = None
    logs_collection = None
    server_settings_collection = None


def _build_log_document(guild_id: int | str, message: str):
    return {
        "guildid": guild_id,
        "message": message,
        "timestamp": datetime.datetime.now().isoformat(),
    }


async def log_message(guild_id: int, client: discord.Client, message: str, log_type: str):
    if server_settings_collection is None:
        logger.warning("No database connected; cannot send log message for guild %s", guild_id)
        return

    settings = await asyncio.to_thread(server_settings_collection.find_one, {"guildId": guild_id})
    if not settings:
        logger.warning("No server settings found for guild %s", guild_id)
        return

    channel_id = settings.get("logsChannel")
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
        title = types.get(log_type, types["info"])
        embed = discord.Embed(
            title=title,
            description=message,
            color=discord.Color.blue(),
        )
        await channel.send(embed=embed)


async def _persist_log(guild_id: int | str, message: str):
    if not loggingEnabled or logs_collection is None:
        return

    try:
        await asyncio.to_thread(logs_collection.insert_one, _build_log_document(guild_id, message))
    except Exception:
        logger.exception("Failed to persist async log for guild %s", guild_id)


def _persist_log_sync(guild_id: int | str, message: str):
    if not loggingEnabled or logs_collection is None:
        return

    try:
        logs_collection.insert_one(_build_log_document(guild_id, message))
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
