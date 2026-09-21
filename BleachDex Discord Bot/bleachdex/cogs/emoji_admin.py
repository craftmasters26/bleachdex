"""
/admin emoji add name:<name> emoji_id:<id> - [Bot admin] set/update a
character OR weapon's custom emoji, by pasting the numeric emoji ID
from Discord's Developer Portal (or right-click the emoji in a server
with Developer Mode on -> Copy Emoji ID). Auto-detects whether `name`
is a character or a weapon - no need to specify which.

Once set, /collection and the catch message show the emoji instead of
(or alongside) the name automatically - see discord_utils.resolve_emoji,
which every place that displays a character/weapon already calls.
"""

import discord
from discord import app_commands
from discord.ext import commands

from db import characters as ch, weapons as wp, custom_emoji as ce
from cogs.permissions import is_admin
from cogs.admin_group import admin_group
from discord_utils import resolve_emoji, refresh_application_emoji_cache


class EmojiGroup(app_commands.Group):
    def __init__(self):
        super().__init__(name="emoji", description="[Bot admin] Manage character/weapon emoji", parent=admin_group)

    @app_commands.command(name="add", description="[Bot admin] Set a character or weapon's custom emoji ID")
    @app_commands.describe(
        name="Name of the character or weapon to update",
        emoji_id="The emoji's numeric ID (Developer Portal, or right-click it with Developer Mode on -> Copy Emoji ID)",
    )
    @is_admin()
    async def add(self, interaction: discord.Interaction, name: str, emoji_id: str):
        char_target = ch.find_character_by_name(name)
        weapon_target = wp.find_weapon_by_name(name)

        if char_target and weapon_target:
            await interaction.response.send_message(
                f"There's both a character AND a weapon named **{name}** - "
                f"rename one so `/admin emoji add` can tell them apart.",
                ephemeral=True,
            )
            return
        if char_target is None and weapon_target is None:
            await interaction.response.send_message(
                f"No character or weapon found named **{name}**.", ephemeral=True
            )
            return

        emoji_id = emoji_id.strip()
        if not emoji_id.isdigit():
            await interaction.response.send_message(
                "emoji_id must be the numeric emoji ID, not the emoji itself. "
                "Right-click the emoji with Developer Mode on and choose "
                "**Copy Emoji ID**.",
                ephemeral=True,
            )
            return

        if char_target:
            ch.update_character_emoji(char_target.id, emoji_id)
            target_name = char_target.name
        else:
            wp.update_weapon_emoji(weapon_target.id, emoji_id)
            target_name = weapon_target.name

        mention = resolve_emoji(interaction.client, emoji_id)
        if not mention:
            # Might just be missing from our cache if it was uploaded to
            # the Developer Portal moments ago - refresh and try once more
            # before giving up.
            await refresh_application_emoji_cache(interaction.client)
            mention = resolve_emoji(interaction.client, emoji_id)
        if mention:
            await interaction.response.send_message(
                f"**{target_name}**'s emoji is now set — {mention}", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"Saved emoji ID `{emoji_id}` for **{target_name}**, but the bot "
                f"can't currently find that emoji — either it's a server emoji from "
                f"a server the bot isn't in, or the ID is mistyped. Double-check it.",
                ephemeral=True,
            )

    @add.autocomplete("name")
    async def add_name_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        """Every character and weapon name, filtered as you type, so you
        never have to remember exact spelling. Discord only allows 25
        suggestions at once - startswith matches are listed first, then
        anywhere-in-the-name matches, since those are the more likely pick."""
        current_lower = current.strip().lower()
        all_names = sorted(
            {c.name for c in ch.list_characters(enabled_only=False)}
            | {w.name for w in wp.list_weapons(enabled_only=False)}
        )
        if not current_lower:
            matches = all_names
        else:
            starts = [n for n in all_names if n.lower().startswith(current_lower)]
            contains = [n for n in all_names if current_lower in n.lower() and n not in starts]
            matches = starts + contains
        return [app_commands.Choice(name=n, value=n) for n in matches[:25]]

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

    @app_commands.command(
        name="set-custom",
        description="[Bot admin] Set an emoji for something that isn't a character/weapon (KAN, boss drops, etc.)",
    )
    @app_commands.describe(
        key="Short name for what this emoji is for, e.g. 'kan' or 'boss_drop:soul_shard'",
        emoji_id="The emoji's numeric ID (Developer Portal, or right-click it with Developer Mode on -> Copy Emoji ID)",
    )
    @is_admin()
    async def set_custom(self, interaction: discord.Interaction, key: str, emoji_id: str):
        emoji_id = emoji_id.strip()
        if not emoji_id.isdigit():
            await interaction.response.send_message(
                "emoji_id must be the numeric emoji ID, not the emoji itself. "
                "Right-click the emoji with Developer Mode on and choose "
                "**Copy Emoji ID**.",
                ephemeral=True,
            )
            return

        ce.set_emoji_id(key, emoji_id)

        mention = resolve_emoji(interaction.client, emoji_id)
        if not mention:
            await refresh_application_emoji_cache(interaction.client)
            mention = resolve_emoji(interaction.client, emoji_id)
        if mention:
            await interaction.response.send_message(
                f"**{key}**'s emoji is now set — {mention}", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"Saved emoji ID `{emoji_id}` for **{key}**, but the bot can't currently "
                f"find that emoji — either it's a server emoji from a server the bot isn't "
                f"in, or the ID is mistyped. Double-check it.",
                ephemeral=True,
            )


class EmojiAdmin(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Instantiating EmojiGroup() attaches it to admin_group
        # automatically (parent=admin_group in its __init__ above) -
        # admin_group itself only gets added to bot.tree once, in
        # bot.py's setup_hook, after every extension has loaded.
        self.emoji_group = EmojiGroup()


async def setup(bot: commands.Bot):
    await bot.add_cog(EmojiAdmin(bot))