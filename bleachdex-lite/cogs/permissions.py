"""
Restricts admin-only slash commands (/character add, /weapon add, etc.)
to the specific Discord user IDs listed in ADMIN_USER_IDS in your .env.
Discord server "Administrator" permission is deliberately NOT enough
on its own - only IDs on that list can use these commands, even if
someone has full server admin rights.
"""

import os

import discord
from discord import app_commands

_raw_ids = os.environ.get("ADMIN_USER_IDS", "")
ADMIN_USER_IDS = {int(x) for x in _raw_ids.split(",") if x.strip().isdigit()}


def is_admin():
    def predicate(interaction: discord.Interaction) -> bool:
        return interaction.user.id in ADMIN_USER_IDS
    return app_commands.check(predicate)
