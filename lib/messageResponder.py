from pathlib import Path
import importlib
import re
from typing import Any

import discord
from lib.logging import logger
from lib.settingsLib import getSettings

PATTERN_CONFIG_PATH = Path(__file__).resolve().parent.parent / "static" / "message_patterns.yaml"


def _render_response(template: str, message: discord.Message) -> str:
    return template.format(
        mention=message.author.mention,
        username=message.author.display_name,
    )


def _load_pattern_responses() -> list[tuple[re.Pattern[str], str]]:
    if not PATTERN_CONFIG_PATH.exists():
        logger.warning("Pattern config not found: %s", PATTERN_CONFIG_PATH)
        return []

    try:
        yaml = importlib.import_module("yaml")
        with PATTERN_CONFIG_PATH.open("r", encoding="utf-8") as file:
            payload = yaml.safe_load(file) or {}
    except Exception as e:
        logger.error("Failed to load message patterns: %s", e)
        return []

    raw_patterns: list[dict[str, Any]] = payload.get("patterns", [])
    loaded_patterns: list[tuple[re.Pattern[str], str]] = []

    for item in raw_patterns:
        pattern_text = item.get("pattern")
        response_text = item.get("response")

        if not isinstance(pattern_text, str) or not isinstance(response_text, str):
            continue

        try:
            loaded_patterns.append((re.compile(pattern_text, re.IGNORECASE), response_text))
        except re.error as err:
            logger.warning("Invalid regex pattern %r: %s", pattern_text, err)

    return loaded_patterns


PATTERN_RESPONSES = _load_pattern_responses()


async def check_and_respond(message: discord.Message) -> bool:
    guild = message.guild
    if not guild:
        return False
    
    success, settings = await getSettings(guild.id)
    if not success:
        logger.error("Failed to load settings for guild %s: %s", guild.id, settings)
        return False

    if not isinstance(settings, dict):
        logger.warning("Unexpected settings type for guild %s: %s", guild.id, type(settings).__name__)
        return False

    auto_responder_channel_id = settings.get("autoResponderChannel", None)
    if auto_responder_channel_id and message.channel.id != auto_responder_channel_id:
        return False
    
    content = message.content or ""

    for pattern, response_template in PATTERN_RESPONSES:
        if not pattern.search(content):
            continue

        try:
            await message.reply(_render_response(response_template, message), mention_author=False)
            return True
        except discord.Forbidden:
            logger.warning(
                "Missing permission to reply in channel %s for guild %s",
                message.channel.id,
                guild.id,
            )
            return False
        except discord.HTTPException:
            logger.exception(
                "Failed to send auto-response in channel %s for guild %s",
                message.channel.id,
                guild.id,
            )
            return False

    return False
