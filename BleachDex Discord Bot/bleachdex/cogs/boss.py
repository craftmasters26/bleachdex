"""
Boss battles - solo preset fights seeded from Boss.txt (see
seed_bossbattle.py / db/bosses.py's PresetBoss section).

Everyone (not just admins) can click Challenge on a spawned boss - it
starts a private, ephemeral 10-round fight for that person alone,
against a fresh copy of the boss's HP, using their own /team roster
(auto-played as a whole team each round, same style as /battle).

A boss reaches a channel one of two ways:
  - /admin bossbattle - an admin manually spawns one right now, by name.
  - hourly_boss_spawn (this cog's background task) - once an hour, on
    the hour, GMT+8, a random enabled preset boss is posted into
    whichever channel is already configured for regular Soul spawns
    (the same /set spawn channel from cogs/spawn.py) - there's no
    separate boss channel to set up.

The spawn message itself is deliberately bare: no embed, no HP/DMG/drop
numbers up front - just the boss's name, its art as a plain attachment,
and a Challenge button. Stats only show up once you're actually in a
fight (the private round-by-round embed after you click Challenge).
"""

import asyncio
import datetime
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

from db import bosses as bs, teams, player_stats as pstats, achievements as ach, inventory as inv, custom_emoji as ce
from cogs.permissions import is_admin
from cogs.admin_group import admin_group
from discord_utils import resolve_emoji
from factions import ADMIN_FACTION_CHOICES, ADMIN_FACTION_LABELS, boss_categories_for_faction
from image_source import fetch_image_bytes

log = logging.getLogger("bleachdex.boss")

BOSSBATTLE_MAX_ROUNDS = 10
BOSSBATTLE_ROUND_DELAY_SECONDS = 1.5

# A boss spawned at 6:00 can't be challenged anymore once 7:00 rolls
# around - matches the hourly spawn cadence, so there's always exactly
# one challengeable boss window at a time (or none, between the hour
# mark and whenever the next one spawns).
BOSS_EXPIRY_SECONDS = 3600

# Hourly auto-spawn is pinned to GMT+8 regardless of where the bot's
# host machine actually lives - see Boss.hourly_boss_spawn() below.
GMT8 = datetime.timezone(datetime.timedelta(hours=8))


def _hp_bar(current: int, maximum: int, length: int = 20) -> str:
    filled = round(length * max(0, current) / maximum) if maximum else 0
    return "█" * filled + "░" * (length - filled)


async def _expire_boss_spawn_later(message: discord.Message, view: "BossChallengeView") -> None:
    """Waits out the rest of the boss's 1-hour window, then disables
    the Challenge button and edits the message to show the boss is
    gone - proactively, rather than only rejecting clicks after the
    fact. So a boss that spawned at 6am visibly stops being
    challengeable at 7am even if nobody happens to click it."""
    remaining = BOSS_EXPIRY_SECONDS - (time.time() - view.spawned_at)
    if remaining > 0:
        await asyncio.sleep(remaining)

    for child in view.children:
        child.disabled = True
    try:
        await message.edit(content=f"~~{message.content}~~\n*This boss has fled.*", view=view)
    except discord.HTTPException:
        pass  # message deleted, or channel/permissions changed - nothing to fix


async def _send_boss_spawn(channel: discord.abc.Messageable, boss: bs.PresetBoss) -> discord.Message:
    """Posts the bare spawn message for a preset boss: no embed, no
    stats, no drop rates - just the name, its art, and a Challenge
    button. Used by both the manual /admin bossbattle command and the
    hourly auto-spawn task, so the two look identical.

    The Challenge button stops working exactly BOSS_EXPIRY_SECONDS (1
    hour) after this is called - see BossChallengeView.spawned_at and
    _expire_boss_spawn_later above."""
    content = f"**{boss.name}** has appeared! Click Challenge to fight it with your /team."
    view = BossChallengeView(boss.id)

    file = None
    if boss.image_path:
        # Same blocking-network-call issue as spawn.py's image fetch -
        # fetch_image_bytes() does a synchronous urllib download, EVERY
        # time now (no cache). This runs inside hourly_boss_spawn's loop
        # over EVERY configured guild, so without threading it, one
        # slow boss image freezes the whole bot for every guild
        # processed that tick.
        resolved = await asyncio.to_thread(fetch_image_bytes, boss.image_path)
        if resolved:
            ext = Path(boss.image_path.split("?")[0]).suffix or ".png"
            file = discord.File(resolved, filename=f"boss{ext}")

    if file:
        message = await channel.send(content=content, file=file, view=view)
    else:
        message = await channel.send(content=content, view=view)

    asyncio.create_task(_expire_boss_spawn_later(message, view))
    return message


