import io
import os

import aiohttp
import discord
from PIL import Image, ImageDraw, ImageFont, ImageOps

from lib.logging import log
from lib.settingsLib import getSettings

WELCOME_BG_LOCAL_PATH = "static/images/welcome.png"
WELCOME_BG_FALLBACK_URL = "https://placehold.co/700x300"
WELCOME_IMAGE_SIZE = (700, 300)


async def _fetch_image_bytes(url: str):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as response:
                if response.status != 200:
                    return None
                return await response.read()
    except Exception:
        return None


def _load_font(size: int, bold: bool = False):
    font_paths = [
        "fonts/Montserrat-Bold.ttf" if bold else "fonts/Montserrat-Medium.ttf",
        # "fonts/Poppins-Bold.ttf" if bold else "fonts/Poppins-Regular.ttf",
        # "fonts/Arial-Bold.ttf" if bold else "fonts/Arial.ttf",
    ]

    for path in font_paths:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue

    return ImageFont.load_default()


def _draw_centered_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    y: int,
    font: ImageFont.FreeTypeFont,
    fill=(255, 255, 255, 255),
):
    text_bbox = draw.textbbox((0, 0), text, font=font)
    text_width = text_bbox[2] - text_bbox[0]
    x = (WELCOME_IMAGE_SIZE[0] - text_width) // 2

    draw.text(
        (x, y),
        text,
        font=font,
        fill=fill,
        stroke_width=6,
        stroke_fill=(0, 0, 0, 230),
    )


def _fit_bold_font(draw: ImageDraw.ImageDraw, text: str, start_size: int, min_size: int, max_width: int):
    size = start_size
    while size >= min_size:
        font = _load_font(size, bold=True)
        if draw.textlength(text, font=font) <= max_width:
            return font
        size -= 1
    return _load_font(min_size, bold=True)


def _truncate_for_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int):
    if draw.textlength(text, font=font) <= max_width:
        return text

    trimmed = text
    while len(trimmed) > 1 and draw.textlength(f"{trimmed}...", font=font) > max_width:
        trimmed = trimmed[:-1]
    return f"{trimmed}..."


async def generate_welcome_image(member: discord.Member):
    background = None
    if os.path.exists(WELCOME_BG_LOCAL_PATH):
        try:
            background = Image.open(WELCOME_BG_LOCAL_PATH).convert("RGBA")
        except Exception:
            background = None

    if background is None:
        bg_bytes = await _fetch_image_bytes(WELCOME_BG_FALLBACK_URL)
        if bg_bytes:
            try:
                background = Image.open(io.BytesIO(bg_bytes)).convert("RGBA")
            except Exception:
                background = None

    if background is None:
        background = Image.new("RGBA", WELCOME_IMAGE_SIZE, (35, 35, 45, 255))

    background = ImageOps.fit(background, WELCOME_IMAGE_SIZE)
    canvas = background.copy()

    overlay = Image.new("RGBA", WELCOME_IMAGE_SIZE, (0, 0, 0, 135))
    canvas = Image.alpha_composite(canvas, overlay)

    avatar_bytes = await member.display_avatar.replace(size=256).read()
    avatar = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
    avatar_size = 92
    avatar = ImageOps.fit(avatar, (avatar_size, avatar_size))

    avatar_mask = Image.new("L", (avatar_size, avatar_size), 0)
    avatar_mask_draw = ImageDraw.Draw(avatar_mask)
    avatar_mask_draw.ellipse((0, 0, avatar_size - 1, avatar_size - 1), fill=255)

    avatar_x = (WELCOME_IMAGE_SIZE[0] - avatar_size) // 2
    avatar_y = 34
    canvas.paste(avatar, (avatar_x, avatar_y), avatar_mask)

    draw = ImageDraw.Draw(canvas)

    username_base_font = _load_font(54, bold=True)
    subtitle_base_font = _load_font(34, bold=True)

    username_text = _truncate_for_width(draw, member.name, username_base_font, max_width=640)
    subtitle_text = _truncate_for_width(draw, f"Welcome to {member.guild.name}", subtitle_base_font, max_width=640)

    username_font = _fit_bold_font(draw, username_text, start_size=54, min_size=30, max_width=640)
    subtitle_font = _fit_bold_font(draw, subtitle_text, start_size=34, min_size=20, max_width=640)

    _draw_centered_text(draw, username_text, 130, username_font)
    _draw_centered_text(draw, subtitle_text, 215, subtitle_font)

    output = io.BytesIO()
    canvas.convert("RGB").save(output, format="PNG")
    output.seek(0)
    return discord.File(output, filename="welcome.png")


async def send_welcome_message(member: discord.Member):
    success, saved_settings = await getSettings(member.guild.id)
    if not success:
        return False

    welcome_channel_id = saved_settings.get("welcomeChannel")
    if not welcome_channel_id:
        return False

    channel = member.guild.get_channel(int(welcome_channel_id))
    if channel is None:
        return False

    welcome_file = await generate_welcome_image(member)
    try:
        await channel.send(content=f"Welcome to {member.guild.name}, {member.mention}!", file=welcome_file)
        return True
    except discord.Forbidden:
        log(member.guild.id, f"Missing permission to send welcome message in channel {channel.id}")
        return False
    except discord.HTTPException as error:
        log(member.guild.id, f"Failed to send welcome message in channel {channel.id}: {error}")
        return False