"""
/shop — 2 characters + 2 weapons, re-rolled every 24 hours. Buy with
KAN coins (earned via /daily).
"""

import discord
from discord import app_commands
from discord.ext import commands

from db import shop as sh, characters as ch, weapons as wp, players as pl


def _describe_slot(slot: sh.ShopSlot) -> tuple[str, str]:
    if slot.kind == "character":
        item = ch.get_character(slot.item_id)
        label = f"🧍 {item.name}" if item else "(removed)"
        detail = f"{item.tier.title()} · {item.hp} HP / {item.attack} ATK" if item else ""
    else:
        item = wp.get_weapon(slot.item_id)
        label = f"🗡️ {item.name}" if item else "(removed)"
        detail = f"{item.tier.title()} · +{item.attack_bonus} ATK" if item else ""
    return label, detail


def _format_remaining(seconds: int) -> str:
    hours, remainder = divmod(seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    return f"{hours}h {minutes}m"


class BuyButton(discord.ui.Button):
    def __init__(self, slot: sh.ShopSlot, label_text: str):
        super().__init__(label=f"Buy {label_text} ({slot.price} KAN)", style=discord.ButtonStyle.success)
        self.slot_number = slot.slot

    async def callback(self, interaction: discord.Interaction):
        try:
            slot = sh.buy_slot(interaction.user.id, self.slot_number)
        except sh.PurchaseError as e:
            await interaction.response.send_message(f"❌ {e}", ephemeral=True)
            return
        label, _ = _describe_slot(slot)
        await interaction.response.send_message(
            f"✅ Bought {label} for {slot.price} KAN! Check `/collection inventory`.",
            ephemeral=True,
        )


class ShopView(discord.ui.View):
    def __init__(self, slots: list[sh.ShopSlot]):
        super().__init__(timeout=300)
        for slot in slots:
            label, _ = _describe_slot(slot)
            self.add_item(BuyButton(slot, label.split(" ", 1)[-1]))


class Shop(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="shop", description="See today's shop — 2 characters + 2 weapons, buyable with KAN coins")
    async def shop(self, interaction: discord.Interaction):
        slots = sh.get_current_shop()
        balance = pl.get_balance(interaction.user.id)
        remaining = _format_remaining(sh.seconds_until_rotation())

        embed = discord.Embed(
            title="🛒 Today's Shop",
            description=f"Rotates in **{remaining}** · Your balance: **{balance} KAN**",
            color=discord.Color.gold(),
        )
        for slot in slots:
            label, detail = _describe_slot(slot)
            embed.add_field(name=f"{label} — {slot.price} KAN", value=detail or "\u200b", inline=True)

        if not slots:
            embed.description += "\n\nShop is empty — no characters/weapons in the roster yet."
            await interaction.response.send_message(embed=embed)
            return

        await interaction.response.send_message(embed=embed, view=ShopView(slots))


async def setup(bot: commands.Bot):
    await bot.add_cog(Shop(bot))
