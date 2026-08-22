"""
/pack daily - 3 pulls per day (refills at UTC midnight), any tier
/pack weekly - 1 pull per week, guaranteed Epic or Mythic
"""

import io

import discord
from discord import app_commands
from discord.ext import commands

from db import characters as ch, collection as coll, players as pl, achievements as ach
from cards.render import render_card
from discord_utils import resolve_emoji

TIER_COLORS = {
    "common": discord.Color.light_gray(),
    "uncommon": discord.Color.green(),
    "rare": discord.Color.blue(),
    "epic": discord.Color.purple(),
    "legendary": discord.Color.orange(),
    "mythic": discord.Color.gold(),
}

def _character_card_embed(
    character, remaining_note: str, client: discord.Client
) -> tuple[discord.Embed, discord.File]:
    png_bytes = render_card(
        name=character.name,
        artwork_path=character.card_image_path or character.image_path,
        hp=character.hp,
        attack=character.attack,
        rarity=character.rarity,
        ability_name=character.ability_name,
        ability_description=character.ability_description,
        template_path=character.card_template_path,
    )
    file = discord.File(io.BytesIO(png_bytes), filename="card.png")

    emoji = TIER_EMOJI.get(character.tier, "")
    char_emoji_mention = resolve_emoji(client, character.emoji)
    char_emoji = f" {char_emoji_mention}" if char_emoji_mention else ""
    embed = discord.Embed(
        title=f"🎁 You got {character.name}!{char_emoji}",
        description=f"{emoji} **{character.tier.title()}**",
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
                f"⏳ You've used all your daily pulls. "
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

        coll.grant_character(character.id, interaction.user.id)
        embed, file = _character_card_embed(
            character, f"Daily pulls left today: {remaining}", interaction.client
        )
        await interaction.response.send_message(embed=embed, file=file)

        newly_earned = ach.check_and_grant(interaction.user.id)
        for a in newly_earned:
            await interaction.followup.send(
                f"🏅 {interaction.user.mention} unlocked the **{a.name}** achievement — {a.description}!"
            )

    @app_commands.command(name="weekly", description="Claim your weekly pack (guaranteed Epic or better)")
    async def weekly(self, interaction: discord.Interaction):
        try:
            pl.claim_weekly_pack_slot(interaction.user.id)
        except pl.OnCooldown as e:
            await interaction.response.send_message(
                f"⏳ You already claimed your weekly pack. "
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

        coll.grant_character(character.id, interaction.user.id)
        embed, file = _character_card_embed(
            character, "Weekly pack: guaranteed Epic or better ", interaction.client
        )
        await interaction.response.send_message(embed=embed, file=file)

        newly_earned = ach.check_and_grant(interaction.user.id)
        for a in newly_earned:
            await interaction.followup.send(
                f"🏅 {interaction.user.mention} unlocked the **{a.name}** achievement — {a.description}!"
            )


class Packs(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.bot.tree.add_command(PackGroup())


async def setup(bot: commands.Bot):
    await bot.add_cog(Packs(bot))