"""/achievements - see which achievements you've earned and your progress toward the rest."""

import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional

from db import achievements as ach


class Achievements(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="achievements", description="See your earned achievements and progress")
    async def achievements(self, interaction: discord.Interaction, user: Optional[discord.User] = None):
        target = user or interaction.user
        earned = ach.earned_keys(target.id)

        lines = []
        for a in ach.ACHIEVEMENTS:
            if a.key in earned:
                lines.append(f" **{a.name}** — {a.description}")
            else:
                progress = a.progress_fn(target.id)
                lines.append(f" **{a.name}** — {a.description} ({progress}/{a.threshold})")

        embed = discord.Embed(
            title=f"🏅 {target.display_name}'s Achievements",
            description="\n".join(lines),
            color=discord.Color.gold(),
        )
        embed.set_footer(text=f"{len(earned)}/{len(ach.ACHIEVEMENTS)} earned")
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Achievements(bot))