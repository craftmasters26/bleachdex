"""
/admin craftable - create a craftable character (name/image/hp/damage)
                    with a single-drop recipe. (The big multi-ingredient
                    recipe list is seeded by seed_craftables.py /
                    /admin seed craftables.)
/craft            - pick a category, then pick a craftable from it; every
                    ingredient (boss drops, weapon cards, character cards
                    / previous forms) is checked and spent together.

See db/craftables.py for the actual logic - this file is just the
Discord-facing wrapper, same split as merchant/boss.
"""

import asyncio
import io
import logging
from pathlib import Path
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from db import craftables as cf, achievements as ach
from cogs.permissions import is_admin
from cogs.admin_group import admin_group
from discord_utils import resolve_emoji
from cards.render import render_card
from reiatsu import REIATSU_EMOJI, REIATSU_PERK_TEXT, boosted_attack, boosted_hp, display_name

log = logging.getLogger("bleachdex.craft")

UPLOAD_DIR = Path(__file__).parent.parent / "admin" / "static" / "uploads" / "craftables"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


async def _save_craftable_image(attachment: discord.Attachment, name: str) -> str:
    ext = Path(attachment.filename).suffix or ".png"
    safe_name = "".join(c if c.isalnum() else "_" for c in name.lower())
    dest = UPLOAD_DIR / f"{safe_name}{ext}"
    await attachment.save(dest)
    return str(dest)


class CraftableAdminGroup(app_commands.Group):
    def __init__(self):
        super().__init__(
            name="craftable",
            description="[Bot admin] Create craft-only characters (never spawn/pack pullable)",
            parent=admin_group,
        )

    @app_commands.command(name="add", description="[Bot admin] Create a new craftable character and its recipe")
    @app_commands.describe(
        name="The craftable character's name",
        image="Its artwork",
        hp="HP stat",
        damage="Attack/damage stat",
        required_drop_name="Which boss drop is needed to craft it (must match a drop name exactly)",
        required_drop_qty="How many of that drop it costs",
    )
    @is_admin()
    async def add(
        self,
        interaction: discord.Interaction,
        name: str,
        image: discord.Attachment,
        hp: int,
        damage: int,
        required_drop_name: str,
        required_drop_qty: int,
    ):
        image_path = await _save_craftable_image(image, name)
        try:
            character = cf.add_craftable(
                name, image_path, hp, damage, required_drop_name, required_drop_qty
            )
        except cf.CraftError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return

        await interaction.response.send_message(
            f"**{character.name}** created — craftable for {required_drop_qty}x {required_drop_name}. "
            f"It will never appear in packs or wild spawns.",
            ephemeral=True,
        )

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        if isinstance(error, app_commands.CheckFailure):
            msg = "Only the bot owner/admins listed in ADMIN_USER_IDS can use this command."
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
        else:
            raise error


def _recipe_text(recipe: cf.Recipe) -> str:
    """'Sosuke Aizen + Kyoka Suigetsu + Hogyoku + 2x Jigokuchō' - the
    whole recipe, squeezed into a dropdown description (100 char cap)."""
    text = " + ".join(f"{i.qty}x {i.name}" if i.qty > 1 else i.name for i in recipe.ingredients)
    return text if len(text) <= 100 else text[:99] + "…"


def _group_by_category(craftables: list) -> dict[str, list]:
    groups: dict[str, list] = {}
    for character, recipe in craftables:  # already in creation order
        groups.setdefault(recipe.category or "Other", []).append((character, recipe))
    return groups


def _intro_embed(groups: dict[str, list]) -> discord.Embed:
    total = sum(len(v) for v in groups.values())
    return discord.Embed(
        title="Crafting",
        description=(
            f"{total} characters can be crafted from boss drops, weapons and other cards.\n"
            "Pick a category below to see the recipes."
        ),
        color=discord.Color.dark_gold(),
    )


def _category_embed(category: str, entries: list) -> discord.Embed:
    embed = discord.Embed(
        title=f"Crafting — {category}",
        description="\n".join(f"• **{character.name}**" for character, _ in entries)[:4000],
        color=discord.Color.dark_gold(),
    )
    embed.set_footer(text="Open the dropdown below to see each recipe and craft it")
    return embed


