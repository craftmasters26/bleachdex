"""
BleachDex-Lite — single-process Discord bot.

Run with:  python3 bot.py

This replaces BallsDex's Docker+Postgres+Django stack with one Python
process + a local SQLite file, so it can run on hosts that only give
you a single process slot (Wispbyte, Render, a cheap VPS, your own PC).
"""

import asyncio
import logging

import discord
from discord.ext import commands

import config
from db.connection import init_db
from discord_utils import refresh_application_emoji_cache

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("bleachdex")

INTENTS = discord.Intents.default()
INTENTS.message_content = False  # not needed; we're slash-command only

EXTENSIONS = [
    "cogs.packs",
    "cogs.collection",
    "cogs.economy",
    "cogs.admin_add",
    "cogs.card_view",
    "cogs.trade",
    "cogs.battle",
    "cogs.equip",
    "cogs.team",
    "cogs.spawn",
    "cogs.admin_edit",
    "cogs.shop",
    "cogs.leaderboard",
    "cogs.about",
    "cogs.achievements",
    "cogs.emoji_admin",
]


class BleachDexBot(commands.Bot):
    def __init__(self, on_ready_extra=None):
        """
        on_ready_extra: optional zero-arg callable (sync or will be awaited
        if it returns a coroutine) run once, the first time on_ready fires.
        Used by server.py to start the web layer only after the bot is
        actually logged in — never called if you just run bot.py alone.
        """
        super().__init__(command_prefix="!", intents=INTENTS)
        self._on_ready_extra = on_ready_extra
        self._on_ready_extra_done = False

    async def setup_hook(self):
        init_db()
        for ext in EXTENSIONS:
            await self.load_extension(ext)
            log.info("Loaded %s", ext)
        # All bot-admin cogs attach their subgroups to admin_group via
        # parent= as soon as they're imported (above) - it only needs
        # to be added to the tree itself once, here, after everything's
        # loaded. See cogs/admin_group.py for why this lives here and
        # not in any individual cog's setup().
        from cogs.admin_group import admin_group
        self.tree.add_command(admin_group)
        synced = await self.tree.sync()
        log.info("Synced %d slash commands", len(synced))

    async def on_ready(self):
        log.info("Logged in as %s (id: %s)", self.user, self.user.id)
        await refresh_application_emoji_cache(self)
        if self._on_ready_extra and not self._on_ready_extra_done:
            self._on_ready_extra_done = True
            result = self._on_ready_extra()
            if asyncio.iscoroutine(result):
                await result


async def main():
    bot = BleachDexBot()
    async with bot:
        await bot.start(config.DISCORD_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())