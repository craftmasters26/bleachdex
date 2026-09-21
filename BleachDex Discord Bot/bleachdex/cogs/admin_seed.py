"""
/admin seed roster|bosses|craftables|emojis - [Bot admin] runs seed_roster.py's logic from
inside Discord, since single-process hosts (Wispbyte etc.) don't give
you a separate shell to run `python seed_roster.py` by hand.

Safe to run more than once - seed_roster.main() already skips
anything already in the database by name.
"""

import asyncio

import discord
from discord import app_commands
from discord.ext import commands

from cogs.permissions import is_admin
from cogs.admin_group import admin_group

import seed_roster
import seed_bossbattle
import seed_craftables
import seed_emojis
from discord_utils import refresh_application_emoji_cache


class AdminSeed(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    seed_group = app_commands.Group(
        name="seed", description="[Admin] Bulk-seed the roster", parent=admin_group
    )

    @seed_group.command(
        name="roster",
        description="[Admin] Add every character/weapon from the master roster (safe to re-run)",
    )
    @is_admin()
    async def seed_roster_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        result = await seed_roster.main()
        await interaction.followup.send(
            f"**Characters:** {result['added_c']} added, {result['updated_c']} updated, "
            f"{result['skipped_c']} already existed, {result['missing_c']} missing an image mapping.\n"
            f"**Weapons:** {result['added_w']} added, {result['updated_w']} updated, "
            f"{result['skipped_w']} already existed, {result['missing_w']} missing an image mapping.\n"
            f"**Owned weapon copies resynced to corrected boosts:** {result['resynced_w']}\n\n"
            f"Everything above is catchable/spawnable now. Card art still needs "
            f"`/admin edit character` / `/admin edit weapon` per entry, once card.py is filled in.",
            ephemeral=True,
        )

    @seed_group.command(
        name="bosses",
        description="[Admin] Add/update every preset boss battle boss (safe to re-run)",
    )
    @is_admin()
    async def seed_bosses_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        count = await asyncio.to_thread(seed_bossbattle.seed_bossbattle)
        await interaction.followup.send(
            f"Seeded/updated **{count}** boss battle bosses.", ephemeral=True
        )

    @seed_group.command(
        name="craftables",
        description="[Admin] Add/update every craftable character + recipe (safe to re-run)",
    )
    @is_admin()
    async def seed_craftables_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        result = await asyncio.to_thread(seed_craftables.seed_craftables)
        msg = f"**Craftables:** {result['created']} created, {result['updated']} updated."
        if result["skipped"]:
            shown = "\n".join(f"• {n}: {why}" for n, why in result["skipped"][:15])
            msg += f"\n**Skipped ({len(result['skipped'])}):**\n{shown}"
        await interaction.followup.send(msg[:1900], ephemeral=True)

    @seed_group.command(
        name="emojis",
        description="[Admin] Set every uploaded character/weapon emoji at once (safe to re-run)",
    )
    @is_admin()
    async def seed_emojis_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        # Pick up emoji uploaded to the Developer Portal since the bot started.
        await refresh_application_emoji_cache(interaction.client)
        result = await asyncio.to_thread(seed_emojis.seed_emojis)
        msg = (
            f"Emoji set on **{result['characters']}** characters and "
            f"**{result['weapons']}** weapons."
        )
        if result["missing"]:
            shown = "\n".join(f"• {kind}: {name}" for kind, name in result["missing"][:15])
            msg += f"\n**Not found in the database ({len(result['missing'])}):**\n{shown}"
        await interaction.followup.send(msg[:1900], ephemeral=True)

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        if isinstance(error, app_commands.CheckFailure):
            msg = "🚫 Only the bot owner/admins listed in ADMIN_USER_IDS can use this command."
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
        else:
            raise error


async def setup(bot: commands.Bot):
    cog = AdminSeed(bot)
    await bot.add_cog(cog)
    # See the matching note in cogs/admin_add.py's setup() - seed_group
    # has parent=admin_group, so its command never gets bound to this
    # cog by discord.py's normal Cog machinery and fails at runtime
    # without this.
    for command in cog.seed_group.walk_commands():
        command.binding = cog