class CategorySelect(discord.ui.Select):
    def __init__(self, groups: dict[str, list], selected: str | None):
        options = [
            discord.SelectOption(
                label=name[:100],
                description=f"{len(entries)} craftable" + ("s" if len(entries) != 1 else ""),
                value=name,
                default=(name == selected),
            )
            for name, entries in list(groups.items())[:25]
        ]
        super().__init__(placeholder="Category", options=options, row=0)
        self.groups = groups

    async def callback(self, interaction: discord.Interaction):
        category = self.values[0]
        embed = _category_embed(category, self.groups[category])
        view = CraftView(interaction.user.id, self.groups, category)
        await interaction.response.edit_message(embed=embed, view=view)


class CraftSelect(discord.ui.Select):
    def __init__(self, owner_id: int, entries: list):
        options = [
            discord.SelectOption(
                label=character.name[:100],
                description=_recipe_text(recipe),
                value=str(character.id),
            )
            for character, recipe in entries[:25]
        ]
        super().__init__(placeholder="Craft", options=options, row=1)

    async def callback(self, interaction: discord.Interaction):
        character_id = int(self.values[0])

        # Acknowledge IMMEDIATELY. Discord gives a button/dropdown handler
        # only 3 seconds to respond; the craft itself plus rendering the
        # card (which can include a first-time artwork download) can take
        # longer, and the old code only replied at the very end - so the
        # user saw "The application didn't respond" even though the craft
        # had already succeeded and the card was already in their
        # inventory. Deferring buys up to 15 minutes; the result goes out
        # as a followup.
        await interaction.response.defer()

        try:
            # DB work runs off the event loop like everything else that can block.
            character, instance = await asyncio.to_thread(
                cf.craft, interaction.user.id, character_id
            )
        except cf.CraftError as e:
            await interaction.followup.send(str(e), ephemeral=True)
            return

        is_reiatsu = bool(instance and instance.is_reiatsu)
        emoji_mention = resolve_emoji(interaction.client, character.emoji)
        emoji_suffix = f" {emoji_mention}" if emoji_mention else ""
        # Public announcement line for every craft.
        announce = f"{interaction.user.mention} crafted **{display_name(character.name, is_reiatsu)}**{emoji_suffix}!"

        if is_reiatsu:
            embed = discord.Embed(
                title=f"{REIATSU_EMOJI} Reiatsu awakened! Crafted {display_name(character.name, True)}!",
                description=REIATSU_PERK_TEXT,
                color=discord.Color(0x46CDFF),
            )
        else:
            embed = discord.Embed(title=f"Crafted {character.name}!", color=discord.Color.dark_gold())

        # The card is already in the inventory at this point, so a render /
        # image-download hiccup must never swallow the announcement.
        file = None
        try:
            png_bytes = await asyncio.to_thread(
                render_card,
                name=character.name,
                artwork_path=character.card_image_path or character.image_path,
                # Normal card look; a Reiatsu copy just shows boosted HP / attack.
                hp=boosted_hp(character.hp) if is_reiatsu else character.hp,
                attack=boosted_attack(character.attack) if is_reiatsu else character.attack,
                rarity=character.rarity,
                ability_name=character.ability_name,
                ability_description=character.ability_description,
                template_path=character.card_template_path,
            )
            file = discord.File(io.BytesIO(png_bytes), filename="card.png")
            embed.set_image(url="attachment://card.png")
        except Exception:
            log.exception("Could not render card for craft of %s", character.name)

        if file is not None:
            await interaction.followup.send(content=announce, embed=embed, file=file)
        else:
            await interaction.followup.send(content=announce, embed=embed)

        newly_earned = ach.check_and_grant(interaction.user.id)
        for a in newly_earned:
            await interaction.followup.send(
                f"{interaction.user.mention} unlocked the **{a.name}** achievement — {a.description}!"
            )


class CraftView(discord.ui.View):
    def __init__(self, owner_id: int, groups: dict[str, list], selected: str | None = None):
        super().__init__(timeout=300)
        self.owner_id = owner_id
        self.add_item(CategorySelect(groups, selected))
        if selected is not None:
            self.add_item(CraftSelect(owner_id, groups[selected]))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "Run `/craft` yourself to craft from your own inventory.", ephemeral=True
            )
            return False
        return True


class Craft(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.craftable_admin = CraftableAdminGroup()

    @app_commands.command(name="craft", description="Craft a character from boss drops, weapons and cards")
    async def craft(self, interaction: discord.Interaction):
        craftables = cf.list_craftables()
        if not craftables:
            await interaction.response.send_message(
                "There's nothing craftable yet — an admin hasn't added any.", ephemeral=True
            )
            return

        groups = _group_by_category(craftables)
        view = CraftView(interaction.user.id, groups)
        await interaction.response.send_message(embed=_intro_embed(groups), view=view, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Craft(bot))