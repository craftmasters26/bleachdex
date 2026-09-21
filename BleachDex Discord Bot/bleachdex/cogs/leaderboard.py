"""
/leaderboard              - top players by total items owned
/leaderboard item:<name>  - top owners of one specific character/weapon/craftable
/leaderboard kan:True     - top players by KAN coins
"""

from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from db import leaderboard as lb, characters as ch, weapons as wp
from discord_utils import kan_label

TOP_N = 3


async def _item_autocomplete(interaction: discord.Interaction, current: str):
    current = (current or "").lower()
    # include_craftable_only=True: list_characters() hides craftables by default
    # (so packs/spawns never hand them out), which also hid them from this search.
    char_matches = [
        c.name for c in ch.list_characters(enabled_only=False, include_craftable_only=True)
        if current in c.name.lower()
    ]
    weapon_matches = [w.name for w in wp.list_weapons(enabled_only=False) if current in w.name.lower()]
    names = sorted(char_matches + weapon_matches)
    return [app_commands.Choice(name=n, value=n) for n in names[:25]]


class Leaderboard(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _display_name(self, interaction: discord.Interaction, discord_id: int) -> str:
        """Prefer the guild nickname (real 'display name'), fall back to
        the global username, and only show the raw ID as a last resort.
        bot.get_user() only checks the local cache, which is often empty
        for players who haven't interacted recently - fetch_member /
        fetch_user hit the API instead so this actually resolves."""
        if interaction.guild:
            member = interaction.guild.get_member(discord_id)
            if member is None:
                try:
                    member = await interaction.guild.fetch_member(discord_id)
                except discord.HTTPException:
                    member = None
            if member:
                return member.display_name

        user = self.bot.get_user(discord_id)
        if user is None:
            try:
                user = await self.bot.fetch_user(discord_id)
            except discord.HTTPException:
                user = None
        return user.display_name if user else f"User {discord_id}"

    @app_commands.command(name="leaderboard", description="See who owns the most cards or KAN, or the most of one item")
    @app_commands.describe(
        item="Optional: a specific character or weapon name to rank by",
        kan="Optional: set to True to rank players by how many KAN coins they have",
    )
    @app_commands.autocomplete(item=_item_autocomplete)
    async def leaderboard(self, interaction: discord.Interaction, item: Optional[str] = None, kan: bool = False):
        if kan and item:
            await interaction.response.send_message(
                "Pick either `item` or `kan`, not both.", ephemeral=True
            )
            return
        await interaction.response.defer()

        unit = ""
        empty_text = "Nobody's caught anything yet."

        if kan:
            entries = lb.kan_leaderboard(limit=TOP_N)
            my_rank = lb.kan_rank(interaction.user.id)
            title = "Leaderboard — KAN"
            unit = f" {kan_label(interaction.client)}"
            empty_text = "Nobody has any KAN yet."
        elif item:
            character = ch.find_character_by_name(item, enabled_only=False)
            weapon = None if character else wp.find_weapon_by_name(item, enabled_only=False)
            if character:
                entries = lb.character_leaderboard(character.id, limit=TOP_N)
                my_rank = lb.character_rank(character.id, interaction.user.id)
                title = f"Leaderboard — {character.name}"
            elif weapon:
                entries = lb.weapon_leaderboard(weapon.id, limit=TOP_N)
                my_rank = lb.weapon_rank(weapon.id, interaction.user.id)
                title = f"Leaderboard — {weapon.name}"
            else:
                await interaction.followup.send(f"No character or weapon named **{item}**.")
                return
        else:
            entries = lb.overall_leaderboard(limit=TOP_N)
            my_rank = lb.overall_rank(interaction.user.id)
            title = "Leaderboard — Overall"

        embed = discord.Embed(title=title, color=discord.Color.gold())
        if not entries:
            embed.description = empty_text
        else:
            medals = ["🥇", "🥈", "🥉"]
            lines = []
            for rank, entry in enumerate(entries, start=1):
                name = await self._display_name(interaction, entry.discord_id)
                lines.append(f"{medals[rank - 1]} **{name}** — {entry.count:,}{unit}")

            # Only add the invoker's own line if they're not already
            # shown above (i.e. outside the top N, or they own nothing
            # at all - my_rank is None in that second case).
            if my_rank and my_rank.rank > TOP_N:
                my_name = await self._display_name(interaction, interaction.user.id)
                lines.append("")  # the blank-line gap you asked for
                lines.append(f"**#{my_rank.rank}** — {my_name} — {my_rank.count:,}{unit}")

            embed.description = "\n".join(lines)

        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Leaderboard(bot))