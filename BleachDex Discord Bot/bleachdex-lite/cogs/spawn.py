"""
The core spawn loop - this is the "main thing" of the bot.

/set spawn #channel   - (server admin) configure where Souls spawn
/spawn character/weapon name:X - (BOT admin only, via ADMIN_USER_IDS,
                                    not server admin) force-spawn
                                    anything immediately

How the timing works (mirrors the original BallsDex spawn behaviour):
- Every message sent in the configured channel marks that guild as
  "active" (db/spawns.py: mark_channel_active).
- A background loop wakes up on a random 5-10 minute cadence per
  guild. If the channel had activity since the last check, it spawns
  something and resets the flag. A dead-quiet channel never spawns
  into an empty room.
- The spawn is a message with the character/weapon image, a random
  flavor quote, a "Catch Soul!" button, and a "What is this?" button
  (ephemeral name reveal, for anyone who wants a hint). Catching opens
  a modal asking you to type the name - either the first OR last word
  of it is accepted (e.g. "Giriko Kutsuzawa" catches on "Giriko" or
  "Kutsuzawa"). First correct guess wins - see db/spawns.py's
  resolve_catch() for the race-safe claim logic. You only have
  db/spawns.py's CATCH_WINDOW_SECONDS (5 minutes) from spawn time to
  catch it - after that, both the button and a correct guess refuse.
"""

import asyncio
import io
import logging
import random
import time
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands, tasks

from db import spawns as sp, characters as ch, weapons as wp, collection as coll, players as pl, achievements as ach
from db.connection import TIER_WEIGHTS
from logic.quotes import random_spawn_quote, random_roast_quote
from cogs.permissions import is_admin
from cogs.admin_group import admin_group
from discord_utils import resolve_emoji

log = logging.getLogger("bleachdex.spawn")

SERVER_INVITE_LINK = "https://discord.gg/RNp5d5TGPD"

WHAT_IS_THIS_TEXT = (
    "This Soul is **{name}**.\n"
    "For giveaways, spawn parties, active community about the bot & such more, "
    "join the main server.\n"
    "{link}"
)


def _accepted_guesses(full_name: str) -> set[str]:
    """First name, last name, or the full name all count as a valid
    catch - e.g. 'Giriko Kutsuzawa' can be caught as 'Giriko',
    'Kutsuzawa', or the full name."""
    tokens = full_name.strip().split()
    accepted = {full_name.strip().lower()}
    if tokens:
        accepted.add(tokens[0].lower())
        accepted.add(tokens[-1].lower())
    return accepted


def _pick_random_collectible():
    """Weighted pick across BOTH characters and weapons combined, so
    either can spawn - matches the reference screenshots where devil
    fruits (our weapons) spawn the same way characters do."""
    all_chars = ch.list_characters(enabled_only=True)
    all_weapons = wp.list_weapons(enabled_only=True)
    pool = [("character", c) for c in all_chars] + [("weapon", w) for w in all_weapons]
    if not pool:
        return None, None
    weights = [TIER_WEIGHTS.get(item.tier, 1) for _, item in pool]
    kind, item = random.choices(pool, weights=weights, k=1)[0]
    return kind, item


def _spawn_image_bytes(item) -> bytes:
    """Returns the raw artwork exactly as uploaded - no name, stats, or
    ability text drawn on top. This is a guessing game: if the card
    render (which prints the name right on the image) were used here,
    the answer would just be sitting in plain sight. The composited
    card with name/stats IS used elsewhere, once the item's already
    been claimed - see cards/render.py + packs.py and /card view."""
    with open(item.image_path, "rb") as f:
        return f.read()


