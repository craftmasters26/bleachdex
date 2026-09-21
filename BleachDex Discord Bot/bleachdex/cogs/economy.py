"""
/daily - claim your daily KAN coins
/balance - check your KAN coin balance
"""

import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional

from db import players as pl
from discord_utils import kan_label


class Economy(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="daily", description="Claim your daily KAN coins")
    async def daily(self, interaction: discord.Interaction):
        try:
            new_balance = pl.claim_daily_coins(interaction.user.id)
        except pl.OnCooldown as e:
            await interaction.response.send_message(
                f"⏳ You already claimed today. Come back in "
                f"**{pl.format_remaining(e.seconds_remaining)}**.",
                ephemeral=True,
            )
            return

        kan = kan_label(interaction.client)
        await interaction.response.send_message(
            f"You claimed **{pl.DAILY_COIN_AMOUNT} {kan}**! "
            f"Balance: **{new_balance} {kan}**."
        )

    @app_commands.command(name="balance", description="Check your KAN coin balance")
    async def balance(self, interaction: discord.Interaction, user: Optional[discord.User] = None):
        target = user or interaction.user
        bal = pl.get_balance(target.id)
        kan = kan_label(interaction.client)
        await interaction.response.send_message(f"{target.display_name} has **{bal} {kan}**.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Economy(bot))