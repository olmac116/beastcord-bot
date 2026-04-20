import discord
from discord import app_commands
from datetime import datetime, timezone
import secrets

from pymongo import AsyncMongoClient as MongoClient

from lib.envLoader import env
from lib.embeds import errorEmbed, generalEmbed, successEmbed
from lib.settingsLib import getSettings

dbEnabled = env("DB_URI", None) is not None

if dbEnabled:
    mongo_client = MongoClient(env("DB_URI"))
    db = mongo_client[env("DB_MAIN_COLLECTION_NAME", "bot")]
    server_settings_collection = db["server_settings"]
    modmail_tickets_collection = db["modmail_tickets"]

_listener_registered = False
_listener_client: discord.Client | None = None


async def _get_modmail_channel(guild_id: int) -> int | None:
    if not dbEnabled:
        return None

    settings = await server_settings_collection.find_one({"guildId": int(guild_id)})
    if not settings:
        return None

    return settings.get("modMailChannel")


async def _find_open_ticket_for_user(user_id: int):
    if not dbEnabled:
        return None
    return await modmail_tickets_collection.find_one({"userId": int(user_id), "open": True})


async def _find_open_ticket_for_thread(guild_id: int, thread_id: int):
    if not dbEnabled:
        return None
    return await modmail_tickets_collection.find_one(
        {"guildId": int(guild_id), "threadId": int(thread_id), "open": True}
    )


async def _is_moderator(message: discord.Message) -> bool:
    if not message.guild:
        return False

    member = message.author
    if not isinstance(member, discord.Member):
        return False

    if member.guild_permissions.administrator or member.guild_permissions.manage_messages:
        return True

    if not dbEnabled:
        return False

    settings = await server_settings_collection.find_one({"guildId": int(message.guild.id)})
    registered_mod_roles = settings.get("registeredModerators", []) if settings else []
    if not registered_mod_roles:
        return False

    member_role_ids = {role.id for role in member.roles}
    return any(int(role_id) in member_role_ids for role_id in registered_mod_roles)


async def _get_client_user(user_id: int):
    if _listener_client is None:
        return None

    user = _listener_client.get_user(int(user_id))
    if user is None:
        try:
            user = await _listener_client.fetch_user(int(user_id))
        except Exception:
            return None
    return user


async def _get_ticket_thread(ticket: dict):
    if _listener_client is None:
        return None

    thread = _listener_client.get_channel(int(ticket["threadId"]))
    if isinstance(thread, discord.Thread):
        return thread

    try:
        fetched = await _listener_client.fetch_channel(int(ticket["threadId"]))
        if isinstance(fetched, discord.Thread):
            return fetched
    except Exception:
        return None
    return None


async def _close_ticket(ticket: dict, closed_by: str):
    if not dbEnabled:
        return

    if not ticket.get("open", False):
        return

    await modmail_tickets_collection.update_one(
        {"_id": ticket["_id"]},
        {
            "$set": {
                "open": False,
                "closedAt": datetime.now(timezone.utc),
                "closedBy": closed_by,
            }
        },
    )

    thread = await _get_ticket_thread(ticket)
    if thread is not None:
        try:
            await thread.send(f"Ticket closed by {closed_by}.")
            await thread.edit(archived=True, locked=False)
        except Exception:
            pass

    user = await _get_client_user(int(ticket["userId"]))
    if user is not None:
        try:
            await user.send(
                embed=generalEmbed(
                    title="Modmail Closed",
                    description=f"Your modmail ticket was closed by {closed_by}.",
                    timestamp=datetime.now(timezone.utc),
                )
            )
        except Exception:
            pass


async def _handle_modmail_message(message: discord.Message):
    if not dbEnabled:
        return

    if message.author.bot:
        return

    if isinstance(message.channel, discord.Thread):
        await _handle_thread_message(message)
        return

    if isinstance(message.channel, discord.DMChannel):
        await _handle_user_dm_message(message)


