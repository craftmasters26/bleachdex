"""
/shop - a 6-page daily shop, laid out like /merchant (see db/shop.py for the
rules and prices).

  pages 1-5   Soul Reaper / Vizard / Quincy / Hollow / Full Bringer - 6
              characters or weapons of that faction
  page 6      6 boss drops

The embed lists the 6 items with their emoji, tier/stats and KAN price. Pick a
page with the top dropdown or the arrows; pick an item in the second dropdown
and it is bought immediately (no second command), just like /merchant.
Items change every 24 hours (00:00 UTC). Only the person who ran /shop can use
its dropdowns and buttons.
"""

import asyncio

import discord
from discord import app_commands
from discord.ext import commands

from cogs.packs import TIER_COLORS
from db import shop as sh, characters as ch, weapons as wp, players as pl, inventory as inv, achievements as ach, custom_emoji as ce
from discord_utils import resolve_emoji, get_emoji_object, refresh_application_emoji_cache, kan_label

FALLBACK_EMOJI = "❔"   # same placeholder /collection uses for a card with no emoji set yet
DROP_FALLBACK_EMOJI = "📦"


def _emoji_id(item: sh.ShopItem) -> str:
    """The stored emoji id for an item (drops store an emoji *key* that maps to an id)."""
    if item.kind == "drop":
        return ce.get_emoji_id(item.emoji) if item.emoji else ""
    return item.emoji


def _face(client: discord.Client, item: sh.ShopItem) -> str:
    mention = resolve_emoji(client, _emoji_id(item))
    if mention:
        return mention
    return DROP_FALLBACK_EMOJI if item.kind == "drop" else FALLBACK_EMOJI


