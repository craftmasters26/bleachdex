"""
/admin edit template   - [bot admin] replace the GLOBAL card template
                        background used for any card that doesn't have
                        its own template set.
/admin edit character  - [bot admin] build/update the actual card for a
                        character that was added with /admin character add:
                        its damage & health, an optional template
                        image just for this card, and optionally swap
                        the artwork.
/admin edit weapon     - same idea, for a weapon added with /admin weapon add.
/admin change character - [bot admin] swap an existing character's image
/admin change weapon    - [bot admin] swap an existing weapon's image
                        (kept as a quick shortcut; /admin edit character
                        /weapon can also do this via their image option)
"""

from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from db import characters as ch, weapons as wp
from db.connection import set_setting
from cogs.permissions import is_admin
from cogs.admin_group import admin_group

UPLOAD_DIR = Path(__file__).parent.parent / "admin" / "static" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
TEMPLATE_DIR = Path(__file__).parent.parent / "assets" / "backgrounds"
TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)


async def _save_attachment(attachment: discord.Attachment, dest: Path) -> str:
    await attachment.save(dest)
    return str(dest)


async def _character_autocomplete(interaction: discord.Interaction, current: str):
    current = (current or "").lower()
    matches = [c for c in ch.list_characters(enabled_only=False) if current in c.name.lower()]
    return [app_commands.Choice(name=c.name, value=c.name) for c in matches[:25]]


async def _weapon_autocomplete(interaction: discord.Interaction, current: str):
    current = (current or "").lower()
    matches = [w for w in wp.list_weapons(enabled_only=False) if current in w.name.lower()]
    return [app_commands.Choice(name=w.name, value=w.name) for w in matches[:25]]


