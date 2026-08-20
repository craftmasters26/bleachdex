"""
/equip   - attach one of your owned weapons to one of your owned characters
/unequip - remove whatever weapon is attached to a character

The weapon's attack_bonus applies automatically in /battle once equipped.
"""

import discord
from discord import app_commands
from discord.ext import commands

from db import collection as coll


class Equip(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="equip", description="Equip a weapon onto one of your characters")
    async def equip(self, interaction: discord.Interaction, character_name: str, weapon_name: str):
        char_inst = coll.find_owned_character_by_name(interaction.user.id, character_name)
        if char_inst is None:
            await interaction.response.send_message(
                f"You don't own a character named **{character_name}**.", ephemeral=True
            )
            return
        weapon_inst = coll.find_owned_weapon_by_name(interaction.user.id, weapon_name)
        if weapon_inst is None:
            await interaction.response.send_message(
                f"You don't own a weapon named **{weapon_name}**.", ephemeral=True
            )
            return

        coll.equip_weapon(char_inst.id, weapon_inst.id, interaction.user.id)
        await interaction.response.send_message(
            f"🗡️ Equipped **{weapon_name}** onto **{character_name}**. "
            f"Its attack bonus now applies in battle."
        )

    @app_commands.command(name="unequip", description="Remove the weapon equipped on one of your characters")
    async def unequip(self, interaction: discord.Interaction, character_name: str):
        char_inst = coll.find_owned_character_by_name(interaction.user.id, character_name)
        if char_inst is None:
            await interaction.response.send_message(
                f"You don't own a character named **{character_name}**.", ephemeral=True
            )
            return
        coll.unequip_weapon(char_inst.id, interaction.user.id)
        await interaction.response.send_message(f"🗡️ Unequipped **{character_name}**'s weapon.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Equip(bot))
