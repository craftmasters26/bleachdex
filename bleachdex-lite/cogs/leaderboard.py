"""
/leaderboard              - top players by total items owned
/leaderboard item:<name>  - top owners of one specific character/weapon
"""

from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from db import leaderboard as lb, characters as ch, weapons as wp

PAGE_SIZE = 10


class Leaderboard(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="leaderboard", description="See who owns the most cards overall, or of one item")
    @app_commands.describe(item="Optional: a specific character or weapon name to rank by")
    async def leaderboard(self, interaction: discord.Interaction, item: Optional[str] = None):
        await interaction.response.defer()

        if item:
            character = ch.find_character_by_name(item, enabled_only=False)
            weapon = None if character else wp.find_weapon_by_name(item, enabled_only=False)
            if character:
                entries = lb.character_leaderboard(character.id, limit=PAGE_SIZE)
                title = f"Leaderboard — {character.name}"
            elif weapon:
                entries = lb.weapon_leaderboard(weapon.id, limit=PAGE_SIZE)
                title = f"Leaderboard — {weapon.name}"
            else:
                await interaction.followup.send(f"No character or weapon named **{item}**.")
                return
        else:
            entries = lb.overall_leaderboard(limit=PAGE_SIZE)
            title = "Leaderboard — Overall"

        embed = discord.Embed(title=title, color=discord.Color.gold())
        if not entries:
            embed.description = "Nobody's caught anything yet."
        else:
            lines = []
            for rank, entry in enumerate(entries, start=1):
                user = self.bot.get_user(entry.discord_id)
                name = user.display_name if user else f"User {entry.discord_id}"
                lines.append(f"**Top {rank}** — {name} — Count: {entry.count}")
            embed.description = "\n".join(lines)

        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Leaderboard(bot))
