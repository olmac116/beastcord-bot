import discord
from discord import app_commands

from lib.logging import log

group = app_commands.Group(name="help", description="Help commands")

@group.command(name="moderation", description="Help with moderation commands")
async def moderation(interaction: discord.Interaction):
    embed = discord.Embed(title="Moderation Commands Help", description="There are no moderation commands at this time")
    # embed.add_field(name="CommandName", value="Information")

    await interaction.response.send_message(embed)

@group.command(name="entertainment", description="Help with entertainment commands")
async def entertainment(interaction: discord.Interaction):
    await interaction.response.send_message("MESSAGE")
    await log(interaction.guild_id, "Testing!!")

def setup(bot_tree, guild=None):
    if guild:
        bot_tree.add_command(group, guild=guild)
    else:
        bot_tree.add_command(group)