class AdminEdit(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    edit_group = app_commands.Group(name="edit", description="[Admin] Edit bot assets", parent=admin_group)
    change_group = app_commands.Group(name="change", description="[Admin] Swap a roster entry's image", parent=admin_group)

    @edit_group.command(name="template", description="[Admin] Replace the GLOBAL default card template background")
    @is_admin()
    async def card_template(self, interaction: discord.Interaction, template: discord.Attachment):
        await interaction.response.defer(ephemeral=True)
        dest = TEMPLATE_DIR / "active_template.png"
        path = await _save_attachment(template, dest)
        set_setting("card_template_path", path)
        await interaction.followup.send(
            "✅ Global card template updated — any card without its own template will use it from now on.",
            ephemeral=True,
        )

    @edit_group.command(
        name="character",
        description="[Admin] Build/update the card for an already-added character (stats, template, art)",
    )
    @app_commands.describe(
        character="An already-added character (see /admin character add)",
        template="Optional: a card background just for this character",
        health="Optional: set this character's HP",
        damage="Optional: set this character's Attack",
        image="Optional: card artwork ONLY (spawns keep using the original image - use /admin change character for that)",
        ability_name="Optional: set this character's ability name",
        ability_description="Optional: set this character's ability description",
    )
    @app_commands.autocomplete(character=_character_autocomplete)
    @is_admin()
    async def card_character(
        self,
        interaction: discord.Interaction,
        character: str,
        template: discord.Attachment = None,
        health: int = None,
        damage: int = None,
        image: discord.Attachment = None,
        ability_name: str = None,
        ability_description: str = None,
    ):
        char = ch.find_character_by_name(character, enabled_only=False)
        if char is None:
            await interaction.response.send_message(
                f"No character named **{character}**. Add it first with `/admin character add`.",
                ephemeral=True,
            )
            return
        if (
            template is None and health is None and damage is None and image is None
            and ability_name is None and ability_description is None
        ):
            await interaction.response.send_message(
                "Give me at least one of template, health, damage, image, ability_name, "
                "or ability_description to update.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)
        template_path = None
        if template is not None:
            ext = Path(template.filename).suffix or ".png"
            dest = TEMPLATE_DIR / f"{char.name.lower().replace(' ', '_')}_template{ext}"
            template_path = await _save_attachment(template, dest)

        image_path = None
        if image is not None:
            ext = Path(image.filename).suffix or ".png"
            dest = UPLOAD_DIR / f"{char.name.lower().replace(' ', '_')}_v2{ext}"
            image_path = await _save_attachment(image, dest)

        ch.update_character_card(
            char.id, hp=health, attack=damage,
            card_template_path=template_path, card_image_path=image_path,
            ability_name=ability_name, ability_description=ability_description,
        )
        await interaction.followup.send(
            f"✅ Updated **{char.name}**'s card. This only changes what shows in "
            f"`/pack daily`/`/card view` - {char.name}'s spawn image is unchanged. "
            f"Preview it with `/card view name:{char.name}`.",
            ephemeral=True,
        )

    @edit_group.command(
        name="weapon",
        description="[Admin] Build/update the card for an already-added weapon (damage, template, art)",
    )
    @app_commands.describe(
        weapon="An already-added weapon (see /admin weapon add)",
        template="Optional: a card background just for this weapon",
        damage="Optional: set this weapon's attack bonus",
        image="Optional: card artwork ONLY (spawns keep using the original image - use /admin change weapon for that)",
        ability_name="Optional: set this weapon's ability name",
        ability_description="Optional: set this weapon's ability description",
    )
    @app_commands.autocomplete(weapon=_weapon_autocomplete)
    @is_admin()
    async def card_weapon(
        self,
        interaction: discord.Interaction,
        weapon: str,
        template: discord.Attachment = None,
        damage: int = None,
        image: discord.Attachment = None,
        ability_name: str = None,
        ability_description: str = None,
    ):
        wpn = wp.find_weapon_by_name(weapon, enabled_only=False)
        if wpn is None:
            await interaction.response.send_message(
                f"No weapon named **{weapon}**. Add it first with `/admin weapon add`.", ephemeral=True
            )
            return
        if (
            template is None and damage is None and image is None
            and ability_name is None and ability_description is None
        ):
            await interaction.response.send_message(
                "Give me at least one of template, damage, image, ability_name, "
                "or ability_description to update.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)
        template_path = None
        if template is not None:
            ext = Path(template.filename).suffix or ".png"
            dest = TEMPLATE_DIR / f"weapon_{wpn.name.lower().replace(' ', '_')}_template{ext}"
            template_path = await _save_attachment(template, dest)

        image_path = None
        if image is not None:
            ext = Path(image.filename).suffix or ".png"
            dest = UPLOAD_DIR / f"weapon_{wpn.name.lower().replace(' ', '_')}_v2{ext}"
            image_path = await _save_attachment(image, dest)

        wp.update_weapon_card(
            wpn.id, attack_bonus=damage,
            card_template_path=template_path, card_image_path=image_path,
            ability_name=ability_name, ability_description=ability_description,
        )
        await interaction.followup.send(
            f"✅ Updated **{wpn.name}**'s card. This only changes what shows in "
            f"`/pack daily`/`/card view` - {wpn.name}'s spawn image is unchanged. "
            f"Preview it with `/card view name:{wpn.name}`.",
            ephemeral=True,
        )

    @change_group.command(name="character", description="[Admin] Swap an existing character's image")
    @is_admin()
    async def change_character(self, interaction: discord.Interaction, name: str, image: discord.Attachment):
        character = ch.find_character_by_name(name, enabled_only=False)
        if character is None:
            await interaction.response.send_message(f"No character named **{name}**.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        ext = Path(image.filename).suffix or ".png"
        dest = UPLOAD_DIR / f"{name.lower().replace(' ', '_')}_v2{ext}"
        path = await _save_attachment(image, dest)
        ch.update_character_image(character.id, path)
        await interaction.followup.send(f"✅ Updated **{character.name}**'s image.", ephemeral=True)

    @change_group.command(name="weapon", description="[Admin] Swap an existing weapon's image")
    @is_admin()
    async def change_weapon(self, interaction: discord.Interaction, name: str, image: discord.Attachment):
        weapon = wp.find_weapon_by_name(name, enabled_only=False)
        if weapon is None:
            await interaction.response.send_message(f"No weapon named **{name}**.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        ext = Path(image.filename).suffix or ".png"
        dest = UPLOAD_DIR / f"weapon_{name.lower().replace(' ', '_')}_v2{ext}"
        path = await _save_attachment(image, dest)
        wp.update_weapon_image(weapon.id, path)
        await interaction.followup.send(f"✅ Updated **{weapon.name}**'s image.", ephemeral=True)

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            msg = "🚫 Only the bot owner/admins listed in ADMIN_USER_IDS can use this command."
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
        else:
            raise error


async def setup(bot: commands.Bot):
    await bot.add_cog(AdminEdit(bot))