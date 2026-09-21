"""
/pack daily - 3 pulls per day (refills at UTC midnight), any tier
/pack weekly - 1 pull per week, guaranteed Epic or Mythic
"""

import asyncio
import io

import discord
from discord import app_commands
from discord.ext import commands

from db import characters as ch, collection as coll, players as pl, achievements as ach
from cards.render import render_card
from discord_utils import resolve_emoji
from factions import CHARACTER_FACTIONS
from reiatsu import (
    REIATSU_EMOJI, REIATSU_PERK_TEXT, boosted_attack, boosted_hp, display_name,
)

REIATSU_COLOR = discord.Color(0x46CDFF)

TIER_COLORS = {
    "common": discord.Color.light_gray(),
    "uncommon": discord.Color.green(),
    "rare": discord.Color.blue(),
    "epic": discord.Color.purple(),
    "legendary": discord.Color.orange(),
    "mythic": discord.Color.gold(),
}

async def _character_card_embed(
    character, remaining_note: str, client: discord.Client, reiatsu: bool = False
) -> tuple[discord.Embed, discord.File]:
    png_bytes = await asyncio.to_thread(
        render_card,
        name=character.name,
        artwork_path=character.card_image_path or character.image_path,
        # Normal card look; a Reiatsu copy just shows boosted HP / attack.
        hp=boosted_hp(character.hp) if reiatsu else character.hp,
        attack=boosted_attack(character.attack) if reiatsu else character.attack,
        rarity=character.rarity,
        ability_name=character.ability_name,
        ability_description=character.ability_description,
        template_path=character.card_template_path,
        faction=CHARACTER_FACTIONS.get(character.name, ""),
    )
    file = discord.File(io.BytesIO(png_bytes), filename="card.png")

    char_emoji_mention = resolve_emoji(client, character.emoji)
    char_emoji = f" {char_emoji_mention}" if char_emoji_mention else ""
    if reiatsu:
        embed = discord.Embed(
            title=f"{REIATSU_EMOJI} Reiatsu awakened! You got {display_name(character.name, True)}!{char_emoji}",
            description=f"**{character.tier.title()}** • {REIATSU_PERK_TEXT}",
            color=REIATSU_COLOR,
        )
        embed.add_field(name="HP", value=f"{boosted_hp(character.hp)} (base {character.hp})")
        embed.add_field(name="Attack", value=f"{boosted_attack(character.attack)} (base {character.attack})")
    else:
        embed = discord.Embed(
            title=f"You got {character.name}!{char_emoji}",
            description=f"**{character.tier.title()}**",
            color=TIER_COLORS.get(character.tier, discord.Color.default()),
        )
        embed.add_field(name="HP", value=str(character.hp))
        embed.add_field(name="Attack", value=str(character.attack))
    embed.set_footer(text=remaining_note)
    embed.set_image(url="attachment://card.png")
    return embed, file


class PackGroup(app_commands.Group):
    def __init__(self):
        super().__init__(name="pack", description="Claim your character packs")

    @app_commands.command(name="daily", description="Claim a daily pack (3 per day)")
    async def daily(self, interaction: discord.Interaction):
        try:
            remaining = pl.claim_daily_pack_slot(interaction.user.id)
        except pl.OnCooldown as e:
            await interaction.response.send_message(
                f"You've used all your daily pulls. "
                f"Resets in **{pl.format_remaining(e.seconds_remaining)}**.",
                ephemeral=True,
            )
            return

        character = ch.pick_random_character()
        if character is None:
            await interaction.response.send_message(
                "There are no characters set up yet — ask an admin to add some "
                "with `/admin character add`.",
                ephemeral=True,
            )
            return

        # Rendering the card can involve a first-time image download
        # (see image_source.resolve_image_path) that can take several
        # seconds - well past Discord's 3-second window for an initial
        # response. Deferring immediately buys up to 15 minutes instead,
        # and the actual card gets sent via followup once it's ready.
        await interaction.response.defer()

        instance_id = coll.grant_character(character.id, interaction.user.id)
        inst = coll.get_owned_character_instance(instance_id)
        embed, file = await _character_card_embed(
            character, f"Daily pulls left today: {remaining}", interaction.client,
            reiatsu=bool(inst and inst.is_reiatsu),
        )
        await interaction.followup.send(embed=embed, file=file)

        newly_earned = ach.check_and_grant(interaction.user.id)
        for a in newly_earned:
            await interaction.followup.send(
                f"{interaction.user.mention} unlocked the **{a.name}** achievement — {a.description}!"
            )

    @app_commands.command(name="weekly", description="Claim your weekly pack (guaranteed Epic or better)")
    async def weekly(self, interaction: discord.Interaction):
        try:
            pl.claim_weekly_pack_slot(interaction.user.id)
        except pl.OnCooldown as e:
            await interaction.response.send_message(
                f"You already claimed your weekly pack. "
                f"Come back in **{pl.format_remaining(e.seconds_remaining)}**.",
                ephemeral=True,
            )
            return

        character = ch.pick_random_character(min_tier="epic")
        if character is None:
            await interaction.response.send_message(
                "There are no Epic or Mythic characters set up yet — ask an "
                "admin to add some with `/admin character add`.",
                ephemeral=True,
            )
            return

        # Same reasoning as /pack daily above - defer before the
        # potentially-slow render/download, send the result via followup.
        await interaction.response.defer()

        instance_id = coll.grant_character(character.id, interaction.user.id)
        inst = coll.get_owned_character_instance(instance_id)
        embed, file = await _character_card_embed(
            character, "Weekly pack: guaranteed Epic or better ", interaction.client,
            reiatsu=bool(inst and inst.is_reiatsu),
        )
        await interaction.followup.send(embed=embed, file=file)

        newly_earned = ach.check_and_grant(interaction.user.id)
        for a in newly_earned:
            await interaction.followup.send(
                f"{interaction.user.mention} unlocked the **{a.name}** achievement — {a.description}!"
            )


class Packs(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.bot.tree.add_command(PackGroup())


async def setup(bot: commands.Bot):
    await bot.add_cog(Packs(bot))