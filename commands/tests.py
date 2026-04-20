import discord
from discord import app_commands

from lib.welcome import send_welcome_message


group = app_commands.Group(name="tests", description="Perform a manual test of a bot function")


@group.command(name="welcome", description="Send a test welcome message for yourself")
async def test_welcome(interaction: discord.Interaction):
    if interaction.guild is None or not isinstance(interaction.user, discord.Member):
        await interaction.response.send_message("This command can only be used inside a server.", ephemeral=True)
        return

    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("You need administrator permissions to run this command.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    try:
        sent = await send_welcome_message(interaction.user)
        if not sent:
            await interaction.followup.send(
                "No welcome channel is configured (or it is invalid). Set one with /settings welcome.",
                ephemeral=True,
            )
            return

        await interaction.followup.send("Sent a test welcome message in the configured welcome channel.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"Failed to send test welcome message: {e}", ephemeral=True)


def setup(bot_tree, guild=None):
    if guild:
        bot_tree.add_command(group, guild=guild)
    else:
        bot_tree.add_command(group)