class CatchModal(discord.ui.Modal, title="Catch this Soul!"):
    guess = discord.ui.TextInput(label="Name of this Soul", placeholder="Your guess", required=True)

    def __init__(self, spawn_id: int, correct_name: str, kind: str, item_id: int):
        super().__init__()
        self.spawn_id = spawn_id
        self.correct_name = correct_name
        self.kind = kind
        self.item_id = item_id

    async def on_submit(self, interaction: discord.Interaction):
        guess_clean = self.guess.value.strip().lower()

        if guess_clean not in _accepted_guesses(self.correct_name):
            # Public roast (Bleach-themed only), mentions the guesser.
            await interaction.response.send_message(
                f"❌ {random_roast_quote(interaction.user.mention)}"
            )
            return

        won = sp.resolve_catch(self.spawn_id, interaction.user.id)
        if not won:
            spawn = sp.get_active_spawn(self.spawn_id)
            if spawn and spawn.caught_by is None and sp.is_catch_window_expired(spawn):
                await interaction.response.send_message(
                    "⌛ Too slow — the 5-minute catch window on this Soul already closed.",
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    "😢 Someone else caught this Soul just before you.", ephemeral=True
                )
            return

        if self.kind == "character":
            coll.grant_character(self.item_id, interaction.user.id)
            item = ch.get_character(self.item_id)
        else:
            coll.grant_weapon(self.item_id, interaction.user.id)
            item = wp.get_weapon(self.item_id)

        # Flat reward regardless of tier - tier-scaled rewards only
        # apply to pack pulls (see db/players.py's add_tier_coin_reward,
        # used in cogs/packs.py), not wild spawn catches.
        SPAWN_CATCH_BONUS = 30
        coin_reward = SPAWN_CATCH_BONUS
        new_balance = pl.add_coins(interaction.user.id, coin_reward)

        emoji_mention = resolve_emoji(interaction.client, item.emoji) if item else ""
        emoji_suffix = f" {emoji_mention}" if emoji_mention else ""
        coin_note = f" (+{coin_reward} KAN)" if coin_reward else ""
        await interaction.response.send_message(
            f"🎉 {interaction.user.mention} congratulations, you caught "
            f"**{self.correct_name}**{emoji_suffix}!{coin_note}"
        )

        newly_earned = ach.check_and_grant(interaction.user.id)
        for a in newly_earned:
            await interaction.followup.send(
                f"🏅 {interaction.user.mention} unlocked the **{a.name}** achievement — {a.description}!"
            )

        # Disable the buttons on the original spawn message so it can't be
        # caught twice - but leave the embed itself untouched (no "Caught!"
        # field added, no name/number revealed there).
        try:
            channel = interaction.client.get_channel(interaction.channel_id)
            spawn = sp.get_active_spawn(self.spawn_id)
            if channel and spawn and spawn.message_id:
                msg = await channel.fetch_message(spawn.message_id)
                await msg.edit(view=None)
        except (discord.NotFound, discord.Forbidden, IndexError):
            pass


class CatchView(discord.ui.View):
    def __init__(self, spawn_id: int, correct_name: str, kind: str, item_id: int):
        super().__init__(timeout=sp.CATCH_WINDOW_SECONDS)
        self.spawn_id = spawn_id
        self.correct_name = correct_name
        self.kind = kind
        self.item_id = item_id
        self.message: discord.Message | None = None

    @discord.ui.button(label="Catch Soul!", style=discord.ButtonStyle.primary)
    async def catch(self, interaction: discord.Interaction, button: discord.ui.Button):
        spawn = sp.get_active_spawn(self.spawn_id)
        if spawn and spawn.caught_by is not None:
            await interaction.response.send_message("This one's already been caught!", ephemeral=True)
            return
        if spawn and sp.is_catch_window_expired(spawn):
            await interaction.response.send_message(
                "⌛ Too slow — the 5-minute catch window on this Soul already closed.",
                ephemeral=True,
            )
            return
        await interaction.response.send_modal(
            CatchModal(self.spawn_id, self.correct_name, self.kind, self.item_id)
        )

    @discord.ui.button(label="What is this?", style=discord.ButtonStyle.secondary)
    async def what_is_this(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            WHAT_IS_THIS_TEXT.format(name=self.correct_name, link=SERVER_INVITE_LINK),
            ephemeral=True,
        )

    async def on_timeout(self):
        # Only relevant if nobody caught it in time - if it WAS caught,
        # CatchModal.on_submit already stripped the view off the message.
        spawn = sp.get_active_spawn(self.spawn_id)
        if spawn and spawn.caught_by is not None:
            return
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


