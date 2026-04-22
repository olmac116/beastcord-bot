import discord
from discord import app_commands
import asyncio
import time
from datetime import datetime, timezone

from pymongo import MongoClient

from lib.envLoader import env
from lib.embeds import generalEmbed

STARTED_AT = datetime.now(timezone.utc)


def _format_uptime(total_seconds: float) -> str:
    seconds = int(total_seconds)
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    return f"{days}d {hours}h {minutes}m {seconds}s"


async def _mongo_ping() -> tuple[float | None, str | None]:
    mongo_uri = env("MONGO_URI", env("DB_URI", None))
    if not mongo_uri:
        return None, "Not configured"

    def _do_ping() -> tuple[float | None, str | None]:
        client = MongoClient(mongo_uri, serverSelectionTimeoutMS=2500)
        try:
            start = time.perf_counter()
            client.admin.command("ping")
            elapsed_ms = (time.perf_counter() - start) * 1000
            return elapsed_ms, None
        except Exception as exc:
            return None, str(exc)
        finally:
            client.close()

    return await asyncio.to_thread(_do_ping)

@app_commands.command(name="ping", description="Get connection info and bot uptime")
async def ping(interaction: discord.Interaction):
    websocket_ms = interaction.client.latency * 1000
    mongo_ms, mongo_error = await _mongo_ping()
    uptime = _format_uptime((datetime.now(timezone.utc) - STARTED_AT).total_seconds())

    embed = generalEmbed(
        title="Pong!",
        description="Bot status diagnostics",
        timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(name="WebSocket", value=f"{websocket_ms:.2f} ms", inline=True)

    if mongo_ms is not None:
        embed.add_field(name="Database", value=f"{mongo_ms:.2f} ms", inline=True)
    else:
        reason = mongo_error or "Unavailable"
        if len(reason) > 90:
            reason = reason[:87] + "..."
        embed.add_field(name="Database", value=f"Unavailable ({reason})", inline=True)

    embed.add_field(name="Uptime", value=uptime, inline=False)
    
    # add the guilds counter if theres more than 1 guild
    if len(interaction.client.guilds) > 1:
        embed.add_field(name="Guilds", value=str(len(interaction.client.guilds)), inline=True)
        
    if env("TESTING_ENABLED", "false").lower() == "true":
        embed.set_footer(text="Test mode is enabled - results may be inaccurate to production environment")

    await interaction.response.send_message(embed=embed)

def setup(bot_tree, guild=None):
    if guild:
        bot_tree.add_command(ping, guild=guild)
    else:
        bot_tree.add_command(ping)
