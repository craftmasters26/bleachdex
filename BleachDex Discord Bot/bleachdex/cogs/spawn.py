"""
The core spawn engine - this is the "main thing" of the bot.

/set spawn #channel   - (server admin) configure where Souls spawn
/admin spawn name:X amount:N - (BOT admin only, via ADMIN_USER_IDS,
                                 not server admin) force-spawn a
                                 specific character/weapon (name), or
                                 N random characters if name is left
                                 empty - posts right in the channel the
                                 command was run from, NOT the /set
                                 spawn channel

How the timing works (message-driven, not a background timer):
- Every message sent anywhere in the guild calls db/spawns.py's
  record_message(), which bumps a running message count and checks it
  against a readiness score:
      score = scaled_message_count + TIME_MULTIPLIER * minutes_elapsed
  A spawn only ever fires as the direct result of a message being
  sent - there's no polling loop, so a dead-quiet server never spawns
  into an empty room, and a burst of spam can't force an instant spawn
  either (message count is capped in the formula). See
  db/spawns.py's module docstring for the exact tuning. The spawn
  itself always POSTS in the configured /set spawn channel regardless
  of which channel triggered it.
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
from discord.ext import commands

from db import spawns as sp, characters as ch, weapons as wp, collection as coll, players as pl, achievements as ach
from db.connection import TIER_WEIGHTS
from logic.quotes import random_spawn_quote, random_roast_quote
from cogs.permissions import is_admin
from cogs.admin_group import admin_group
from discord_utils import resolve_emoji, kan_label
from reiatsu import REIATSU_EMOJI, REIATSU_PERK_TEXT, display_name
from factions import ADMIN_FACTION_CHOICES, ADMIN_FACTION_LABELS, character_in_faction

log = logging.getLogger("bleachdex.spawn")

# True  -> spawn is a normal embed (accent-colored left bar).
# False -> spawn is a plain message: quote as content, image as a bare
#          attachment (no colored bar/border at all, since that bar is
#          literally the embed's color property - the only way to make
#          it disappear entirely is to not use an embed).
SPAWN_USE_EMBED = False

# The accent color for the spawn embed's left bar. Picked to match the
# art's warm palette instead of Discord's stock "dark gold" so the bar
# blends with the card art sitting next to it rather than clashing.
SPAWN_ACCENT_COLOR = discord.Color(0xD98A3D)

SERVER_INVITE_LINK = "https://discord.gg/RNp5d5TGPD"

WHAT_IS_THIS_TEXT = (
    "This Soul is **{name}**.\n"
    "For giveaways, spawn parties, active community about the bot & such more, "
    "join the main server.\n"
    "{link}"
)


async def _spawn_name_autocomplete(interaction: discord.Interaction, current: str):
    """Combined autocomplete across BOTH characters and weapons, since
    the merged /admin spawn command accepts either kind of name."""
    current = (current or "").lower()
    char_matches = [c.name for c in ch.list_characters(enabled_only=True) if current in c.name.lower()]
    weapon_matches = [w.name for w in wp.list_weapons(enabled_only=True) if current in w.name.lower()]
    names = char_matches + weapon_matches
    return [app_commands.Choice(name=n, value=n) for n in names[:25]]


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


def _pick_random_character_in_faction(faction: str):
    """Same tier-weighted pick as _pick_random_collectible(), but ONLY
    characters (no weapons) belonging to `faction`. Returns
    ("character", char), or (None, None) if the faction has none."""
    pool = [c for c in ch.list_characters(enabled_only=True) if character_in_faction(c.name, faction)]
    if not pool:
        return None, None
    weights = [TIER_WEIGHTS.get(c.tier, 1) for c in pool]
    return "character", random.choices(pool, weights=weights, k=1)[0]


def _spawn_image_bytes(item) -> bytes:
    """Returns the raw artwork exactly as uploaded - no name, stats, or
    ability text drawn on top. This is a guessing game: if the card
    render (which prints the name right on the image) were used here,
    the answer would just be sitting in plain sight. The composited
    card with name/stats IS used elsewhere, once the item's already
    been claimed - see cards/render.py + packs.py and /card view."""
    from image_source import fetch_image_bytes
    buf = fetch_image_bytes(item.image_path)
    if buf is None:
        raise FileNotFoundError(f"Could not load or fetch image for {item.name!r}: {item.image_path}")
    return buf.getvalue()


def _seconds_since_spawn(spawn_id: int, interaction: discord.Interaction) -> float:
    """Seconds between the spawn message being posted and this catch."""
    spawn = sp.get_active_spawn(spawn_id)
    if spawn is None:
        return float("inf")
    if spawn.message_id:
        elapsed = (interaction.created_at - discord.utils.snowflake_time(spawn.message_id)).total_seconds()
        if 0 <= elapsed <= sp.CATCH_WINDOW_SECONDS + 30:
            return elapsed
    return max(0.0, time.time() - spawn.spawned_at)


class CatchModal(discord.ui.Modal, title="Catch this Soul!"):
    guess = discord.ui.TextInput(label="Name of this Soul", placeholder="Your guess", required=True)

    def __init__(self, view: "CatchView", spawn_id: int, correct_name: str, kind: str, item_id: int):
        super().__init__()
        self.view_ref = view
        self.spawn_id = spawn_id
        self.correct_name = correct_name
        self.kind = kind
        self.item_id = item_id

    async def on_submit(self, interaction: discord.Interaction):
        guess_clean = self.guess.value.strip().lower()

        if guess_clean not in _accepted_guesses(self.correct_name):
            # Public roast (Bleach-themed only), mentions the guesser.
            await interaction.response.send_message(
                f" {random_roast_quote(interaction.user.mention)}"
            )
            return

        won = sp.resolve_catch(self.spawn_id, interaction.user.id)
        if not won:
            spawn = sp.get_active_spawn(self.spawn_id)
            if spawn and spawn.caught_by is None and sp.is_catch_window_expired(spawn):
                await interaction.response.send_message(
                    " Too slow — the 5-minute catch window on this Soul already closed.",
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    " Someone else caught this Soul just before you.", ephemeral=True
                )
            return

        # How long the spawn had been up when this correct guess landed -
        # feeds the catch-speed achievements (Speed is a Burden / Sniper /
        # Fast Catcher). Measured from the spawn message's own timestamp to
        # the moment Discord received the modal submit, so it's not skewed
        # by bot lag.
        ach.record_catch_speed(interaction.user.id, _seconds_since_spawn(self.spawn_id, interaction))

        got_reiatsu = False
        if self.kind == "character":
            # 10% chance this copy is an awakened Reiatsu copy (reiatsu.py).
            instance_id = coll.grant_character(self.item_id, interaction.user.id)
            inst = coll.get_owned_character_instance(instance_id)
            got_reiatsu = bool(inst and inst.is_reiatsu)
            item = ch.get_character(self.item_id)
        else:
            coll.grant_weapon(self.item_id, interaction.user.id)
            item = wp.get_weapon(self.item_id)

        # Flat reward regardless of tier - tier-scaled rewards only
        # apply to pack pulls (see db/players.py's add_tier_coin_reward,
        # used in cogs/packs.py), not wild spawn catches.
        SPAWN_CATCH_BONUS = 50
        coin_reward = SPAWN_CATCH_BONUS
        new_balance = pl.add_coins(interaction.user.id, coin_reward)

        emoji_mention = resolve_emoji(interaction.client, item.emoji) if item else ""
        emoji_suffix = f" {emoji_mention}" if emoji_mention else ""
        coin_note = f" (+{coin_reward} {kan_label(interaction.client)})" if coin_reward else ""
        if got_reiatsu:
            await interaction.response.send_message(
                f" {interaction.user.mention} congratulations, you caught "
                f"**{display_name(self.correct_name, True)}**{emoji_suffix}!{coin_note}\n"
                f"{REIATSU_EMOJI} **Reiatsu awakened!** This copy fights with {REIATSU_PERK_TEXT}."
            )
        else:
            await interaction.response.send_message(
                f" {interaction.user.mention} congratulations, you caught "
                f"**{self.correct_name}**{emoji_suffix}!{coin_note}"
            )

        newly_earned = ach.check_and_grant(interaction.user.id)
        for a in newly_earned:
            await interaction.followup.send(
                f" {interaction.user.mention} unlocked the **{a.name}** achievement — {a.description}!"
            )

        # Disable (not remove) the buttons on the original spawn message so
        # it can't be caught twice - they stay visible, just greyed out and
        # unclickable, instead of vanishing entirely. The embed/content
        # itself stays untouched (no "Caught!" field added, no name/number
        # revealed there).
        for child in self.view_ref.children:
            child.disabled = True
        try:
            channel = interaction.client.get_channel(interaction.channel_id)
            spawn = sp.get_active_spawn(self.spawn_id)
            if channel and spawn and spawn.message_id:
                msg = await channel.fetch_message(spawn.message_id)
                await msg.edit(view=self.view_ref)
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

    # Discord only offers 5 usable button styles (blurple "primary", grey
    # "secondary", green "success", red "danger", link) plus "premium"
    # (gradient, purchase-only) - there is no custom hex color field on
    # buttons at all, in this or any Discord library, so a literal light
    # blue/orange isn't possible. primary (blurple) is the closest to
    # "blue" available; danger (red) is used below as the closest warm
    # tone to "orange" that Discord actually offers.
    @discord.ui.button(label="Catch Soul!", style=discord.ButtonStyle.primary)
    async def catch(self, interaction: discord.Interaction, button: discord.ui.Button):
        spawn = sp.get_active_spawn(self.spawn_id)
        if spawn and spawn.caught_by is not None:
            await interaction.response.send_message("This one's already been caught!", ephemeral=True)
            return
        if spawn and sp.is_catch_window_expired(spawn):
            await interaction.response.send_message(
                "Too slow — the 5-minute catch window on this Soul already closed.",
                ephemeral=True,
            )
            return
        await interaction.response.send_modal(
            CatchModal(self, self.spawn_id, self.correct_name, self.kind, self.item_id)
        )

    @discord.ui.button(label="What is this?", style=discord.ButtonStyle.danger)
    async def what_is_this(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            WHAT_IS_THIS_TEXT.format(name=self.correct_name, link=SERVER_INVITE_LINK),
            ephemeral=True,
        )

    async def on_timeout(self):
        # Only relevant if nobody caught it in time - if it WAS caught,
        # CatchModal.on_submit already disabled the buttons on the message.
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
        # No background loop anymore - spawns are purely message-driven.
        # See db/spawns.py's record_message()/spawn_readiness_score().

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

        # Reading may involve a blocking network fetch (image_source.py's
        # resolve_image_path downloads uncached GitHub-hosted images via
        # urllib, synchronously, with up to a 15s timeout). Running that
        # directly on the event loop freezes the ENTIRE bot - all guilds,
        # heartbeat included - for the duration, which is exactly what was
        # causing hangs/disconnects under repeated /admin spawn bursts.
        # Push it to a thread so the loop stays responsive.
        image_bytes = await asyncio.to_thread(_spawn_image_bytes, item)
        ext = Path(item.image_path).suffix or ".png"
        filename = f"spawn{ext}"
        file = discord.File(io.BytesIO(image_bytes), filename=filename)

        spawn_id = sp.create_active_spawn(guild_id, channel_id, kind, item.id)
        view = CatchView(spawn_id, item.name, kind, item.id)

        if SPAWN_USE_EMBED:
            embed = discord.Embed(description=random_spawn_quote(), color=SPAWN_ACCENT_COLOR)
            embed.set_image(url=f"attachment://{filename}")
            message = await channel.send(embed=embed, file=file, view=view)
        else:
            # No embed at all: the image is a bare attachment, so there's
            # no colored border/card around it - just the quote as plain
            # message text and the picture underneath, with the same two
            # buttons.
            content = random_spawn_quote()
            message = await channel.send(content=content, file=file, view=view)

        view.message = message
        sp.attach_message_id(spawn_id, message.id)
        return True

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return
        spawn_channel = sp.get_spawn_channel(message.guild.id)
        if not spawn_channel:
            return
        # Activity from ANY channel in the guild counts toward the spawn
        # meter - only where the spawn actually gets POSTED is locked to
        # the configured channel (see spawn_now() below). Previously this
        # required message.channel.id == spawn_channel, so only messages
        # sent in that one channel ever counted at all.

        # record_message() bumps the message count, computes
        # scaled_message_count + TIME_MULTIPLIER x minutes_elapsed, and
        # tells us right here whether that crossed the threshold - a
        # spawn only ever happens as the direct result of a message
        # being sent, never from a background timer alone. It also
        # already resets the counter itself the instant it returns
        # True, before any of the async work below runs - see its
        # docstring in db/spawns.py for why that matters (it's what
        # fixes messages sometimes spawning 2-3x in a row).
        ready = sp.record_message(message.guild.id)
        if not ready:
            return

        try:
            spawned = await self.spawn_now(message.guild.id, spawn_channel)
        except Exception:
            log.exception("Failed to spawn in guild %s channel %s", message.guild.id, spawn_channel)
            spawned = False
        # No reset_after_spawn() call here anymore - record_message()
        # already reset the counter before we even started spawning.

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
            f" Souls will now spawn in {channel.mention} (roughly every 5-10 minutes, "
            f"only when someone's actively chatting there).",
            ephemeral=True,
        )

    @admin_group.command(name="spawn", description="[Bot admin] Force-spawn something right now")
    @app_commands.describe(
        name="A specific character or weapon name to spawn (leave empty to spawn random characters)",
        amount="How many to spawn (default 1, max 20)",
        faction="Only spawn random characters from this faction (ignored if you give a name)",
    )
    @app_commands.choices(faction=[
        app_commands.Choice(name=label, value=value) for label, value in ADMIN_FACTION_CHOICES
    ])
    @app_commands.autocomplete(name=_spawn_name_autocomplete)
    @is_admin()
    async def admin_spawn(
        self,
        interaction: discord.Interaction,
        name: str = None,
        amount: app_commands.Range[int, 1, 20] = 1,
        faction: app_commands.Choice[str] = None,
    ):
        if interaction.guild is None:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return
        # Posts right here in the channel the command was run from -
        # NOT the /set spawn channel (that channel is only where the
        # automatic, message-driven spawns land).
        channel_id = interaction.channel_id

        if name is not None:
            # A specific name was given - look it up as a character first,
            # then as a weapon, so one command covers both (this replaces
            # the old separate /admin spawn character and /admin spawn
            # weapon commands).
            kind, item = "character", ch.find_character_by_name(name)
            if item is None:
                kind, item = "weapon", wp.find_weapon_by_name(name)
            if item is None:
                await interaction.response.send_message(
                    f"No character or weapon named **{name}**.", ephemeral=True
                )
                return
            await interaction.response.send_message(
                f"Spawning **{item.name}** x{amount}..." if amount > 1 else f"Spawning **{item.name}**...",
                ephemeral=True,
            )
            failures = 0
            for _ in range(amount):
                try:
                    await self.spawn_now(interaction.guild.id, channel_id, kind=kind, item=item)
                except Exception:
                    log.exception("admin_spawn: failed to spawn %s", item.name)
                    failures += 1
            if failures:
                await interaction.followup.send(
                    f" {failures}/{amount} spawn(s) failed (image fetch issue) - check logs.",
                    ephemeral=True,
                )
            return

        # A faction was picked (and no specific name) - spawn `amount`
        # random CHARACTERS from just that faction, tier-weighted like a
        # normal spawn. Weapons are left out: the option is about
        # characters.
        if faction is not None:
            label = ADMIN_FACTION_LABELS.get(faction.value, faction.name)
            kind, item = _pick_random_character_in_faction(faction.value)
            if item is None:
                await interaction.response.send_message(
                    f"There are no {label} characters available to spawn.", ephemeral=True
                )
                return
            await interaction.response.send_message(
                f"Spawning {amount} random {label} character{'s' if amount != 1 else ''}...",
                ephemeral=True,
            )
            failures = 0
            for i in range(amount):
                if i:
                    kind, item = _pick_random_character_in_faction(faction.value)
                try:
                    await self.spawn_now(interaction.guild.id, channel_id, kind=kind, item=item)
                except Exception:
                    log.exception("admin_spawn: failed to spawn %s", item.name)
                    failures += 1
            if failures:
                await interaction.followup.send(
                    f" {failures}/{amount} spawn(s) failed (image fetch issue) - check logs.",
                    ephemeral=True,
                )
            return

        # No name given - spawn `amount` random items from the SAME
        # weighted character+weapon pool the real message-driven spawns
        # use (_pick_random_collectible), so weapons actually show up
        # here too instead of only being reachable by naming one.
        await interaction.response.send_message(
            f"Spawning {amount} random item{'s' if amount != 1 else ''}...", ephemeral=True
        )
        failures = 0
        for _ in range(amount):
            kind, item = _pick_random_collectible()
            if item is None:
                await interaction.followup.send("No characters or weapons available to spawn.", ephemeral=True)
                return
            try:
                await self.spawn_now(interaction.guild.id, channel_id, kind=kind, item=item)
            except Exception:
                log.exception("admin_spawn: failed to spawn %s", item.name)
                failures += 1
        if failures:
            await interaction.followup.send(
                f" {failures}/{amount} spawn(s) failed (image fetch issue) - check logs.",
                ephemeral=True,
            )

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            msg = " Only the bot owner/admins listed in ADMIN_USER_IDS can use this command."
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
        else:
            raise error


async def setup(bot: commands.Bot):
    cog = Spawn(bot)
    await bot.add_cog(cog)
    # set_group has no parent, so it's a genuine top-level command of
    # this cog and discord.py binds it correctly on its own.
    # admin_spawn, however, was added via @admin_group.command(...) -
    # i.e. parented directly to admin_group instead of being a normal
    # top-level command of this cog - so, same as the matching note in
    # cogs/admin_add.py's setup(), it never gets bound to this cog by
    # discord.py's normal Cog machinery and fails at runtime without this.
    cog.admin_spawn.binding = cog