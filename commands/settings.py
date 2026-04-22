import discord
from discord import app_commands
from discord import channel
from discord.ui import View, RoleSelect

from pymongo import AsyncMongoClient as MongoClient

from lib.logging import log, log_message
from lib.embeds import errorEmbed, successEmbed, generalEmbed
from lib.envLoader import env
from lib.settingsLib import resetSettings as resetServerSettings, updateSettings


group = app_commands.Group(name="settings", description="Bot Server settings")

RESET_SETTING_CHOICES = [
    app_commands.Choice(name="Logs Channel", value="logsChannel"),
    app_commands.Choice(name="Registered Moderator Roles", value="registeredModerators"),
    app_commands.Choice(name="Auto-Responder Channel", value="autoResponderChannel"),
    app_commands.Choice(name="Welcome Channel", value="welcomeChannel"),
    app_commands.Choice(name="Leave Channel", value="leaveChannel"),
    app_commands.Choice(name="Mod Mail Channel", value="modMailChannel"),
    app_commands.Choice(name="Allow Anonymous Mod Mail", value="allowAnonymousModMail"),
]

RESET_SETTING_LABELS = {choice.value: choice.name for choice in RESET_SETTING_CHOICES}

dbEnabled = env("DB_URI", None) is not None

CHANNEL_PERMISSION_REQUIREMENTS = {
    "autoResponderChannel": ("view_channel", "send_messages"),
    "logsChannel": ("view_channel", "send_messages", "embed_links"),
    "welcomeChannel": ("view_channel", "send_messages", "attach_files"),
    "leaveChannel": ("view_channel", "send_messages"),
    "modMailChannel": ("view_channel", "send_messages", "embed_links", "create_public_threads"),
}

PERMISSION_LABELS = {
    "view_channel": "View Channel",
    "send_messages": "Send Messages",
    "embed_links": "Embed Links",
    "attach_files": "Attach Files",
    "create_public_threads": "Create Public Threads",
}

if dbEnabled:
    mongo_client = MongoClient(env("DB_URI"))
    db = mongo_client[env("DB_MAIN_COLLECTION_NAME", "bot")]
    moderationLogs = db["modLogs"]
    activeBans = db["activeBans"]
    server_settings_collection = db["server_settings"]

async def checkOwner(interaction: discord.Interaction):
    if interaction.user == interaction.guild.owner or interaction.user.guild_permissions.administrator or (interaction.user.id == int(env("OWNER_ID", 0)) and env("TESTING", "false").lower() == "true"):
        return True
    else:
        await interaction.response.send_message(embed=errorEmbed(title="Insufficient Permissions", description="Only administrators and the server owner has access to this command!"))
        return False
    
async def sendSaveError(response: discord.Message, error: str):
    await response.edit(content=None, embed=errorEmbed(title="Settings", description=f"We were unable to save your server settings.\n\nError: {str(error) or 'None'}"), view=None)
    return


async def _get_bot_member(interaction: discord.Interaction):
    if interaction.guild is None or interaction.client.user is None:
        return None

    bot_member = interaction.guild.get_member(interaction.client.user.id)
    if bot_member is not None:
        return bot_member

    try:
        return await interaction.guild.fetch_member(interaction.client.user.id)
    except Exception:
        return None


async def _check_channel_permissions(interaction: discord.Interaction, channel: discord.TextChannel, setting_key: str):
    bot_member = await _get_bot_member(interaction)
    if bot_member is None:
        return False, errorEmbed(
            title="Settings",
            description=f"I couldn't verify my permissions in {channel.mention} right now. Try again once the bot is fully available.",
        )

    required_permissions = CHANNEL_PERMISSION_REQUIREMENTS.get(setting_key, ("view_channel", "send_messages"))
    permissions = channel.permissions_for(bot_member)
    missing_permissions = [
        PERMISSION_LABELS.get(permission, permission.replace("_", " ").title())
        for permission in required_permissions
        if not getattr(permissions, permission, False)
    ]

    if missing_permissions:
        return False, errorEmbed(
            title="Settings",
            description=(
                f"The bot doesn't have permission to use {channel.mention}.\n\n"
                f"Missing permissions: {', '.join(missing_permissions)}"
            ),
        )

    return True, None


