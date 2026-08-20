"""
/collection completion - shows % owned, owned vs missing, with each
character's custom emoji (if the admin set one) shown next to its name.
"""

from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from db import characters as ch, weapons as wp, collection as coll
from discord_utils import resolve_emoji


def _label(character: ch.Character, client: discord.Client) -> str:
    mention = resolve_emoji(client, character.emoji)
    prefix = f"{mention} " if mention else ""
    return f"{prefix}{character.name}"


def _weapon_label(weapon: wp.Weapon, client: discord.Client) -> str:
    mention = resolve_emoji(client, weapon.emoji)
    prefix = f"{mention} " if mention else ""
    return f"{prefix}{weapon.name}"


class CollectionGroup(app_commands.Group):
    def __init__(self):
        super().__init__(name="collection", description="View your character collection")

    @app_commands.command(name="completion", description="See your collection progress")
    async def completion(
        self, interaction: discord.Interaction, user: Optional[discord.User] = None
    ):
        target = user or interaction.user
        obtainable = ch.list_characters(enabled_only=True)
        owned_ids = coll.get_owned_character_ids(target.id)

        total = len(obtainable)
        owned_count = sum(1 for c in obtainable if c.id in owned_ids)
        percent = (owned_count / total * 100) if total else 0.0

        # "Missing" only lists things still obtainable via packs - a
        # delisted character shouldn't count against you. Shown as a
        # bare emoji grid (no names) so it's a "here's what's left to
        # find" teaser, not a spoiler - a character with no custom
        # emoji set falls back to a plain "?" placeholder so it still
        # shows up as a distinct slot in the grid.
        missing_emojis = []
        for c in obtainable:
            if c.id in owned_ids:
                continue
            mention = resolve_emoji(interaction.client, c.emoji)
            missing_emojis.append(mention if mention else "❓")

        # "Owned" always reflects everything you actually hold, INCLUDING
        # characters an admin has since removed from packs - removing a
        # character with /character remove never takes it away from
        # players who already caught it, so it must keep showing up here.
        owned_characters = [ch.get_character(cid) for cid in owned_ids]
        owned = [_label(c, interaction.client) for c in owned_characters if c is not None]

        embed = discord.Embed(
            title=f"{target.display_name}",
            description=f"BleachDex collectibles progression: **{percent:.1f}%**",
            color=discord.Color.gold(),
        )
        embed.add_field(
            name="Owned collectibles",
            value="\n".join(owned) if owned else "Nothing yet.",
            inline=False,
        )
        embed.add_field(
            name="Missing collectibles",
            value=" ".join(missing_emojis) if missing_emojis else "You caught them all! 🎉",
            inline=False,
        )
        embed.set_thumbnail(url=target.display_avatar.url)

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="inventory", description="List your owned characters and weapons by name")
    async def inventory(
        self, interaction: discord.Interaction, user: Optional[discord.User] = None
    ):
        target = user or interaction.user
        owned_chars = coll.list_owned_characters(target.id)
        owned_weapons = coll.list_owned_weapons(target.id)

        char_lines = []
        for inst in owned_chars:
            char = ch.get_character(inst.character_id)
            if char is None:
                continue
            equipped_note = ""
            if inst.equipped_weapon_instance_id:
                w_inst = coll.get_owned_weapon_instance(inst.equipped_weapon_instance_id)
                weapon = wp.get_weapon(w_inst.weapon_id) if w_inst else None
                if weapon:
                    equipped_note = f" *(equipped: {weapon.name})*"
            char_lines.append(
                f"{_label(char, interaction.client)} — {inst.health} HP / "
                f"{inst.attack} ATK{equipped_note}"
            )

        weapon_lines = []
        for inst in owned_weapons:
            weapon = wp.get_weapon(inst.weapon_id)
            if weapon is None:
                continue
            weapon_lines.append(f"{_weapon_label(weapon, interaction.client)} — +{inst.attack_bonus} ATK")

        embed = discord.Embed(title=f"{target.display_name}'s inventory", color=discord.Color.blurple())
        embed.add_field(
            name=f"Characters ({len(char_lines)})",
            value="\n".join(char_lines) if char_lines else "None yet.",
            inline=False,
        )
        embed.add_field(
            name=f"Weapons ({len(weapon_lines)})",
            value="\n".join(weapon_lines) if weapon_lines else "None yet.",
            inline=False,
        )
        await interaction.response.send_message(embed=embed)


class Collection(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.bot.tree.add_command(CollectionGroup())


async def setup(bot: commands.Bot):
    await bot.add_cog(Collection(bot))