import discord
from discord import app_commands

from lib.logging import log

group = app_commands.Group(name="help", description="Help commands")

# @group.command(name="moderation", description="Help with moderation commands")
# async def moderation(interaction: discord.Interaction):
#     embed = discord.Embed(title="Moderation Commands Help", description="There are no moderation commands at this time")
#     # embed.add_field(name="CommandName", value="Information")

#     await interaction.response.send_message(embed)
    
@group.command(name="modmail", description="Help with modmail commands")
async def modmail(interaction: discord.Interaction):
    helpEmbed = discord.Embed(title="Modmail Commands Help", description="Send a message to the moderators using the /modmail command. The moderators will respond to your message as soon as possible.\n\n**Command Arguments**")
    helpEmbed.add_field(name="message", value="This is what the moderators will see when you send a modmail message.")
    helpEmbed.add_field(name="anonymous", value="Anonymously send the message to the server moderators. This will hide your username and avatar.")
    helpEmbed.add_field(name="allow_replies", value="Allow or disable replies to your modmail message (Note: you must have server messages enabled).")

    await interaction.response.send_message(embed=helpEmbed)

def setup(bot_tree, guild=None):
    if guild:
        bot_tree.add_command(group, guild=guild)
    else:
        bot_tree.add_command(group)
