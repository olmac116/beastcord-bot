import discord
from discord import app_commands
from discord.ext import commands, tasks
import importlib
import os

from lib.logging import log
from lib.envLoader import env
from lib.messageResponder import check_and_respond
from lib.settingsLib import getSettings
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

# status loop
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
    await bot.change_presence(activity=discord.CustomActivity(name=f"{'' if not testing_enabled else 'test mode '}/help | {status}"), status=discord.Status.online)
    current_status_index += 1

# when the bot logs in
@bot.event
async def on_ready():
    log("GLOBAL", f"Logged in as {bot.user}")
    
    # set initial presence while loading statuses
    await bot.change_presence(activity=discord.CustomActivity(name="Starting up.."), status=discord.Status.do_not_disturb)
    
    # load statuses from the file
    statuses_loaded, status_count, status_error = load_statuses()
    if statuses_loaded and status_count is not None:
        log("GLOBAL", f"Loaded {status_count} status(es)")
    elif status_error:
        log("GLOBAL", f"Error loading statuses: {status_error}")

    if statuses_loaded:
        # start the status cycling task
        if not cycle_status.is_running():
            cycle_status.start()
    else:
        log("GLOBAL", "No statuses loaded, skipping status cycling.")
        await bot.change_presence(activity=discord.CustomActivity(name=f"{'' if not testing_enabled else 'test mode '}/help"), status=discord.Status.online)

    # if the db is not set up, log a warning that some features may not work
    if env("DB_URI", None) is None:
        log(guild_id="GLOBAL", message="No DB_URI set in environment variables. Some features may be disabled and issues may occur.")

    # sync commands
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

# welcome message
@bot.event
async def on_member_join(member: discord.Member):
    try:
        await send_welcome_message(member)
    except Exception as e:
        log(member.guild.id, f"Failed to send welcome card: {e}")

# leave message
@bot.event
async def on_member_remove(member: discord.Member):
    success, saved_settings = await getSettings(member.guild.id)
    if not success:
        log(member.guild.id, "Failed to load settings while sending leave message")
        return

    leave_channel_id = saved_settings.get("leaveChannel") if saved_settings else None
    if not leave_channel_id:
        return

    channel = member.guild.get_channel(int(leave_channel_id))
    if channel is None:
        log(member.guild.id, f"Configured leave channel {leave_channel_id} was not found")
        return

    try:
        await channel.send(f"*{member.mention} left the server.*")
    except discord.Forbidden:
        log(member.guild.id, f"Missing permission to send leave message in channel {channel.id}")
    except discord.HTTPException as error:
        log(member.guild.id, f"Failed to send leave message in channel {channel.id}: {error}")

# message responder
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    await check_and_respond(message)
    await bot.process_commands(message)

# when the script is ran from the command line, load all commands from the commands folder and start the bot
if __name__ == "__main__":
    log("GLOBAL", f"Initializing commands...")
    testing_value = env("TESTING", False)
    testing_enabled = testing_value if isinstance(testing_value, bool) else str(testing_value).lower() == "true"
    
    for filename in os.listdir("./commands"):
        if filename.endswith(".py") and filename != "__init__.py":
            # exclude testing commands in production
            if not testing_enabled and filename.startswith("tests"):
                continue
            
            # exclude example commands
            if filename.startswith("example"):
                continue
            
            module_name = f"commands.{filename[:-3]}"
            module = importlib.import_module(module_name)
            if hasattr(module, "setup"):
                if guild_obj:
                    module.setup(tree, guild=discord.Object(id=mainguildid))
                else:
                    module.setup(tree)
    
    log("GLOBAL", f"Starting bot...")
    bot.run(env("DISCORD_TOKEN"))
