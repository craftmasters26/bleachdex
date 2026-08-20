"""
/about — interactive command reference. A dropdown lets you pick a
category and the embed swaps to show just that category, instead of
dumping every command at once.

Bot-admin-only commands (everything under /admin) are deliberately
left out of this entirely, for every user - this is a player-facing
reference, not a full command dump. /set spawn stays in, since that's
a server-admin command any server owner might need to find, not a
bot-admin one.

Kept as a hand-maintained dict rather than introspecting the command
tree, so descriptions stay readable. If you add new player-facing
commands later, add a line here too.
"""

import discord
from discord import app_commands
from discord.ext import commands

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
        "emoji": "⚔",
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
            ("/shop", "See today's shop — 2 characters + 2 weapons, rotates every 24h"),
        ],
    },
    "Leaderboard & Achievements": {
        "emoji": "",
        "commands": [
            ("/leaderboard", "Top players by total items owned"),
            ("/leaderboard item:<name>", "Top owners of one specific character/weapon"),
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
            discord.SelectOption(label=name, emoji=data["emoji"], default=(name == DEFAULT_CATEGORY))
            for name, data in CATEGORIES.items()
        ]
        super().__init__(placeholder="Choose a category...", options=options)

    async def callback(self, interaction: discord.Interaction):
        chosen = self.values[0]
        for option in self.options:
            option.default = (option.label == chosen)
        await interaction.response.edit_message(embed=_build_embed(chosen), view=self.view)


class AboutView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        self.add_item(CategorySelect())


class About(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="about", description="See what this bot can do")
    async def about(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            embed=_build_embed(DEFAULT_CATEGORY), view=AboutView()
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(About(bot))