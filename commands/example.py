import discord
from discord import app_commands

group = app_commands.Group(name="example", description="Example commands")

# @group.command(name="ping", description="Replies with Pong!")
# async def ping(interaction: discord.Interaction):
#     await interaction.response.send_message("Pong!")

@group.command(name="boom", description="Replies with Boom!")
async def boom(interaction: discord.Interaction):
    await interaction.response.send_message("Boom!")

def setup(bot_tree, guild=None):
    if guild:
        bot_tree.add_command(group, guild=guild)
    else:
        bot_tree.add_command(group)
