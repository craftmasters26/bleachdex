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
    "cogs.admin_seed",
    "cogs.card_view",
    "cogs.equip",
    "cogs.team",
    "cogs.spawn",
    "cogs.admin_edit",
    "cogs.leaderboard",
    "cogs.about",
    "cogs.achievements",
    "cogs.emoji_admin",
    "cogs.trade",    
    "cogs.boss",
    "cogs.merchant",
    "cogs.craft",
    "cogs.shop",
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

        if config.DEV_GUILD_ID:
            # DEV_GUILD_ID is a debugging aid only, for one server you use
            # while testing - it must never make the bot behave as if it
            # only serves one server. So: if it's set, we ONLY use it to
            # wipe out any leftover guild-scoped commands that an earlier
            # version of this file may have registered there (those would
            # otherwise sit alongside the global ones as confusing
            # duplicates in that one server). We do NOT copy commands into
            # that guild anymore - everything below is a normal global
            # sync, same as if this var were unset.
            guild = discord.Object(id=int(config.DEV_GUILD_ID))
            self.tree.clear_commands(guild=guild)
            await self.tree.sync(guild=guild)
            log.info(
                "Cleared any leftover guild-scoped commands from guild %s "
                "(BLEACHDEX_DEV_GUILD_ID is only used for cleanup now - "
                "commands sync globally, for every server)", config.DEV_GUILD_ID
            )

        synced = await self.tree.sync()
        log.info(
            "Synced %d slash commands globally, for every server this bot "
            "is in (can take up to an hour to fully propagate after a "
            "change)", len(synced)
        )

    async def on_ready(self):
        log.info("Logged in as %s (id: %s)", self.user, self.user.id)
        await refresh_application_emoji_cache(self)
        if self._on_ready_extra and not self._on_ready_extra_done:
            self._on_ready_extra_done = True
            result = self._on_ready_extra()
            if asyncio.iscoroutine(result):
                await result

        # Website sync bridge - mirrors SQLite into MongoDB every
        # MONGO_SYNC_INTERVAL_SECONDS so the BleachDex website's
        # leaderboard/dashboard/roster reflect real, live player data.
        # No-ops (just logs a warning once) if MONGODB_URI isn't set -
        # the bot and admin panel are fully unaffected either way.
        # Task is stashed on self so it isn't garbage-collected mid-run,
        # and only started once even if on_ready fires again after a
        # reconnect (self._mongo_sync_task already set).
        if not getattr(self, "_mongo_sync_task", None):
            from sync.mongo_sync import start_background_sync
            self._mongo_sync_task = start_background_sync(self)


async def main():
    bot = BleachDexBot()
    async with bot:
        await bot.start(config.DISCORD_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())