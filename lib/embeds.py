import discord

def successEmbed(title: str, description: str = None, timestamp=None):
    embed = discord.Embed(title=title, description=description, color=discord.Color.green(), timestamp=timestamp)
    return embed

def errorEmbed(title: str, description: str = None, timestamp=None):
    embed = discord.Embed(title=title, description=description, color=discord.Color.red(), timestamp=timestamp)
    return embed

def generalEmbed(title: str, description: str = None, timestamp=None):
    embed = discord.Embed(title=title, description=description, color=discord.Color.blurple(), timestamp=timestamp)
    return embed

def alertEmbed(title: str, description: str = None, timestamp=None):
    embed = discord.Embed(title=title, description=description, color=discord.Color.orange(), timestamp=timestamp)
    return embed