class Spawn(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.spawn_loop.start()

    def cog_unload(self):
        self.spawn_loop.cancel()

    async def spawn_now(self, guild_id: int, channel_id: int, kind: str = None, item=None) -> bool:
        """Posts a spawn. If kind/item aren't given, picks randomly.
        Returns True if something was actually spawned."""
        if kind is None or item is None:
            kind, item = _pick_random_collectible()
        if item is None:
            return False

        channel = self.bot.get_channel(channel_id)
        if channel is None:
            return False

        image_bytes = _spawn_image_bytes(item)
        ext = Path(item.image_path).suffix or ".png"
        filename = f"spawn{ext}"
        file = discord.File(io.BytesIO(image_bytes), filename=filename)
        embed = discord.Embed(description=random_spawn_quote(), color=discord.Color.dark_gold())
        embed.set_image(url=f"attachment://{filename}")

        spawn_id = sp.create_active_spawn(guild_id, channel_id, kind, item.id)
        view = CatchView(spawn_id, item.name, kind, item.id)
        message = await channel.send(embed=embed, file=file, view=view)
        view.message = message
        sp.attach_message_id(spawn_id, message.id)

        # Sent as a separate follow-up message (not part of the embed),
        # matching the reference bot's spawn layout - a plain line
        # underneath, not inside the bordered embed.
        await channel.send(
            f"💡 If you want to contribute with art or help with code, "
            f"the main server is the place to go!"
        )
        return True

    @tasks.loop(seconds=60)
    async def spawn_loop(self):
        """
        Ticks every 60s just to check the clock, but each guild only
        actually gets checked on its own random 5-10 minute schedule
        (guild_settings.next_check_at). When a guild's check comes due:
        if its spawn channel had activity since the last check, spawn
        something there. Either way, roll a fresh 5-10 minute delay for
        the next check.
        """
        for guild_id in sp.list_configured_guilds():
            channel_id = sp.get_spawn_channel(guild_id)
            if channel_id is None or not sp.is_check_due(guild_id):
                continue

            had_activity = sp.has_activity_since_last_check(guild_id)
            sp.advance_next_check(guild_id, clear_activity=True)
            if not had_activity:
                continue

            try:
                await self.spawn_now(guild_id, channel_id)
            except Exception:
                log.exception("Failed to spawn in guild %s channel %s", guild_id, channel_id)

    @spawn_loop.before_loop
    async def before_spawn_loop(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return
        spawn_channel = sp.get_spawn_channel(message.guild.id)
        if spawn_channel and message.channel.id == spawn_channel:
            sp.mark_channel_active(message.guild.id)

    set_group = app_commands.Group(name="set", description="Server settings (admin)")

    @set_group.command(name="spawn", description="[Server admin] Set the channel where Souls spawn")
    @app_commands.default_permissions(administrator=True)
    async def set_spawn(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if not interaction.guild or not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "You need server Administrator permission to set the spawn channel.", ephemeral=True
            )
            return
        sp.set_spawn_channel(interaction.guild.id, channel.id)
        await interaction.response.send_message(
            f"✅ Souls will now spawn in {channel.mention} (roughly every 5-10 minutes, "
            f"only when someone's actively chatting there).",
            ephemeral=True,
        )

    spawn_group = app_commands.Group(name="spawn", description="[Bot admin] Force-spawn something right now", parent=admin_group)

    @spawn_group.command(name="character", description="[Bot admin] Force-spawn a specific character now")
    @is_admin()
    async def spawn_character(self, interaction: discord.Interaction, name: str):
        if interaction.guild is None:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return
        channel_id = sp.get_spawn_channel(interaction.guild.id)
        if channel_id is None:
            await interaction.response.send_message(
                "No spawn channel set yet — run `/set spawn` first.", ephemeral=True
            )
            return
        character = ch.find_character_by_name(name)
        if character is None:
            await interaction.response.send_message(f"No character named **{name}**.", ephemeral=True)
            return
        await interaction.response.send_message(f"Spawning **{character.name}**...", ephemeral=True)
        await self.spawn_now(interaction.guild.id, channel_id, kind="character", item=character)

    @spawn_group.command(name="weapon", description="[Bot admin] Force-spawn a specific weapon now")
    @is_admin()
    async def spawn_weapon(self, interaction: discord.Interaction, name: str):
        if interaction.guild is None:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return
        channel_id = sp.get_spawn_channel(interaction.guild.id)
        if channel_id is None:
            await interaction.response.send_message(
                "No spawn channel set yet — run `/set spawn` first.", ephemeral=True
            )
            return
        weapon = wp.find_weapon_by_name(name)
        if weapon is None:
            await interaction.response.send_message(f"No weapon named **{name}**.", ephemeral=True)
            return
        await interaction.response.send_message(f"Spawning **{weapon.name}**...", ephemeral=True)
        await self.spawn_now(interaction.guild.id, channel_id, kind="weapon", item=weapon)

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            msg = "🚫 Only the bot owner/admins listed in ADMIN_USER_IDS can use this command."
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
        else:
            raise error


async def setup(bot: commands.Bot):
    await bot.add_cog(Spawn(bot))
    # set_group and spawn_group are registered automatically since
    # they're Group class attributes on the Cog - see admin_add.py's
    # note for why NOT to also call bot.tree.add_command() here.