def _item_lines(items: list[sh.ShopItem], client: discord.Client, kan: str) -> str:
    if not items:
        return "*Nothing available on this page right now.*"
    lines = []
    for n, item in enumerate(items, start=1):
        lines.append(f"**{n}.** {_face(client, item)} **{item.name}** • **{item.price:,}** {kan}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# purchase receipts
# ---------------------------------------------------------------------------

async def _receipt(item: sh.ShopItem, instance_id: int, user_id: int, client: discord.Client):
    """A text-only embed (no rendered card image) shown after a successful purchase."""
    note = f"Balance: {pl.get_balance(user_id):,} KAN"
    face = _face(client, item)
    if item.kind == "character":
        character = ch.get_character(item.item_id)
        embed = discord.Embed(
            title=f"You got {character.name}! {face}",
            description=f"**{character.tier.title()}** • HP {character.hp:,} / ATK {character.attack:,}",
            color=TIER_COLORS.get(character.tier, discord.Color.default()),
        )
        embed.set_footer(text=note)
        return embed, None
    if item.kind == "weapon":
        weapon = wp.get_weapon(item.item_id)
        stat = "HP" if weapon.boost_type == "hp" else "Damage"
        embed = discord.Embed(
            title=f"You got {weapon.name}! {face}",
            description=f"**{weapon.tier.title()}** • +{weapon.boost_percent}% {stat}",
            color=TIER_COLORS.get(weapon.tier, discord.Color.default()),
        )
        embed.set_footer(text=note)
        return embed, None
    have = inv.get_quantity(user_id, item.name)
    embed = discord.Embed(
        title=f"You bought {face} {item.name}!",
        description=f"You now have **{have}**.",
        color=discord.Color.dark_gold(),
    )
    embed.set_footer(text=note)
    return embed, None


# ---------------------------------------------------------------------------
# the dropdowns and buttons
# ---------------------------------------------------------------------------

class PageSelect(discord.ui.Select):
    def __init__(self, page: int):
        super().__init__(
            placeholder="Shop page",
            options=[
                discord.SelectOption(label=f"{i + 1}. {label}", value=str(i), default=(i == page))
                for i, (_key, label) in enumerate(sh.PAGES)
            ],
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        await self.view.go_to(interaction, int(self.values[0]))


class BuySelect(discord.ui.Select):
    """One option per item on the current page; picking one buys it."""

    def __init__(self):
        super().__init__(
            placeholder="Buy an item",
            options=[discord.SelectOption(label="Nothing available", value="none")],
            row=1,
        )

    def load(self, items: list[sh.ShopItem], client: discord.Client) -> None:
        if not items:
            self.options = [discord.SelectOption(label="Nothing available", value="none")]
            self.disabled = True
            return
        self.disabled = False
        options = []
        for slot, item in enumerate(items):
            options.append(
                discord.SelectOption(
                    label=f"{item.name} — {item.price:,} KAN"[:100],
                    value=str(slot),
                    emoji=get_emoji_object(client, _emoji_id(item)),
                )
            )
        self.options = options

    async def callback(self, interaction: discord.Interaction):
        view: "ShopView" = self.view
        if self.values[0] == "none":
            await interaction.response.defer()
            return
        slot = int(self.values[0])
        if slot >= len(view.items):
            await interaction.response.send_message("There's nothing in that slot.", ephemeral=True)
            return
        expected = view.items[slot].name
        user_id = interaction.user.id

        try:
            item, instance_id = await asyncio.to_thread(sh.buy, user_id, view.page_key, slot, expected)
        except sh.PurchaseError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return

        # Rendering a card can involve a first-time image download, so the
        # purchase itself is done first (instant) and the slow part is deferred.
        await interaction.response.defer()
        client = interaction.client
        embed, file = await _receipt(item, instance_id, user_id, client)
        content = f"{interaction.user.mention} bought **{item.name}** for **{item.price:,}** {kan_label(client)}!"
        if file is not None:
            await interaction.followup.send(content=content, embed=embed, file=file)
        else:
            await interaction.followup.send(content=content, embed=embed)

        # The balance on the shop message is now out of date (and the dropdown
        # still shows the old selection), so redraw it.
        if view.message is not None:
            view._load()
            try:
                await view.message.edit(embed=view.build_embed(), view=view)
            except discord.HTTPException:
                pass

        for a in ach.check_and_grant(user_id):
            await interaction.followup.send(
                f"{interaction.user.mention} unlocked the **{a.name}** achievement — {a.description}!"
            )


class NavButton(discord.ui.Button):
    def __init__(self, label: str, step: int):
        super().__init__(label=label, style=discord.ButtonStyle.secondary, row=2)
        self.step = step

    async def callback(self, interaction: discord.Interaction):
        await self.view.go_to(interaction, (self.view.page + self.step) % len(sh.PAGES))


class ShopView(discord.ui.View):
    def __init__(self, owner_id: int, client: discord.Client, page: int = 0):
        super().__init__(timeout=300)
        self.owner_id = owner_id
        self.client = client
        self.page = page
        self.message: discord.Message | None = None
        self.items: list[sh.ShopItem] = []

        self.page_select = PageSelect(page)
        self.buy_select = BuySelect()
        self.add_item(self.page_select)
        self.add_item(self.buy_select)
        self.add_item(NavButton("◀", -1))
        self.add_item(NavButton("▶", +1))
        self._load()

    @property
    def page_key(self) -> str:
        return sh.PAGES[self.page][0]

    def _load(self) -> None:
        """Reads today's items for the current page and syncs both dropdowns."""
        self.items = sh.get_page_items(self.page_key)
        self.buy_select.load(self.items, self.client)
        for i, option in enumerate(self.page_select.options):
            option.default = (i == self.page)

    def build_embed(self) -> discord.Embed:
        label = sh.PAGES[self.page][1]
        kan = kan_label(self.client)
        balance = pl.get_balance(self.owner_id)
        blurb = "Boss drops, used for crafting." if self.page_key == sh.DROPS_PAGE else f"Characters and weapons of the **{label}** faction."
        embed = discord.Embed(
            title=f"Shop — {label}  ({self.page + 1}/{len(sh.PAGES)})",
            description=(
                f"{blurb}\n"
                f"Your balance: **{balance:,}** {kan}\n\n"
                + _item_lines(self.items, self.client, kan)
            ),
            color=discord.Color.dark_gold(),
        )
        embed.set_footer(text="Shop rotates every 24 hours")
        embed.add_field(name="Next rotation", value=f"<t:{sh.next_rotation_at()}:R>", inline=False)
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "This isn't your shop window — run /shop yourself.", ephemeral=True
            )
            return False
        return True

    async def go_to(self, interaction: discord.Interaction, page: int) -> None:
        self.page = page
        self._load()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


class Shop(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="shop",
        description="Daily shop - 5 faction pages + boss drops, refreshes every 24 hours",
    )
    async def shop(self, interaction: discord.Interaction):
        await refresh_application_emoji_cache(interaction.client)
        view = ShopView(interaction.user.id, interaction.client)
        await interaction.response.send_message(embed=view.build_embed(), view=view)
        view.message = await interaction.original_response()


async def setup(bot: commands.Bot):
    await bot.add_cog(Shop(bot))