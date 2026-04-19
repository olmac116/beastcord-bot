import discord
from discord import app_commands
from discord.ext import commands, tasks
import importlib
import os

from lib.logging import log
from lib.envLoader import env
from lib.messageResponder import check_and_respond
from lib.welcome import send_welcome_message

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

mainguildid = env("MAIN_GUILD_ID", None)
guild_obj = discord.Object(id=int(mainguildid)) if mainguildid else None

# status cycling
statuses = []
current_status_index = 0

def load_statuses():
    global statuses
    try:
        if os.path.exists("static/statuses.txt"):
            with open("static/statuses.txt", "r") as f:
                statuses = [line.strip() for line in f if line.strip()]
            if statuses:
                return True, len(statuses), None
        return False, None, None
    except Exception as e:
        return False, None, str(e)

@tasks.loop(minutes=5)
async def cycle_status():
    global current_status_index, statuses
    
    if not statuses:
        return
    
    formats = {
        "{member-count}": f"{sum(len(guild.members) for guild in bot.guilds):,}",
    }
    
    status = statuses[current_status_index % len(statuses)]
    for placeholder, value in formats.items():
        status = status.replace(placeholder, value)
    await bot.change_presence(activity=discord.CustomActivity(name=f"/help | {status}"), status=discord.Status.online)
    current_status_index += 1

@bot.event
async def on_ready():
    log("GLOBAL", f"Logged in as {bot.user}")
    
    # Load statuses from file
    statuses_loaded, status_count, status_error = load_statuses()
    if statuses_loaded and status_count is not None:
        log("GLOBAL", f"Loaded {status_count} status(es)")
    elif status_error:
        log("GLOBAL", f"Error loading statuses: {status_error}")

    if not statuses_loaded:
        # Fallback to default status if no file exists
        await bot.change_presence(activity=discord.CustomActivity(name="Starting up.."), status=discord.Status.do_not_disturb)
    else:
        # Start the status cycling task
        if not cycle_status.is_running():
            cycle_status.start()

    if env("DB_URI", None) is None:
        log(guild_id="GLOBAL", message="No DB_URI set in environment variables. Some features may be disabled and issues may occur.")

    try:
        if guild_obj:
            await tree.sync(guild=guild_obj)
            log("GLOBAL", f"Commands synced to guild {mainguildid}")
        else:
            await tree.sync()
            log("GLOBAL", "Commands synced globally")
    except Exception as e:
        log("GLOBAL", f"Error syncing commands: {e}")
    
    for command in tree.get_commands(guild=guild_obj):
        log("GLOBAL", f"Registered command: /{command.name}")


@bot.event
async def on_member_join(member: discord.Member):
    # print(f"[JOIN] {member} joined {member.guild.name}")
    try:
        await send_welcome_message(member)
    except Exception as e:
        log(member.guild.id, f"Failed to send welcome card: {e}")

    # # Example: send a welcome message to the server's system channel if available.
    # if member.guild.system_channel:
    #     await member.guild.system_channel.send(
    #         f"Welcome {member.mention}!"
    #     )


@bot.event
async def on_member_remove(member: discord.Member):
    # print(f"[LEAVE] {member} left {member.guild.name}")
    
    # Example: send a farewell message to the server's system channel if available.
    if member.guild.system_channel:
        await member.guild.system_channel.send(
            f"*{member.mention} left the server.*"
        )


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    await check_and_respond(message)
    await bot.process_commands(message)



for filename in os.listdir("./commands"):
    if filename.endswith(".py") and filename != "__init__.py":
        module_name = f"commands.{filename[:-3]}"
        module = importlib.import_module(module_name)
        if hasattr(module, "setup"):
            if guild_obj:
                module.setup(tree, guild=discord.Object(id=mainguildid))
            else:
                module.setup(tree)

bot.run(env("DISCORD_TOKEN"))
