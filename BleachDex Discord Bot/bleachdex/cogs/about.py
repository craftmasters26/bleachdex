"""
/help  - interactive command reference. A dropdown lets you pick a
category and the embed swaps to show just that category, instead of
dumping every command at once. (This used to be /about.)
/about - what BleachDex is, what you can do with it, and a few live
stats (servers, players, how many characters/weapons exist, latency).

Bot-admin-only commands (everything under /admin) are deliberately
left out of /help entirely, for every user - it is a player-facing
reference, not a full command dump. /set spawn stays in, since that's
a server-admin command any server owner might need to find, not a
bot-admin one.

/help is a hand-maintained dict rather than introspecting the command
tree, so descriptions stay readable. If you add new player-facing
commands later, add a line here too.
"""

import math
import time

import discord
from discord import app_commands
from discord.ext import commands

from db.connection import get_connection

CATEGORIES = {
    "Packs & Collection": {
        "emoji": "",
        "commands": [
            ("/pack daily", "Claim up to 3 random pulls per day"),
            ("/pack weekly", "Claim 1 guaranteed Epic+ pull per week"),
            ("/collection completion", "See your % owned, owned vs missing"),
            ("/collection inventory", "List your owned characters and weapons by name"),
        ],
    },
    "Battling & Trading": {
        "emoji": "",
        "commands": [
            ("/team add", "Set your 3-character battle team"),
            ("/battle", "Challenge another player to a turn-based fight"),
            ("/equip", "Attach an owned weapon to an owned character"),
            ("/unequip", "Remove a character's equipped weapon"),
            ("/trade start", "Propose a trade — both sides must accept"),
        ],
    },
    "Economy": {
        "emoji": "",
        "commands": [
            ("/daily", "Claim your daily KAN coins"),
            ("/balance", "Check your (or someone else's) KAN coin balance"),
            ("/shop", "Daily shop — 5 faction pages + boss drops, 6 items each, refreshes every 24 hours"),
        ],
    },
    "Leaderboard & Achievements": {
        "emoji": "",
        "commands": [
            ("/leaderboard", "Top players by total items owned"),
            ("/leaderboard item:<name>", "Top owners of one specific character/weapon"),
            ("/leaderboard kan:True", "Top players by KAN coins"),
            ("/achievements", "See your earned achievements and progress"),
        ],
    },
}

DEFAULT_CATEGORY = next(iter(CATEGORIES))


def _build_embed(category_name: str) -> discord.Embed:
    category = CATEGORIES[category_name]
    embed = discord.Embed(
        title=" BleachDex   Commands",
        description=f"{category['emoji']} **{category_name}**",
        color=discord.Color.blurple(),
    )
    value = "\n".join(f"**{cmd}** — {desc}" for cmd, desc in category["commands"])
    embed.add_field(name="\u200b", value=value, inline=False)
    embed.set_footer(text="Choose a category below to see more.")
    return embed


class CategorySelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label=name, emoji=(data["emoji"] or None), default=(name == DEFAULT_CATEGORY)
            )
            for name, data in CATEGORIES.items()
        ]
        super().__init__(placeholder="Choose a category...", options=options)

    async def callback(self, interaction: discord.Interaction):
        chosen = self.values[0]
        for option in self.options:
            option.default = (option.label == chosen)
        await interaction.response.edit_message(embed=_build_embed(chosen), view=self.view)


class HelpView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=440)
        self.add_item(CategorySelect())


def _count(sql: str) -> int:
    conn = get_connection()
    try:
        return conn.execute(sql).fetchone()[0]
    finally:
        conn.close()


def _build_about_embed(client: discord.Client, started_at: int) -> discord.Embed:
    characters = _count("SELECT COUNT(*) FROM characters WHERE enabled = 1")
    craftable = _count("SELECT COUNT(*) FROM characters WHERE enabled = 1 AND craftable_only = 1")
    weapons = _count("SELECT COUNT(*) FROM weapons WHERE enabled = 1")
    players = _count("SELECT COUNT(*) FROM players")
    latency = f"{round(client.latency * 1000)} ms" if math.isfinite(client.latency) else "—"

    embed = discord.Embed(
        title="About BleachDex",
        description=(
            "A Bleach-themed collectible card bot. Catch characters and weapons as they "
            "spawn, open packs, build a team, take on bosses and other players, craft "
            "rare forms and climb the leaderboard."
        ),
        color=discord.Color.blurple(),
    )
    embed.add_field(
        name="Collect",
        value=(
            "Characters and weapons spawn in your server and come out of `/pack daily` and "
            "`/pack weekly`, from Common up to Mythic. Every one belongs to a faction: "
            "Soul Reaper, Vizard, Quincy, Hollow or Full Bringer."
        ),
        inline=False,
    )
    embed.add_field(
        name="Battle",
        value="Save a 3-character team, equip weapons, challenge players with `/battle` and fight bosses when they appear.",
        inline=False,
    )
    embed.add_field(
        name="Economy & crafting",
        value=(
            "Earn KAN with `/daily` and spend it in `/shop`. Swap cards with `/merchant` and `/trade`, "
            "and use `/craft` to turn boss drops, weapons and cards into craft-only characters."
        ),
        inline=False,
    )
    embed.add_field(
        name="Live stats",
        value=(
            f"**Servers:** {len(client.guilds):,}\n"
            f"**Players:** {players:,}\n"
            f"**Characters:** {characters:,} ({craftable:,} craft-only)\n"
            f"**Weapons:** {weapons:,}\n"
            f"**Latency:** {latency}\n"
            f"**Online since:** <t:{started_at}:R>"
        ),
        inline=False,
    )
    embed.set_footer(text="Use /help to see every command.")
    return embed


class About(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.started_at = int(time.time())   # the cog loads when the bot starts

    @app_commands.command(name="help", description="See what this bot can do")
    async def help(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            embed=_build_embed(DEFAULT_CATEGORY), view=HelpView()
        )

    @app_commands.command(name="about", description="About BleachDex - what it is and how it's doing")
    async def about(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            embed=_build_about_embed(interaction.client, self.started_at)
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(About(bot))