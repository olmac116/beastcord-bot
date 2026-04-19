import discord
from discord import app_commands
from discord.ui import View, RoleSelect

from pymongo import AsyncMongoClient as MongoClient

from lib.logging import log
from lib.embeds import errorEmbed, successEmbed, generalEmbed
from lib.envLoader import env

dbEnabled = env("DB_URI", None) is not None


if dbEnabled:
    mongo_client = MongoClient(env("DB_URI"))
    db = mongo_client[env("DB_MAIN_COLLECTION_NAME", "Bot")]
    moderationLogs = db["modLogs"]
    activeBans = db["activeBans"]
    server_settings_collection = db["server_settings"]

async def updateSettings(guildId: int, key: str, data: any):
    if dbEnabled is False or dbEnabled is None:
        log(guild_id="GLOBAL", message="Cannot write to database if one isn't connected!")
        return False, "No Database"
    try:
        await server_settings_collection.update_one(
            {"guildId": int(guildId)},
            {"$set": {key: data}},
            upsert=True
        )
        return True, "Success"
    except Exception as e:
        log(guild_id=guildId, message=f"Failed to update server settings - {e}")
        return False, e


async def resetSettings(guildId: int, key: str | None = None):
    if dbEnabled is False or dbEnabled is None:
        log(guild_id="GLOBAL", message="Cannot write to database if one isn't connected!")
        return False, "No Database"

    try:
        if key is None:
            await server_settings_collection.delete_one({"guildId": int(guildId)})
        else:
            await server_settings_collection.update_one(
                {"guildId": int(guildId)},
                {"$unset": {key: ""}},
                upsert=True,
            )
        return True, "Success"
    except Exception as e:
        log(guild_id=guildId, message=f"Failed to reset server settings - {e}")
        return False, e
    
async def getSettings(guildId: int):
    if dbEnabled is False or dbEnabled is None:
        log(guild_id="GLOBAL", message="Cannot read from database if one isn't connected!")
        return False, "No Database"
    try:
        settings = await server_settings_collection.find_one({"guildId": int(guildId)})
        if settings is None:
            return True, {}
        return True, settings
    except Exception as e:
        log(guild_id=guildId, message=f"Failed to get server settings - {e}")
        return False, e