async def processInteraction(response: discord.Message, view: View):
    if view.value is None:
        # cancel request - response timed out
        await response.edit(content=None, embed=errorEmbed(title="Settings", description="Response timed out!\nYour settings were not saved."), view=None)
        return False
    elif view.value:
        # try to save settings, the user confirmed
        if dbEnabled == False or dbEnabled is None:
            await response.edit(content=None, embed=errorEmbed(title="Settings", description=f"We were unable to save your server settings.\n\nError: No database connected"), view=None)
            return False
        
        # let the user know that we're saving their settings
        await response.edit(content=None, embed=generalEmbed(title="Settings", description=f"Saving your options... Just give us a moment!"), view=None)
        # attempt to update
        return True
    else:
        # cancel request - user clicked cancel
        await response.edit(content=None, embed=generalEmbed(title="Settings", description="Your settings were not saved."), view=None)
        return False


class Confirm(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=25)
        self.value = None

    # when the confirm button is pressed, set the inner value to `True` and
    # stop the View from listening to more input.
    # we also send the user an ephemeral message that we're confirming their choice.
    @discord.ui.button(label='Confirm', style=discord.ButtonStyle.red)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        #await interaction.response.send_message('Confirming', ephemeral=True)
        self.value = True
        self.stop()

    # this one is similar to the confirmation button except sets the inner value to `False`
    @discord.ui.button(label='Cancel', style=discord.ButtonStyle.green)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        #await interaction.response.send_message('Cancelling', ephemeral=True)
        self.value = False
        self.stop()

class MultiRoleSelectView(View):
    def __init__(self):
        super().__init__(timeout=60)

        self.role_select = RoleSelect(
            placeholder="Select Server Moderators...",
            min_values=1,
            max_values=15,
        )
        self.role_select.callback = self.role_select_callback  # bind the callback properly
        self.add_item(self.role_select)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await checkOwner(interaction=interaction)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True

    async def role_select_callback(self, interaction: discord.Interaction):
        selected_roles = [role.name for role in self.role_select.values]
        view = Confirm()
        await interaction.response.send_message(
            embed=errorEmbed(title="Settings",
                             description=f"You are currently editing your server moderators.\nYou selected: {', '.join(selected_roles)}. Are these the roles you would like to register as moderators?"),
            ephemeral=True,
            view=view
        )
        await view.wait() # wait for their response

        response = await interaction.original_response()

        readyToSave = await processInteraction(response=response, view=view)

        if readyToSave:
            success, error = await updateSettings(guildId=interaction.guild_id, key="registeredModerators", data=[int(role.id) for role in self.role_select.values])

            # if theres an issue/error
            if not success:
                await sendSaveError(response=response, error=error)
                return
            
            # if the save was a success
            await response.edit(content=None, embed=successEmbed(title="Settings", description=f"Your selected moderator roles were saved! They may take up to 5 minutes to be applied.\n\n**You selected: {', '.join(selected_roles)}**"), view=None)
            await log_message(interaction.guild_id, interaction.client, f"{interaction.user.name} updated moderator roles to: {', '.join(selected_roles)}", "cmd")

