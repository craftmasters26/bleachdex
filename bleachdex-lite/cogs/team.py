"""
/team add - register your team of 3 owned characters (with whatever
weapons you've already equipped on them via /equip) for use in /battle.

Discord requires required options before optional ones, so the 3
characters come first, then the 3 optional weapons - weaponN equips
onto characterN if you pass it.
"""

import discord
from discord import app_commands
from discord.ext import commands

from db import collection as coll, teams


class TeamGroup(app_commands.Group):
    def __init__(self):
        super().__init__(name="team", description="Manage your 3-character battle team")

    @app_commands.command(
        name="add",
        description="Set your 3-character team (character1/2/3, optionally weapon1/2/3 to equip)",
    )
    async def add(
        self,
        interaction: discord.Interaction,
        character1: str,
        character2: str,
        character3: str,
        weapon1: str = "",
        weapon2: str = "",
        weapon3: str = "",
    ):
        names = [character1, character2, character3]
        weapons = [weapon1, weapon2, weapon3]
        user_id = interaction.user.id

        instances = []
        for name in names:
            inst = coll.find_owned_character_by_name(user_id, name)
            if inst is None:
                await interaction.response.send_message(
                    f"You don't own a character named **{name}**.", ephemeral=True
                )
                return
            instances.append(inst)

        seen_ids = set()
        for name, inst in zip(names, instances):
            if inst.id in seen_ids:
                await interaction.response.send_message(
                    f"**{name}** is already in another slot — each team slot "
                    f"needs a different character.",
                    ephemeral=True,
                )
                return
            seen_ids.add(inst.id)

        for inst, weapon_name in zip(instances, weapons):
            if not weapon_name:
                continue
            weapon_inst = coll.find_owned_weapon_by_name(user_id, weapon_name)
            if weapon_inst is None:
                await interaction.response.send_message(
                    f"You don't own a weapon named **{weapon_name}**.", ephemeral=True
                )
                return
            coll.equip_weapon(inst.id, weapon_inst.id, user_id)

        for slot, inst in enumerate(instances, start=1):
            teams.set_team_slot(user_id, slot, inst.id)

        lines = []
        for slot, (name, weapon_name) in enumerate(zip(names, weapons), start=1):
            weapon_note = f" (+ {weapon_name})" if weapon_name else ""
            lines.append(f"**Slot {slot}:** {name}{weapon_note}")

        embed = discord.Embed(
            title=f"⚔️ {interaction.user.display_name}'s team is set",
            description="\n".join(lines),
            color=discord.Color.teal(),
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="show", description="Show your current battle team")
    async def show(self, interaction: discord.Interaction):
        team = teams.get_team(interaction.user.id)
        if team is None:
            await interaction.response.send_message(
                "You haven't set a full 3-character team yet — use `/team add` first.",
                ephemeral=True,
            )
            return

        from db import characters as ch, weapons as wp

        lines = []
        for slot, inst in enumerate(team, start=1):
            char = ch.get_character(inst.character_id)
            weapon_note = ""
            if inst.equipped_weapon_instance_id:
                w_inst = coll.get_owned_weapon_instance(inst.equipped_weapon_instance_id)
                weapon = wp.get_weapon(w_inst.weapon_id) if w_inst else None
                if weapon:
                    weapon_note = f" (+ {weapon.name})"
            lines.append(
                f"**Slot {slot}:** {char.name} — {inst.health} HP / "
                f"{inst.attack} ATK{weapon_note}"
            )

        embed = discord.Embed(
            title=f"⚔️ {interaction.user.display_name}'s team",
            description="\n".join(lines),
            color=discord.Color.teal(),
        )
        await interaction.response.send_message(embed=embed)


class Team(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.bot.tree.add_command(TeamGroup())


async def setup(bot: commands.Bot):
    await bot.add_cog(Team(bot))
