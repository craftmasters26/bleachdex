"""
/admin emoji add character:<name> emoji_id:<id> - [Bot admin] set/update a
character's custom emoji, by pasting the numeric emoji ID from
Discord's Developer Portal (or right-click the emoji in a server with
Developer Mode on -> Copy Emoji ID).

Once set, /collection and the catch message show the emoji instead of
(or alongside) the character's name automatically - see
discord_utils.resolve_emoji, which every place that displays a
character already calls.
"""

import discord
from discord import app_commands
from discord.ext import commands

from db import characters as ch
from cogs.permissions import is_admin
from cogs.admin_group import admin_group
from discord_utils import resolve_emoji, refresh_application_emoji_cache


class EmojiGroup(app_commands.Group):
    def __init__(self):
        super().__init__(name="emoji", description="[Bot admin] Manage character emoji", parent=admin_group)

    @app_commands.command(name="add", description="[Bot admin] Set a character's custom emoji ID")
    @app_commands.describe(
        character="Name of the character to update",
        emoji_id="The emoji's numeric ID (Developer Portal, or right-click it with Developer Mode on -> Copy Emoji ID)",
    )
    @is_admin()
    async def add(self, interaction: discord.Interaction, character: str, emoji_id: str):
        target = ch.find_character_by_name(character)
        if target is None:
            await interaction.response.send_message(
                f"No character found named **{character}**.", ephemeral=True
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

        ch.update_character_emoji(target.id, emoji_id)

        mention = resolve_emoji(interaction.client, emoji_id)
        if not mention:
            # Might just be missing from our cache if it was uploaded to
            # the Developer Portal moments ago - refresh and try once more
            # before giving up.
            await refresh_application_emoji_cache(interaction.client)
            mention = resolve_emoji(interaction.client, emoji_id)
        if mention:
            await interaction.response.send_message(
                f"✅ **{target.name}**'s emoji is now set — {mention}", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"⚠️ Saved emoji ID `{emoji_id}` for **{target.name}**, but the bot "
                f"can't currently find that emoji — either it's a server emoji from "
                f"a server the bot isn't in, or the ID is mistyped. Double-check it.",
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