async def _handle_thread_message(message: discord.Message):
    if message.guild is None or not isinstance(message.channel, discord.Thread):
        return

    ticket = await _find_open_ticket_for_thread(message.guild.id, message.channel.id)
    if not ticket:
        return

    if not await _is_moderator(message):
        return

    if message.content.strip().lower() == "!close":
        await _close_ticket(ticket, f"moderator {message.author}")
        return

    if not ticket.get("allowReplies", True):
        await message.add_reaction("🔕")
        return

    target_user_id = ticket.get("userId")
    if not target_user_id:
        return

    user = await _get_client_user(int(target_user_id))
    if user is None:
        await message.add_reaction("⚠️")
        return

    dm_embed = generalEmbed(
        title="New Modmail Response",
        description=message.content or "(No text provided)",
        timestamp=datetime.now(timezone.utc),
    )
    dm_embed.add_field(name="Server", value=message.guild.name, inline=True)
    dm_embed.add_field(name="Moderator", value=message.author.mention, inline=True)
    if message.attachments:
        attachment_links = "\n".join(att.url for att in message.attachments)
        dm_embed.add_field(name="Attachments", value=attachment_links[:1024], inline=False)

    try:
        await user.send(embed=dm_embed)
        await message.add_reaction("✅")
    except Exception:
        await message.add_reaction("⚠️")


async def _handle_user_dm_message(message: discord.Message):
    ticket = await _find_open_ticket_for_user(message.author.id)
    if not ticket:
        return

    if message.content.strip().lower() == "!close":
        await _close_ticket(ticket, f"user {message.author}")
        return

    if not ticket.get("allowReplies", True):
        await message.channel.send(
            embed=errorEmbed(
                title="Modmail",
                description="This ticket was created with replies disabled, so DM replies are not forwarded.",
            )
        )
        return

    thread = await _get_ticket_thread(ticket)
    if thread is None:
        await message.channel.send(
            embed=errorEmbed(
                title="Modmail",
                description="Your modmail thread could not be found. Please open a new ticket.",
            )
        )
        await _close_ticket(ticket, "system")
        return

    user_embed = generalEmbed(
        title="User Reply",
        description=message.content or "(No text provided)",
        timestamp=datetime.now(timezone.utc),
    )
    if ticket.get("anonymous", False):
        user_embed.add_field(name="User", value="Anonymous User", inline=False)
    else:
        user_embed.add_field(name="User", value=f"{message.author} ({message.author.id})", inline=False)
    if message.attachments:
        attachment_links = "\n".join(att.url for att in message.attachments)
        user_embed.add_field(name="Attachments", value=attachment_links[:1024], inline=False)

    await thread.send(embed=user_embed)
    await message.add_reaction("✅")


def _ensure_listener_registered(client: discord.Client):
    global _listener_registered, _listener_client
    _listener_client = client

    if _listener_registered:
        return

    client.add_listener(_handle_modmail_message, "on_message")
    _listener_registered = True


