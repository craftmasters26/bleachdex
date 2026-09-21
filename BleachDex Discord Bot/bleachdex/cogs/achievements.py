"""
/achievements - 5 achievements per page (name, description, KAN
reward, and your progress/earned status for each), with first/back/
jump-to-page/next/last controls.

Each achievement gets its own small embed (stacked in one message,
same accent color so they read as one continuous card) so it can carry
its own thumbnail icon - a single embed can only show one image, so
"one achievement per embed" is what makes per-achievement art possible
at 5-per-page.
"""

from pathlib import Path
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from db import achievements as ach, achievement_icons as icons
from cogs.permissions import is_admin
from cogs.admin_group import admin_group
from discord_utils import kan_label

UPLOAD_DIR = Path(__file__).parent.parent / "admin" / "static" / "uploads" / "achievements"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

PER_PAGE = 5
BAR_LENGTH = 10
ACCENT_COLOR = discord.Color.from_rgb(255, 159, 10)  # orange accent bar down the left


async def _save_icon(attachment: discord.Attachment, achievement_key: str) -> str:
    ext = Path(attachment.filename).suffix or ".png"
    dest = UPLOAD_DIR / f"{achievement_key}{ext}"
    await attachment.save(dest)
    return str(dest)


def _progress_bar(current: int, total: int, length: int = BAR_LENGTH) -> str:
    if total <= 0:
        filled = length
    else:
        filled = round(length * min(current, total) / total)
    filled = max(0, min(length, filled))
    return "▰" * filled + "▭" * (length - filled)


