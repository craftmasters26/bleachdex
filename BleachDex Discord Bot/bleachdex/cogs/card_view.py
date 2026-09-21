"""
/card view name: - preview the fully-rendered card (art + name +
                   stats, using its own template if it has one set via
                   /admin edit character/weapon) for a character or
                   weapon YOU'VE ALREADY CAUGHT. Only your own inventory
                   shows up here (and in the autocomplete) - it's not a
                   roster browser for stuff you haven't caught yet.
"""

import asyncio
import io

import discord
from discord import app_commands
from discord.ext import commands

from db import characters as ch, weapons as wp, collection as coll
from cards.render import render_card, weapon_stat_display
from factions import CHARACTER_FACTIONS, weapon_faction
from reiatsu import boosted_attack, boosted_hp


async def _owned_name_autocomplete(interaction: discord.Interaction, current: str):
    current = (current or "").lower()
    owned_char_ids = coll.get_owned_character_ids(interaction.user.id)
    owned_weapon_ids = coll.get_owned_weapon_ids(interaction.user.id)

    names = []
    for cid in owned_char_ids:
        c = ch.get_character(cid)
        if c and current in c.name.lower():
            names.append(c.name)
    for wid in owned_weapon_ids:
        w = wp.get_weapon(wid)
        if w and current in w.name.lower():
            names.append(w.name)
    names.sort()
    return [app_commands.Choice(name=n, value=n) for n in names[:25]]


class CardView(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    card_group = app_commands.Group(name="card", description="Preview cards")

    @card_group.command(name="view", description="Preview the fully-rendered card for a character or weapon you own")
    @app_commands.autocomplete(name=_owned_name_autocomplete)
    async def card_view(self, interaction: discord.Interaction, name: str):
        # Ownership check happens via these lookups themselves - they
        # only return a match if THIS user has actually caught it.
        owned_character = coll.find_owned_character_by_name(interaction.user.id, name)
        owned_weapon = None if owned_character else coll.find_owned_weapon_by_name(interaction.user.id, name)

        character = ch.get_character(owned_character.character_id) if owned_character else None
        weapon = wp.get_weapon(owned_weapon.weapon_id) if owned_weapon else None

        if character is None and weapon is None:
            await interaction.response.send_message(
                f"You don't own **{name}** yet — catch it first before you can view its card.",
                ephemeral=True,
            )
            return

        await interaction.response.defer()
        if character:
            png_bytes = await asyncio.to_thread(
                render_card,
                name=character.name, artwork_path=character.card_image_path or character.image_path,
                # Same card as any other - a Reiatsu copy (find_owned_character_by_name
                # prefers one) just shows its boosted HP / attack numbers.
                hp=boosted_hp(character.hp) if owned_character.is_reiatsu else character.hp,
                attack=boosted_attack(character.attack) if owned_character.is_reiatsu else character.attack,
                rarity=character.rarity,
                ability_name=character.ability_name, ability_description=character.ability_description,
                template_path=character.card_template_path,
                faction=CHARACTER_FACTIONS.get(character.name, ""),
            )
        else:
            hp, attack, hp_display, attack_display = weapon_stat_display(weapon)
            png_bytes = await asyncio.to_thread(
                render_card,
                name=weapon.name, artwork_path=weapon.card_image_path or weapon.image_path,
                hp=hp, attack=attack, rarity=weapon.rarity,
                hp_display=hp_display, attack_display=attack_display,
                ability_name=weapon.ability_name, ability_description=weapon.ability_description,
                template_path=weapon.card_template_path,
                faction=weapon_faction(weapon.name),
            )

        file = discord.File(io.BytesIO(png_bytes), filename="card.png")
        # Sent as a plain attachment (no discord.Embed wrapper) so it's
        # just the image itself in chat, not boxed in an embed frame.
        await interaction.followup.send(file=file)


async def setup(bot: commands.Bot):
    cog = CardView(bot)
    await bot.add_cog(cog)
    # card_group is registered automatically since it's a Group class
    # attribute on the Cog.