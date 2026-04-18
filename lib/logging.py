import discord
from pymongo import AsyncMongoClient as MongoClient
import datetime
from colorama import Fore, init

from lib.envLoader import env

init()

loggingEnabled = env("DB_URI", None) is not None

if loggingEnabled:
    mongo_client = MongoClient(env("DB_URI"))
    db = mongo_client[env("DB_MAIN_COLLECTION_NAME", "Lunaris")]
    logs_collection = db["logs"]
    server_settings_collection = db["server_settings"]


async def log_message(guild_id: int, client: discord.Client, message: str, type: str):
    channel = client.get_channel(
        server_settings_collection.find_one({"guild_id": guild_id})["log_channel_id"]
    )
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


async def log(guild_id: int, message: str):
    if loggingEnabled:
        await logs_collection.insert_one(
            {
                "guildid": guild_id,
                "message": message,
                "timestamp": datetime.datetime.now().isoformat(),
            }
        )

    print(f"{Fore.RED}[LOG]{Fore.RESET} Guild id: {Fore.GREEN}{guild_id}{Fore.RESET} inserted a new log: {Fore.BLUE}{message}{Fore.RESET}")
