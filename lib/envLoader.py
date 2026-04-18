import os
from pathlib import Path

from dotenv import load_dotenv


if Path(".env").exists():
    load_dotenv(".env")


_ALIASES = {
    "BOT_TOKEN": ("DISCORD_TOKEN",),
    "GUILD_ID": ("MAIN_GUILD_ID",),
    "DB_URI": ("MONGO_URI",),
    "DB_MAIN_COLLECTION_NAME": ("MONGO_DB_NAME",),
}


def _coerce_value(value: str):
    lowered = value.lower()
    if lowered in ("true", "false"):
        return lowered == "true"
    if value.isdigit():
        return int(value)
    return value


def env(var_name,fallback_var=""):
    lookup_names = (var_name,) + _ALIASES.get(var_name, ())

    for lookup_name in lookup_names:
        var = os.getenv(lookup_name)
        if var:
            return _coerce_value(var)

    return fallback_var