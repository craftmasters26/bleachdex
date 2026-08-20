"""
/card view name: - preview the fully-rendered card (art + name +
                   stats, using its own template if it has one set via
                   /admin edit character/weapon) for any character or
                   weapon already on the roster.
"""

import io

import discord
from discord import app_commands
from discord.ext import commands

from db import characters as ch, weapons as wp
from cards.render import render_card


async def _name_autocomplete(interaction: discord.Interaction, current: str):
    current = (current or "").lower()
    names = [c.name for c in ch.list_characters(enabled_only=False) if current in c.name.lower()]
    names += [w.name for w in wp.list_weapons(enabled_only=False) if current in w.name.lower()]
    return [app_commands.Choice(name=n, value=n) for n in names[:25]]


class CardView(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    card_group = app_commands.Group(name="card", description="Preview cards")

    @card_group.command(name="view", description="Preview the fully-rendered card for a character or weapon")
    @app_commands.autocomplete(name=_name_autocomplete)
    async def card_view(self, interaction: discord.Interaction, name: str):
        character = ch.find_character_by_name(name, enabled_only=False)
        weapon = None if character else wp.find_weapon_by_name(name, enabled_only=False)

        if character is None and weapon is None:
            await interaction.response.send_message(f"No card found named **{name}**.", ephemeral=True)
            return

        await interaction.response.defer()
        if character:
            png_bytes = render_card(
                name=character.name, artwork_path=character.card_image_path or character.image_path,
                hp=character.hp, attack=character.attack, rarity=character.rarity,
                ability_name=character.ability_name, ability_description=character.ability_description,
                template_path=character.card_template_path,
            )
        else:
            png_bytes = render_card(
                name=weapon.name, artwork_path=weapon.card_image_path or weapon.image_path,
                hp=0, attack=weapon.attack_bonus, rarity=weapon.rarity,
                ability_name=weapon.ability_name, ability_description=weapon.ability_description,
                template_path=weapon.card_template_path,
            )

        file = discord.File(io.BytesIO(png_bytes), filename="card.png")
        embed = discord.Embed(color=discord.Color.dark_gold())
        embed.set_image(url="attachment://card.png")
        await interaction.followup.send(embed=embed, file=file)


async def setup(bot: commands.Bot):
    cog = CardView(bot)
    await bot.add_cog(cog)
    # card_group is registered automatically since it's a Group class
    # attribute on the Cog.