@app_commands.command(name="modmail", description="Send a private modmail message to server moderators")
@app_commands.describe(
    message="Your message for moderators",
    anonymous="Send this message anonymously in the modmail channel",
    allow_replies="Allow mods to reply and allow your DM replies to be forwarded",
)
async def modmail(
    interaction: discord.Interaction,
    message: str,
    anonymous: bool = False,
    allow_replies: bool = True,
):
    if interaction.guild is None:
        await interaction.response.send_message(
            embed=errorEmbed(
                title="Modmail",
                description="This command can only be used inside a server.",
            ),
            ephemeral=True,
        )
        return

    if not dbEnabled:
        await interaction.response.send_message(
            embed=errorEmbed(
                title="Modmail",
                description="Modmail is unavailable because no database is configured.",
            ),
            ephemeral=True,
        )
        return

    _ensure_listener_registered(interaction.client)

    existing_ticket = await _find_open_ticket_for_user(interaction.user.id)
    if existing_ticket:
        await interaction.response.send_message(
            embed=errorEmbed(
                title="Modmail",
                description="You already have an open modmail ticket. Use `!close` in DM with the bot to close it first.",
            ),
            ephemeral=True,
        )
        return

    modmail_channel_id = await _get_modmail_channel(interaction.guild.id)
    if not modmail_channel_id:
        await interaction.response.send_message(
            embed=errorEmbed(
                title="Modmail",
                description="This server has not configured a modmail channel yet. Ask an admin to use `/settings mod-mail`.",
            ),
            ephemeral=True,
        )
        return

    modmail_channel = interaction.guild.get_channel(int(modmail_channel_id))
    if not isinstance(modmail_channel, discord.TextChannel):
        await interaction.response.send_message(
            embed=errorEmbed(
                title="Modmail",
                description="The configured modmail channel is invalid. Ask an admin to set it again with `/settings mod-mail`.",
            ),
            ephemeral=True,
        )
        return
    
    if anonymous:
        settings = getSettings(interaction.guild.id)
        if settings.get("allowAnonymousModMail", False):
            await interaction.response.send_message(
                embed=errorEmbed(
                    title="Modmail",
                    description="This server does not allow anonymous modmail tickets. Please uncheck the 'Anonymous' option and try again.",
                ),
                ephemeral=True,
            )
        return
            

    ticket_embed = generalEmbed(
        title="New Modmail Ticket",
        description=message,
        timestamp=datetime.now(timezone.utc),
    )
    ticket_embed.add_field(name="Anonymous", value="Yes" if anonymous else "No", inline=True)
    ticket_embed.add_field(name="Replies Enabled", value="Yes" if allow_replies else "No", inline=True)
    
    if not anonymous:
        ticket_embed.add_field(name="User ID", value=str(interaction.user.id), inline=True)

    if anonymous:
        ticket_embed.add_field(name="Submitted By", value="Anonymous User", inline=False)
    else:
        ticket_embed.add_field(name="Submitted By", value=interaction.user.mention, inline=False)

    posted_message = await modmail_channel.send(embed=ticket_embed)

    thread_name = f"modmail-{secrets.token_hex(4)}"
    create_reason = (
        "Anonymous modmail ticket opened"
        if anonymous
        else f"Modmail ticket opened by {interaction.user} ({interaction.user.id})"
    )
    thread = await posted_message.create_thread(
        name=thread_name,
        auto_archive_duration=1440,
        reason=create_reason,
    )

    await modmail_tickets_collection.update_one(
        {"threadId": int(thread.id), "guildId": int(interaction.guild.id)},
        {
            "$set": {
                "threadId": int(thread.id),
                "messageId": int(posted_message.id),
                "channelId": int(modmail_channel.id),
                "guildId": int(interaction.guild.id),
                "userId": int(interaction.user.id),
                "anonymous": bool(anonymous),
                "allowReplies": bool(allow_replies),
                "open": True,
                "createdAt": datetime.now(timezone.utc),
            }
        },
        upsert=True,
    )

    await thread.send("Moderator thread opened. Use `!close` to close this ticket.")

    response_text = "Your modmail has been sent to the moderator team."
    if allow_replies:
        response_text += "\n\nReply to the bot in DMs to continue this ticket, or send `!close` to close it."
        response_text += "\n\nIf you do not receive mod replies, enable DMs for this server: Server name -> Privacy Settings -> Allow direct messages from server members."
    else:
        response_text += "\n\nReplies are disabled for this ticket."

    await interaction.response.send_message(
        embed=successEmbed(
            title="Modmail Sent",
            description=response_text,
        ),
        ephemeral=True,
    )


def setup(bot_tree, guild=None):
    if getattr(bot_tree, "client", None) is not None:
        _ensure_listener_registered(bot_tree.client)

    if guild:
        bot_tree.add_command(modmail, guild=guild)
    else:
        bot_tree.add_command(modmail)
