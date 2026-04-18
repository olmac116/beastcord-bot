import discord
from discord import app_commands
from discord.ui import View, RoleSelect

from pymongo import AsyncMongoClient as MongoClient

from lib.logging import log
from lib.embeds import errorEmbed, successEmbed, generalEmbed
from lib.envLoader import env

group = app_commands.Group(name="settings", description="Bot Server settings")

dbEnabled = env("DB_URI", None) is not None

if dbEnabled:
    mongo_client = MongoClient(env("DB_URI"))
    db = mongo_client[env("DB_MAIN_COLLECTION_NAME", "Bot")]
    moderationLogs = db["modLogs"]
    activeBans = db["activeBans"]
    server_settings_collection = db["server_settings"]

async def checkOwner(interaction: discord.Interaction):
    if interaction.user == interaction.guild.owner or interaction.user.guild_permissions.administrator:
        return True
    else:
        await interaction.response.send_message(embed=errorEmbed(title="Insufficient Permissions", description="Only administrators and the server owner has access to this command!"))
        return False
    
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
    
async def sendSaveError(response: discord.Message, error: str):
   await response.edit(content=None, embed=errorEmbed(title="Settings", description=f"We were unable to save your server settings.\n\nError: {str(error) or "None"}"), view=None)
   return


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

        embed_description = f"**Logs Channel:** {logs_channel_mention}\n**Registered Moderator Roles:** {registered_mods_mentions}"
        await interaction.response.send_message(embed=generalEmbed(title="Current Server Settings", description=embed_description), ephemeral=True)

# set moderators command
@group.command(name="moderators", description="Define your moderators!")
async def set_moderators(interaction: discord.Interaction):
    if await checkOwner(interaction=interaction):
        view = MultiRoleSelectView()
        await interaction.response.send_message(embed=generalEmbed(title="Settings", description="Select your moderator roles using the dropdown below this message.\n\n***Note: This will overwrite your current selected moderator settings!***"), view=view, ephemeral=True)


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

            # attempt to update
            success, error = await updateSettings(guildId=interaction.guild_id, key="logsChannel", data=int(channel.id))

            # if theres an issue/error
            if not success:
                await sendSaveError(response=response, error=error)
                return

            # if the save was a success
            await response.edit(content=None, embed=successEmbed(title="Settings", description=f"Your selected log channel was saved! It may take up to 5 minutes to be applied.\n\n**You selected: {channel.mention}**"), view=None)


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

            # attempt to update
            success, error = await updateSettings(guildId=interaction.guild_id, key="modMailChannel", data=int(channel.id))

            # if theres an issue/error
            if not success:
                await sendSaveError(response=response, error=error)
                return

            # if the save was a success
            await response.edit(content=None, embed=successEmbed(title="Settings", description=f"Your selected mod mail channel was saved! It may take up to 5 minutes to be applied.\n\n**You selected: {channel.mention}**"), view=None)


def setup(bot_tree, guild=None):
    if guild:
        bot_tree.add_command(group, guild=guild)
    else:
        bot_tree.add_command(group)
