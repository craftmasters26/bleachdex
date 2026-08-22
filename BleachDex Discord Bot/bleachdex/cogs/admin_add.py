"""
/admin character add - admin-only, adds a catchable character by NAME
                  only - pick the name from the autocomplete list and
                  the bot pulls the image straight from the GitHub repo
                  (see soul.py). It's catchable/spawnable right away,
                  but with placeholder stats (1 HP / 1 ATK) - it
                  doesn't have its real "card" yet. Use
                  /admin edit character to fill in the real stats, a
                  card template, and (optionally) swap the art - see
                  cogs/admin_edit.py.
/admin weapon add - same idea, for a Zanpakuto/weapon (see zanpaku.py).

These are the Discord-native alternative to the web admin panel - both
write to the same database, so characters/weapons added either way
show up everywhere.
"""

from pathlib import Path

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from db import characters as ch, weapons as wp
from cogs.permissions import is_admin
from cogs.admin_group import admin_group
from soul import CHARACTER_IMAGES
from zanpaku import WEAPON_IMAGES

UPLOAD_DIR = Path(__file__).parent.parent / "admin" / "static" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


async def _save_attachment(attachment: discord.Attachment, prefix: str) -> str:
    ext = Path(attachment.filename).suffix or ".png"
    dest = UPLOAD_DIR / f"{prefix}{ext}"
    counter = 1
    while dest.exists():
        dest = UPLOAD_DIR / f"{prefix}_{counter}{ext}"
        counter += 1
    await attachment.save(dest)
    return str(dest)


async def _save_from_url(url: str, prefix: str) -> str:
    ext = Path(url.split("?")[0]).suffix or ".png"
    dest = UPLOAD_DIR / f"{prefix}{ext}"
    counter = 1
    while dest.exists():
        dest = UPLOAD_DIR / f"{prefix}_{counter}{ext}"
        counter += 1
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            resp.raise_for_status()
            data = await resp.read()
    dest.write_bytes(data)
    return str(dest)


async def _soul_autocomplete(interaction: discord.Interaction, current: str):
    current = (current or "").lower()
    matches = [n for n in CHARACTER_IMAGES if current in n.lower()]
    return [app_commands.Choice(name=n, value=n) for n in matches[:25]]


async def _zanpaku_autocomplete(interaction: discord.Interaction, current: str):
    current = (current or "").lower()
    matches = [n for n in WEAPON_IMAGES if current in n.lower()]
    return [app_commands.Choice(name=n, value=n) for n in matches[:25]]


class AdminAdd(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    character_group = app_commands.Group(name="character", description="Manage characters (admin)", parent=admin_group)
    weapon_group = app_commands.Group(name="weapon", description="Manage weapons (admin)", parent=admin_group)

    @character_group.command(name="add", description="[Admin] Add a new catchable character (pick from the roster list)")
    @app_commands.autocomplete(name=_soul_autocomplete)
    @is_admin()
    async def character_add(
        self,
        interaction: discord.Interaction,
        name: str,
    ):
        if ch.find_character_by_name(name) is not None:
            await interaction.response.send_message(
                f"A character named **{name}** already exists.", ephemeral=True
            )
            return

        image_url = CHARACTER_IMAGES.get(name)
        if image_url is None:
            await interaction.response.send_message(
                f"No image mapped for **{name}** in soul.py yet. Pick a name from the "
                f"autocomplete list, or add it to soul.py first.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)
        image_path = await _save_from_url(image_url, name.lower().replace(" ", "_"))

        char_id = ch.add_character(name=name, image_path=image_path)
        await interaction.followup.send(
            f"✅ Added **{name}** — id `{char_id}`. It's catchable/spawnable now, "
            f"but it doesn't have its card set up yet (still placeholder stats). "
            f"Run `/admin edit character` to fill in HP, damage, and a template.",
            ephemeral=True,
        )

    @weapon_group.command(name="add", description="[Admin] Add a new catchable weapon/zanpakuto (pick from the list)")
    @app_commands.autocomplete(name=_zanpaku_autocomplete)
    @is_admin()
    async def weapon_add(
        self,
        interaction: discord.Interaction,
        name: str,
    ):
        if wp.find_weapon_by_name(name) is not None:
            await interaction.response.send_message(
                f"A weapon named **{name}** already exists.", ephemeral=True
            )
            return

        image_url = WEAPON_IMAGES.get(name)
        if image_url is None:
            await interaction.response.send_message(
                f"No image mapped for **{name}** in zanpaku.py yet. Pick a name from the "
                f"autocomplete list, or add it to zanpaku.py first.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)
        image_path = await _save_from_url(image_url, "weapon_" + name.lower().replace(" ", "_"))

        weapon_id = wp.add_weapon(name=name, image_path=image_path)
        await interaction.followup.send(
            f"✅ Added **{name}** — id `{weapon_id}`. It's catchable/spawnable now, "
            f"but it doesn't have its card set up yet (still placeholder stats). "
            f"Run `/admin edit weapon` to fill in damage and a template.",
            ephemeral=True,
        )

    @character_group.command(name="remove", description="[Admin] Remove a character so it stops appearing in packs")
    @is_admin()
    async def character_remove(self, interaction: discord.Interaction, name: str):
        character = ch.find_character_by_name(name)
        if character is None:
            await interaction.response.send_message(
                f"No character found named **{name}**.", ephemeral=True
            )
            return
        ch.delete_character(character.id)
        await interaction.response.send_message(
            f"🗑️ Removed **{character.name}** — it will no longer appear in packs. "
            f"(Anyone who already owns it keeps it.)",
            ephemeral=True,
        )

    @weapon_group.command(name="remove", description="[Admin] Remove a weapon so it stops appearing in packs")
    @is_admin()
    async def weapon_remove(self, interaction: discord.Interaction, name: str):
        weapon = wp.find_weapon_by_name(name)
        if weapon is None:
            await interaction.response.send_message(
                f"No weapon found named **{name}**.", ephemeral=True
            )
            return
        wp.delete_weapon(weapon.id)
        await interaction.response.send_message(
            f"🗑️ Removed **{weapon.name}** — it will no longer appear in packs. "
            f"(Anyone who already owns it keeps it.)",
            ephemeral=True,
        )

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        if isinstance(error, app_commands.CheckFailure):
            msg = "🚫 Only the bot owner/admins listed in ADMIN_USER_IDS can use this command."
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
        else:
            raise error


async def setup(bot: commands.Bot):
    cog = AdminAdd(bot)
    await bot.add_cog(cog)
    # Note: bot.add_cog() already registers character_group and weapon_group
    # (and, transitively, admin_group - see cogs/admin_group.py) to the
    # command tree automatically, since they're defined as Group class
    # attributes on the Cog. admin_group itself only gets explicitly
    # added to bot.tree once, in bot.py's setup_hook, after every
    # extension has loaded.