def _total_pages() -> int:
    return max(1, -(-len(ach.ACHIEVEMENTS) // PER_PAGE))  # ceil division


def _build_embeds(
    client: discord.Client, target: discord.abc.User, page: int
) -> tuple[list[discord.Embed], list[discord.File]]:
    earned = ach.earned_keys(target.id)
    all_achievements = ach.ACHIEVEMENTS
    total = len(all_achievements)
    total_pages = _total_pages()
    page = max(0, min(page, total_pages - 1))

    # Only count achievements that still exist - a player can hold rows for
    # old, removed achievements, which must not inflate "X/Y unlocked".
    earned_count = len(earned & ach.ACHIEVEMENT_KEYS)
    percent = round(100 * earned_count / total) if total else 0
    kan = kan_label(client)

    header = discord.Embed(
        title=f"{target.display_name}'s Achievements",
        description=f"{earned_count}/{total} unlocked ({percent}%)",
        color=ACCENT_COLOR,
    )
    embeds: list[discord.Embed] = [header]
    files: list[discord.File] = []

    page_items = all_achievements[page * PER_PAGE:(page + 1) * PER_PAGE]
    snapshot = ach.Progress(target.id)  # loads each stat once for the whole page
    for a in page_items:
        is_earned = a.key in earned
        target = a.target()
        progress = target if is_earned else min(a.progress_fn(snapshot), target)
        bar = _progress_bar(progress, target)
        status_icon = "✅" if is_earned else "🔒"

        description = (
            f"{status_icon} **{a.name}** • {progress}/{target} {bar}\n"
            f"{a.description}\n"
            f"Reward: **{a.kan_reward} {kan}**"
        )
        entry = discord.Embed(description=description, color=ACCENT_COLOR)

        icon_path = icons.get_icon(a.key)
        if icon_path and Path(icon_path).exists():
            filename = f"{a.key}{Path(icon_path).suffix}"
            files.append(discord.File(icon_path, filename=filename))
            entry.set_thumbnail(url=f"attachment://{filename}")

        embeds.append(entry)

    embeds[-1].set_footer(text=f"Page {page + 1}/{total_pages}")
    return embeds, files


class JumpToPageModal(discord.ui.Modal, title="Go to page"):
    page_number = discord.ui.TextInput(label="Page number", placeholder="e.g. 2")

    def __init__(self, view: "AchievementsView"):
        super().__init__()
        self.view_ref = view

    async def on_submit(self, interaction: discord.Interaction):
        try:
            target_page = int(self.page_number.value) - 1
        except ValueError:
            await interaction.response.send_message("That's not a number.", ephemeral=True)
            return
        total_pages = _total_pages()
        if not (0 <= target_page < total_pages):
            await interaction.response.send_message(
                f"Pick a page between 1 and {total_pages}.", ephemeral=True
            )
            return
        self.view_ref.page = target_page
        self.view_ref._update_buttons()
        embeds, files = _build_embeds(interaction.client, self.view_ref.target, self.view_ref.page)
        await interaction.response.edit_message(embeds=embeds, attachments=files, view=self.view_ref)


class AchievementsView(discord.ui.View):
    def __init__(self, target: discord.abc.User, owner_id: int):
        super().__init__(timeout=180)
        self.target = target
        self.owner_id = owner_id
        self.page = 0
        self.total_pages = _total_pages()
        self._update_buttons()

    def _update_buttons(self):
        at_start = self.page <= 0
        at_end = self.page >= self.total_pages - 1
        self.first_page.disabled = at_start
        self.previous_page.disabled = at_start
        self.next_page.disabled = at_end
        self.last_page.disabled = at_end
        self.go_to_page.label = f"{self.page + 1} (go to)"

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "Run `/achievements` yourself to flip through your own pages.", ephemeral=True
            )
            return False
        return True

    async def _refresh(self, interaction: discord.Interaction):
        self._update_buttons()
        embeds, files = _build_embeds(interaction.client, self.target, self.page)
        await interaction.response.edit_message(embeds=embeds, attachments=files, view=self)

    @discord.ui.button(label="⏮", style=discord.ButtonStyle.secondary)
    async def first_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = 0
        await self._refresh(interaction)

    @discord.ui.button(label="◀ Back", style=discord.ButtonStyle.secondary)
    async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page -= 1
        await self._refresh(interaction)

    @discord.ui.button(label="1 (go to)", style=discord.ButtonStyle.primary)
    async def go_to_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(JumpToPageModal(self))

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page += 1
        await self._refresh(interaction)

    @discord.ui.button(label="⏭", style=discord.ButtonStyle.secondary)
    async def last_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = self.total_pages - 1
        await self._refresh(interaction)


class Achievements(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.icon_group = AchievementIconGroup()
        if admin_group.get_command(self.icon_group.name) is not None:
            admin_group.remove_command(self.icon_group.name)
        admin_group.add_command(self.icon_group)

    @app_commands.command(name="achievements", description="See your earned achievements and progress")
    async def achievements(self, interaction: discord.Interaction, user: Optional[discord.User] = None):
        target = user or interaction.user
        view = AchievementsView(target, owner_id=interaction.user.id)
        embeds, files = _build_embeds(interaction.client, target, 0)
        await interaction.response.send_message(embeds=embeds, files=files, view=view)


class AchievementIconGroup(app_commands.Group):
    def __init__(self):
        super().__init__(
            name="achievement",
            description="[Bot admin] Manage achievement art",
        )

    async def _key_autocomplete(self, interaction: discord.Interaction, current: str):
        current = (current or "").lower()
        return [
            app_commands.Choice(name=f"{a.name} ({a.key})", value=a.key)
            for a in ach.ACHIEVEMENTS
            if current in a.key.lower() or current in a.name.lower()
        ][:25]

    @app_commands.command(name="seticon", description="[Bot admin] Set (or replace) an achievement's icon")
    @app_commands.describe(key="Which achievement", image="The icon image")
    @app_commands.autocomplete(key=_key_autocomplete)
    @is_admin()
    async def seticon(self, interaction: discord.Interaction, key: str, image: discord.Attachment):
        match = next((a for a in ach.ACHIEVEMENTS if a.key == key), None)
        if match is None:
            await interaction.response.send_message(f"No achievement with key `{key}`.", ephemeral=True)
            return
        path = await _save_icon(image, key)
        icons.set_icon(key, path)
        await interaction.response.send_message(
            f"Icon saved for **{match.name}** - it'll now show as a thumbnail next to that "
            f"achievement in `/achievements`.",
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


async def setup(bot: commands.Bot):
    await bot.add_cog(Achievements(bot))