@dataclass
class _BossBattleFightState:
    boss: bs.PresetBoss
    boss_hp: int
    player_hp: int
    max_player_hp: int
    team_attack: int
    round_number: int = 0
    finished: bool = False
    victory: bool = False


def _bossbattle_round_embed(state: _BossBattleFightState, user: discord.abc.User) -> discord.Embed:
    title = "Victory!" if state.finished and state.victory else \
            "Defeat..." if state.finished else f"Round {state.round_number}/{BOSSBATTLE_MAX_ROUNDS}"
    embed = discord.Embed(
        title=f"{state.boss.name} — {title}",
        color=discord.Color.green() if state.finished and state.victory else
              discord.Color.red() if state.finished else discord.Color.orange(),
    )
    embed.add_field(
        name=state.boss.name,
        value=f"`{_hp_bar(state.boss_hp, state.boss.max_hp)}`\n{max(0, state.boss_hp):,}/{state.boss.max_hp:,} HP",
        inline=False,
    )
    embed.add_field(
        name=f"{user.display_name}'s team",
        value=f"`{_hp_bar(state.player_hp, state.max_player_hp)}`\n{max(0, state.player_hp):,}/{state.max_player_hp:,} HP",
        inline=False,
    )
    return embed


class BossChallengeView(discord.ui.View):
    """The single-button view posted on a boss spawn message. Every
    click starts a brand new, private, 10-round fight for that
    clicker alone - the spawn message itself has no shared state
    besides which preset boss it points at, when it spawned, and who's
    already beaten it (defeated_by), so it stays usable for the next
    challenger too, until BOSS_EXPIRY_SECONDS after spawning. A given
    player can keep retrying after a loss, but only gets to actually
    beat (and collect drops from) a given spawn once."""

    def __init__(self, boss_id: int):
        super().__init__(timeout=None)
        self.boss_id = boss_id
        self.spawned_at = time.time()
        self.defeated_by: set[int] = set()  # user IDs who've already won against THIS spawn

    @discord.ui.button(label="Challenge", style=discord.ButtonStyle.danger,
                        custom_id="bossbattle:challenge")
    async def challenge(self, interaction: discord.Interaction, button: discord.ui.Button):
        if time.time() - self.spawned_at >= BOSS_EXPIRY_SECONDS:
            # Belt-and-suspenders alongside _expire_boss_spawn_later: that
            # background task disables the button proactively once the
            # hour is up, but this catches the edge case of a click that
            # was already in flight right as the window closed.
            for child in self.children:
                child.disabled = True
            await interaction.response.edit_message(view=self)
            await interaction.followup.send(
                "This boss already fled — wait for the next one to spawn.", ephemeral=True
            )
            return

        if interaction.user.id in self.defeated_by:
            # One win per spawn: once you've beaten THIS boss, re-clicking
            # Challenge on the same message won't let you farm it again for
            # more drop rolls. A loss doesn't get added to defeated_by, so
            # losing is always retryable right up until the boss expires.
            await interaction.response.send_message(
                "You've already defeated this boss — wait for the next one to spawn.",
                ephemeral=True,
            )
            return

        boss = bs.get_preset_boss_by_id(self.boss_id)
        if boss is None or not boss.enabled:
            await interaction.response.send_message("This boss is no longer available.", ephemeral=True)
            return

        team = teams.get_team(interaction.user.id)
        if team is None:
            await interaction.response.send_message(
                "You need a full 3-character team to challenge a boss — use `/team add` first.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        # Imported here, not at module top, so cogs.boss and cogs.battle
        # never have to fight over which one finishes initializing
        # first at bot startup - this only actually runs once someone
        # clicks Challenge, long after both modules are fully loaded.
        from cogs.battle import _effective_attack, _effective_hp

        max_player_hp = sum(_effective_hp(inst) for inst in team)
        team_attack = sum(_effective_attack(inst) for inst in team)
        state = _BossBattleFightState(
            boss=boss, boss_hp=boss.max_hp, player_hp=max_player_hp,
            max_player_hp=max_player_hp, team_attack=team_attack,
        )

        await interaction.followup.send(embed=_bossbattle_round_embed(state, interaction.user), ephemeral=True)

        while not state.finished and state.round_number < BOSSBATTLE_MAX_ROUNDS:
            await asyncio.sleep(BOSSBATTLE_ROUND_DELAY_SECONDS)
            state.round_number += 1

            state.boss_hp -= state.team_attack
            if state.boss_hp <= 0:
                state.finished, state.victory = True, True
            else:
                state.player_hp -= state.boss.dmg_per_round
                if state.player_hp <= 0:
                    state.finished, state.victory = True, False

            if not state.finished and state.round_number >= BOSSBATTLE_MAX_ROUNDS:
                state.finished, state.victory = True, False  # boss survived 10 rounds -> defeat

            await interaction.edit_original_response(embed=_bossbattle_round_embed(state, interaction.user))

        if state.victory:
            self.defeated_by.add(interaction.user.id)
            pstats.increment(interaction.user.id, "bossbattle_wins")

            # Flawless Victory: the team's HP is one shared pool in this
            # fight, so to decide whether anyone "fell" the damage the boss
            # dealt is split evenly across the team - flawless means none of
            # the three would have reached 0 HP (i.e. their share of the
            # damage stayed under every character's own HP).
            damage_taken = max(0, state.max_player_hp - state.player_hp)
            if damage_taken / len(team) < min(_effective_hp(inst) for inst in team):
                pstats.increment(interaction.user.id, "flawless_wins")
            drops = bs.roll_preset_drops(boss)
            client = interaction.client
            if drops:
                lines = []
                for drop_name, emoji_key in drops:
                    inv.add(interaction.user.id, drop_name, 1)
                    # emoji_key is a lookup key like "bossbattle_drop:hollow_mask"
                    # (db/custom_emoji.py), not the numeric emoji ID itself -
                    # resolve_emoji() needs the actual ID, so it has to be
                    # looked up first. Passing emoji_key straight to
                    # resolve_emoji() (the previous bug here) always failed
                    # silently: it tried int("bossbattle_drop:hollow_mask"),
                    # got a ValueError, and resolve_emoji swallows that and
                    # returns "" - so the icon just never showed up, with no
                    # error anywhere to point at why.
                    emoji_id = ce.get_emoji_id(emoji_key) if emoji_key else ""
                    mention = resolve_emoji(client, emoji_id)
                    icon = f"{mention} " if mention else ""
                    lines.append(f"{icon}**{drop_name}**")
                await interaction.followup.send(
                    f"You defeated **{boss.name}** and got: {', '.join(lines)}!", ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"You defeated **{boss.name}** — no drops this time, but good fight!", ephemeral=True
                )

            newly_earned = ach.check_and_grant(interaction.user.id)
            for a in newly_earned:
                await interaction.followup.send(
                    f"You unlocked the **{a.name}** achievement — {a.description}!", ephemeral=True
                )
        else:
            pstats.increment(interaction.user.id, "bossbattle_losses")
            await interaction.followup.send(
                f"**{boss.name}** was too much this time — better luck next challenge.", ephemeral=True
            )


class Boss(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.hourly_boss_spawn.start()

    def cog_unload(self):
        self.hourly_boss_spawn.cancel()

    # Checked every minute (cheap - it's just a clock comparison per
    # configured guild) but only actually posts anything the instant the
    # GMT+8 clock ticks over to :00 - see the minute check below. Using a
    # 1-minute poll instead of tasks.loop(hours=1) means a bot restart
    # can't "skip" an hour by starting the loop late, and
    # last_boss_spawn_hour_key (persisted per guild) means it can't
    # double-spawn if the bot restarts twice within the same hour either.
    @tasks.loop(minutes=1)
    async def hourly_boss_spawn(self):
        now = datetime.datetime.now(GMT8)
        if now.minute != 0:
            return
        hour_key = now.strftime("%Y-%m-%d %H:00")

        for guild_id, channel_id, last_key in bs.list_hourly_spawn_targets():
            if last_key == hour_key:
                continue  # already spawned for this guild this hour

            boss = bs.pick_random_preset_boss()
            if boss is None:
                continue

            channel = self.bot.get_channel(channel_id)
            if channel is None:
                log.warning("Hourly boss spawn: channel %s not found for guild %s", channel_id, guild_id)
                continue

            try:
                await _send_boss_spawn(channel, boss)
            except discord.HTTPException:
                log.exception("Hourly boss spawn: failed to post in channel %s", channel_id)
                continue

            # Mark this guild done for the hour even if something above
            # only partially succeeded - avoids a broken channel
            # retrying every minute for the rest of the hour.
            bs.mark_boss_spawned(guild_id, hour_key)

    @hourly_boss_spawn.before_loop
    async def _before_hourly_boss_spawn(self):
        await self.bot.wait_until_ready()

    async def _preset_boss_autocomplete(self, interaction: discord.Interaction, current: str):
        current = (current or "").lower()
        return [
            app_commands.Choice(name=f"[{b.category}] {b.name}", value=b.name)
            for b in bs.list_preset_bosses(enabled_only=True)
            if current in b.name.lower() or current in b.category.lower()
        ][:25]

    @admin_group.command(name="bossbattle", description="[Bot admin] Spawn a preset boss battle in this channel")
    @app_commands.describe(
        boss="Which boss to spawn (leave empty to spawn a random boss)",
        amount="How many to spawn (default 1, max 20)",
        faction="Only spawn random bosses from this faction (ignored if you pick a boss)",
    )
    @app_commands.choices(faction=[
        app_commands.Choice(name=label, value=value) for label, value in ADMIN_FACTION_CHOICES
    ])
    @app_commands.autocomplete(boss=_preset_boss_autocomplete)
    @is_admin()
    async def bossbattle(
        self,
        interaction: discord.Interaction,
        boss: str = None,
        amount: app_commands.Range[int, 1, 20] = 1,
        faction: app_commands.Choice[str] = None,
    ):
        if boss is not None:
            the_boss = bs.get_preset_boss_by_name(boss)
            if the_boss is None:
                await interaction.response.send_message(f"No boss named **{boss}**.", ephemeral=True)
                return
            await interaction.response.send_message(
                f"Spawning **{the_boss.name}** x{amount}..." if amount > 1 else f"Spawning **{the_boss.name}**...",
                ephemeral=True,
            )
            failures = 0
            last_error = None
            for _ in range(amount):
                try:
                    await _send_boss_spawn(interaction.channel, the_boss)
                except Exception as e:
                    log.exception("bossbattle: failed to spawn %s", the_boss.name)
                    failures += 1
                    last_error = e
            if failures:
                await interaction.followup.send(
                    f" {failures}/{amount} spawn(s) failed "
                    f"({type(last_error).__name__}: {last_error}) - check logs.",
                    ephemeral=True,
                )
            return

        # No name given - spawn `amount` random enabled preset bosses,
        # each picked independently (same boss can come up more than once).
        # If a faction was picked, only bosses whose category belongs to
        # that faction are in the pool (see factions.BOSS_CATEGORY_FACTIONS).
        categories = None
        faction_label = ""
        if faction is not None:
            categories = boss_categories_for_faction(faction.value)
            faction_label = ADMIN_FACTION_LABELS.get(faction.value, faction.name)
            if bs.pick_random_preset_boss(categories) is None:
                await interaction.response.send_message(
                    f"There are no {faction_label} bosses available to spawn.", ephemeral=True
                )
                return
        what = f"random {faction_label} boss" if faction_label else "random boss"
        await interaction.response.send_message(
            f"Spawning {amount} {what}{'es' if amount != 1 else ''}...", ephemeral=True
        )
        failures = 0
        last_error = None
        for _ in range(amount):
            random_boss = bs.pick_random_preset_boss(categories)
            if random_boss is None:
                await interaction.followup.send("No preset bosses available to spawn.", ephemeral=True)
                return
            try:
                await _send_boss_spawn(interaction.channel, random_boss)
            except Exception as e:
                log.exception("bossbattle: failed to spawn %s", random_boss.name)
                failures += 1
                last_error = e
        if failures:
            await interaction.followup.send(
                f" {failures}/{amount} spawn(s) failed "
                f"({type(last_error).__name__}: {last_error}) - check logs.",
                ephemeral=True,
            )

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        if isinstance(error, app_commands.CheckFailure):
            msg = "Only the bot owner/admins listed in ADMIN_USER_IDS can use this command."
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
        else:
            raise error


async def setup(bot: commands.Bot):
    # Seed the preset bossbattle bosses right here, when this cog loads,
    # instead of relying on bot.py also being edited to call
    # seed_bossbattle() - this cog is already in EXTENSIONS on every
    # existing install, so this guarantees the Boss.txt list is in the
    # database the moment /admin bossbattle exists, with no separate
    # bot.py change required. Safe to run every startup - it's an
    # upsert-by-name, not an insert.
    from seed_bossbattle import seed_bossbattle
    seed_bossbattle()

    cog = Boss(bot)
    await bot.add_cog(cog)
    # /admin bossbattle is attached via @admin_group.command(...) - parented
    # directly to admin_group instead of being a normal top-level command of
    # this cog (same pattern as cogs/spawn.py's admin_spawn) - so it never
    # gets bound to this cog by discord.py's normal Cog machinery and fails
    # at runtime without this.
    cog.bossbattle.binding = cog