# view settings command
@group.command(name="view", description="View your current server settings!")
async def view_settings(interaction: discord.Interaction):
    if await checkOwner(interaction=interaction):
        settings = await server_settings_collection.find_one({"guildId": int(interaction.guild_id)}) if dbEnabled else None

        if settings is None:
            await interaction.response.send_message(embed=generalEmbed(title="Settings", description="No settings found for this server!"), ephemeral=True)
            return
        
        logs_channel_id = settings.get("logsChannel")
        registered_mods_ids = settings.get("registeredModerators", [])

        logs_channel_mention = f"<#{logs_channel_id}>" if logs_channel_id else "Unset set"
        registered_mods_mentions = ", ".join([f"<@&{role_id}>" for role_id in registered_mods_ids]) if registered_mods_ids else "Unset set"

        embed = generalEmbed(title=f"Current Server Settings for {interaction.guild.name}", description="These are your current server settings. To change these settings, use the other subcommands under `/settings`")
        embed.add_field(name="Logs Channel", value=logs_channel_mention, inline=False)
        embed.add_field(name="Registered Moderator Roles", value=registered_mods_mentions, inline=False)
        embed.add_field(name="Auto-Responder Channel", value=f"<#{settings.get('autoResponderChannel')}>" if settings.get('autoResponderChannel') else "Unset", inline=False)
        embed.add_field(name="Welcome Channel", value=f"<#{settings.get('welcomeChannel')}>" if settings.get('welcomeChannel') else "Unset", inline=False)
        embed.add_field(name="Leave Channel", value=f"<#{settings.get('leaveChannel')}>" if settings.get('leaveChannel') else "Unset", inline=False)
        embed.add_field(name="Mod Mail Channel", value=f"<#{settings.get('modMailChannel')}>" if settings.get('modMailChannel') else "Unset", inline=False)
        embed.add_field(name="Allow Anonymous Mod Mail", value=str(settings.get('allowAnonymousModMail', False)), inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

# set moderators command
@group.command(name="moderators", description="Define your moderators.")
async def set_moderators(interaction: discord.Interaction):
    if await checkOwner(interaction=interaction):
        view = MultiRoleSelectView()
        await interaction.response.send_message(embed=generalEmbed(title="Settings", description="Select your moderator roles using the dropdown below this message.\n\n***Note: This will overwrite your current selected moderator settings!***"), view=view, ephemeral=True)


@group.command(name="auto-responder", description=f"Set up which channel the auto-responder can use.")
@app_commands.describe(channel="The channel which the auto-responder will work in")
async def set_auto_responder_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    if await checkOwner(interaction=interaction):
        view = Confirm()
        await interaction.response.send_message(embed=generalEmbed(title="Settings", description=f"This will update where the auto-responder will work.\n\nAre you sure this is the channel you want to select?\n***You selected: {channel.mention}***"), view=view, ephemeral=True)

        await view.wait() # wait for their response

        response = await interaction.original_response()
        
        readyToSave = await processInteraction(response=response, view=view)

        if readyToSave:

            can_use_channel, channel_error = await _check_channel_permissions(interaction=interaction, channel=channel, setting_key="autoResponderChannel")
            if not can_use_channel:
                await response.edit(content=None, embed=channel_error, view=None)
                return

            # attempt to update
            success, error = await updateSettings(guildId=interaction.guild_id, key="autoResponderChannel", data=int(channel.id))

            # if theres an issue/error
            if not success:
                await sendSaveError(response=response, error=error)
                return

            # if the save was a success
            await response.edit(content=None, embed=successEmbed(title="Settings", description=f"Your selected auto-responder channel was saved! It may take up to 5 minutes to be applied.\n\n**You selected: {channel.mention}**"), view=None)
            await log_message(interaction.guild_id, interaction.client, f"{interaction.user.name} updated auto-responder channel to: {channel.mention}", "cmd")


@group.command(name="logs", description=f"Set up your logs channel.")
@app_commands.describe(channel="The channel where we will send server logs to")
async def set_logs_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    if await checkOwner(interaction=interaction):
        view = Confirm()
        await interaction.response.send_message(embed=generalEmbed(title="Settings", description=f"This will update where your logs are sent.\n\nAre you sure this is the channel you want to select?\n***You selected: {channel.mention}***"), view=view, ephemeral=True)

        await view.wait() # wait for their response

        response = await interaction.original_response()
        
        readyToSave = await processInteraction(response=response, view=view)

        if readyToSave:

            can_use_channel, channel_error = await _check_channel_permissions(interaction=interaction, channel=channel, setting_key="logsChannel")
            if not can_use_channel:
                await response.edit(content=None, embed=channel_error, view=None)
                return

            # attempt to update
            success, error = await updateSettings(guildId=interaction.guild_id, key="logsChannel", data=int(channel.id))

            # if theres an issue/error
            if not success:
                await sendSaveError(response=response, error=error)
                return

            # if the save was a success
            await response.edit(content=None, embed=successEmbed(title="Settings", description=f"Your selected log channel was saved! It may take up to 5 minutes to be applied.\n\n**You selected: {channel.mention}**"), view=None)
            await log_message(interaction.guild_id, interaction.client, f"{interaction.user.name} updated logs channel to: {channel.mention}", "cmd")
            await log_message(interaction.guild_id, interaction.client, f"Logs channel updated successfully!", "info")

@group.command(name="welcome", description=f"Set up your welcome message channel.")
@app_commands.describe(channel="The channel where we will send welcome messages to")
async def set_welcome_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    if await checkOwner(interaction=interaction):
        view = Confirm()
        await interaction.response.send_message(embed=generalEmbed(title="Settings", description=f"This will update where your welcome messages are sent.\n\nAre you sure this is the channel you want to select?\n***You selected: {channel.mention}***"), view=view, ephemeral=True)

        await view.wait() # wait for their response

        response = await interaction.original_response()
        
        readyToSave = await processInteraction(response=response, view=view)

        if readyToSave:

            can_use_channel, channel_error = await _check_channel_permissions(interaction=interaction, channel=channel, setting_key="welcomeChannel")
            if not can_use_channel:
                await response.edit(content=None, embed=channel_error, view=None)
                return

            # attempt to update
            success, error = await updateSettings(guildId=interaction.guild_id, key="welcomeChannel", data=int(channel.id))

            # if theres an issue/error
            if not success:
                await sendSaveError(response=response, error=error)
                return

            # if the save was a success
            await response.edit(content=None, embed=successEmbed(title="Settings", description=f"Your selected welcome channel was saved! It may take up to 5 minutes to be applied.\n\n**You selected: {channel.mention}**"), view=None)
            await log_message(interaction.guild_id, interaction.client, f"{interaction.user.name} updated welcome channel to: {channel.mention}", "cmd")


@group.command(name="leave", description=f"Set up your leave message channel.")
@app_commands.describe(channel="The channel where we will send leave messages to")
async def set_leave_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    if await checkOwner(interaction=interaction):
        view = Confirm()
        await interaction.response.send_message(embed=generalEmbed(title="Settings", description=f"This will update where your leave messages are sent.\n\nAre you sure this is the channel you want to select?\n***You selected: {channel.mention}***"), view=view, ephemeral=True)

        await view.wait() # wait for their response

        response = await interaction.original_response()
        
        readyToSave = await processInteraction(response=response, view=view)

        if readyToSave:

            can_use_channel, channel_error = await _check_channel_permissions(interaction=interaction, channel=channel, setting_key="leaveChannel")
            if not can_use_channel:
                await response.edit(content=None, embed=channel_error, view=None)
                return

            # attempt to update
            success, error = await updateSettings(guildId=interaction.guild_id, key="leaveChannel", data=int(channel.id))

            # if theres an issue/error
            if not success:
                await sendSaveError(response=response, error=error)
                return

            # if the save was a success
            await response.edit(content=None, embed=successEmbed(title="Settings", description=f"Your selected leave channel was saved! It may take up to 5 minutes to be applied.\n\n**You selected: {channel.mention}**"), view=None)
            await log_message(interaction.guild_id, interaction.client, f"{interaction.user.name} updated leave channel to: {channel.mention}", "cmd")


@group.command(name="mod-mail", description=f"Set up your mod mail channel")
@app_commands.describe(channel="The channel where we will send mod mail messages to")
async def set_mod_mail_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    if await checkOwner(interaction=interaction):
        view = Confirm()
        await interaction.response.send_message(embed=generalEmbed(title="Settings", description=f"This will update where your mod mail messages are sent.\n\nAre you sure this is the channel you want to select?\n***You selected: {channel.mention}***"), view=view, ephemeral=True)

        await view.wait() # wait for their response

        response = await interaction.original_response()
        
        readyToSave = await processInteraction(response=response, view=view)

        if readyToSave:

            can_use_channel, channel_error = await _check_channel_permissions(interaction=interaction, channel=channel, setting_key="modMailChannel")
            if not can_use_channel:
                await response.edit(content=None, embed=channel_error, view=None)
                return

            # attempt to update
            success, error = await updateSettings(guildId=interaction.guild_id, key="modMailChannel", data=int(channel.id))

            # if theres an issue/error
            if not success:
                await sendSaveError(response=response, error=error)
                return

            # if the save was a success
            await response.edit(content=None, embed=successEmbed(title="Settings", description=f"Your selected mod mail channel was saved! It may take up to 5 minutes to be applied.\n\n**You selected: {channel.mention}**"), view=None)
            await log_message(interaction.guild_id, interaction.client, f"{interaction.user.name} updated mod mail channel to: {channel.mention}", "cmd")


@group.command(name="allow-anonymous-modmail", description=f"Set whether mod mail messages can be sent anonymously or not.")
@app_commands.describe(allow_anonymous="Whether to allow anonymous mod mail messages")
async def set_allow_anonymous_modmail(interaction: discord.Interaction, allow_anonymous: bool):
    if await checkOwner(interaction=interaction):
        view = Confirm()
        await interaction.response.send_message(embed=generalEmbed(title="Settings", description=f"This will update the anonymous mod mail setting.\n\nAre you sure you want to {('allow' if allow_anonymous else 'disallow')} anonymous mod mail messages?"), view=view, ephemeral=True)

        await view.wait() # wait for their response

        response = await interaction.original_response()
        
        readyToSave = await processInteraction(response=response, view=view)

        if readyToSave:

            # attempt to update
            success, error = await updateSettings(guildId=interaction.guild_id, key="allowAnonymousModMail", data=bool(allow_anonymous))

            # if theres an issue/error
            if not success:
                await sendSaveError(response=response, error=error)
                return

            # if the save was a success
            await response.edit(content=None, embed=successEmbed(title="Settings", description=f"Your anonymous mod mail setting was saved! It may take up to 5 minutes to be applied.\n\n**You selected: {allow_anonymous}**"), view=None)
            await log_message(interaction.guild_id, interaction.client, f"{interaction.user.name} updated anonymous mod mail setting to: {allow_anonymous}", "cmd")

@group.command(name="reset", description="Reset all bot settings or a specific setting.")
@app_commands.describe(setting="Leave empty to reset all server settings")
@app_commands.choices(setting=RESET_SETTING_CHOICES)
async def reset_settings(interaction: discord.Interaction, setting: str | None = None):
    if await checkOwner(interaction=interaction):
        setting_label = "all server settings" if setting is None else f"the {RESET_SETTING_LABELS.get(setting, setting)} setting"
        view = Confirm()
        await interaction.response.send_message(
            embed=errorEmbed(
                title="Settings",
                description=f"This will reset {setting_label}.\n\nAre you sure you want to continue?",
            ),
            view=view,
            ephemeral=True,
        )

        await view.wait()

        response = await interaction.original_response()
        readyToSave = await processInteraction(response=response, view=view)

        if readyToSave:
            await log_message(interaction.guild_id, interaction.client, f"{interaction.user.name} reset {setting_label}", "cmd")

            success, error = await resetServerSettings(guildId=interaction.guild_id, key=setting)

            if not success:
                await sendSaveError(response=response, error=error)
                return

            if setting is None:
                await response.edit(
                    content=None,
                    embed=successEmbed(
                        title="Settings",
                        description="All server settings were reset successfully. It may take up to 5 minutes to be fully applied.",
                    ),
                    view=None,
                )

            else:
                await response.edit(
                    content=None,
                    embed=successEmbed(
                        title="Settings",
                        description=f"The {setting_label} was reset successfully. It may take up to 5 minutes to be fully applied.",
                    ),
                    view=None,
                )


def setup(bot_tree, guild=None):
    if guild:
        bot_tree.add_command(group, guild=guild)
    else:
        bot_tree.add_command(group)
