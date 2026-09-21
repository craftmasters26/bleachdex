"""
/collection completion - tabbed progress screen: Souls / Weapons /
Craftable / Soul Reapers / Vizard / Hollow / Quincy / Full Bringer.
Every tab shows what you own and what you're missing, as each item's
custom emoji only - no names.
Two modes (buttons on the bottom row): Normal, and Reiatsu. Reiatsu is a
separate page - the same characters with the same emoji, but ticked off
only by owning a REIATSU copy (normal mode is only ticked off by a plain
copy). Weapons have no Reiatsu variant, so that tab is off in Reiatsu mode.
/collection inventory - first asks which of Weapons / Souls / Drops you
want to see via a dropdown, then shows only that one category,
paginated so a large collection never exceeds Discord's 1024-char
per-field limit in one giant message.
"""

import asyncio
from dataclasses import dataclass
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from db import characters as ch, weapons as wp, collection as coll, inventory as inv, bosses as bs, custom_emoji as ce
from discord_utils import resolve_emoji
from factions import completion_group
from reiatsu import REIATSU_EMOJI

REIATSU_COLOR = 0x46CDFF  # icy cyan, same as the Reiatsu card glow

FIELD_CHAR_LIMIT = 1000  # Discord's real cap is 1024; leave a little headroom
ITEMS_PER_PAGE = 10


FALLBACK_EMOJI = "❔"  # shown for a character/weapon that has no emoji_id set yet


def _label(character: ch.Character, client: discord.Client) -> str:
    mention = resolve_emoji(client, character.emoji)
    prefix = mention if mention else FALLBACK_EMOJI
    return f"{prefix} {character.name}"


def _weapon_label(weapon: wp.Weapon, client: discord.Client) -> str:
    mention = resolve_emoji(client, weapon.emoji)
    prefix = mention if mention else FALLBACK_EMOJI
    return f"{prefix} {weapon.name}"


def _drop_emoji_keys() -> dict[str, str]:
    """Maps drop_name -> emoji_key by scanning every preset boss's
    drop slots. Drop names/emoji are only ever defined on bosses (see
    seed_bossbattle.py), and owned_boss_drops itself just stores plain
    quantities - so this is the only way to find a drop's icon."""
    keys: dict[str, str] = {}
    for boss in bs.list_preset_bosses(enabled_only=False):
        for d in boss.drops:
            if d.item_name:
                keys[d.item_name] = d.emoji_key
    return keys


def _drop_label(drop_name: str, emoji_key: str, client: discord.Client) -> str:
    emoji_id = ce.get_emoji_id(emoji_key) if emoji_key else ""
    mention = resolve_emoji(client, emoji_id)
    prefix = mention if mention else FALLBACK_EMOJI
    return f"{prefix} {drop_name}"


def _chunk_lines(lines: list[str], max_items: int = ITEMS_PER_PAGE, limit: int = FIELD_CHAR_LIMIT) -> list[list[str]]:
    """Fixed-size pages of max_items lines each - but if an unusually
    long batch of lines would still blow past Discord's char limit
    even at that count (e.g. everyone has a long equipped-weapon note),
    a page splits early instead of crashing. Normal-length lines never
    trigger the length check; it's just a safety net under the 10/page
    you actually want."""
    if not lines:
        return [[]]
    chunks: list[list[str]] = []
    current: list[str] = []
    current_len = 0
    for line in lines:
        line_len = len(line) + 1  # +1 for the newline
        would_overflow_length = current and current_len + line_len > limit
        would_overflow_count = len(current) >= max_items
        if current and (would_overflow_length or would_overflow_count):
            chunks.append(current)
            current, current_len = [], 0
        current.append(line)
        current_len += line_len
    if current:
        chunks.append(current)
    return chunks


def _build_char_lines(target: discord.abc.User, client: discord.Client) -> tuple[list[str], int]:
    owned_chars = coll.list_owned_characters(target.id)
    char_counts: dict[int, int] = {}
    reiatsu_counts: dict[int, int] = {}
    char_order: list[int] = []  # first-caught order, for stable display
    for inst in owned_chars:
        if inst.character_id not in char_counts:
            char_order.append(inst.character_id)
        char_counts[inst.character_id] = char_counts.get(inst.character_id, 0) + 1
        if inst.is_reiatsu:
            reiatsu_counts[inst.character_id] = reiatsu_counts.get(inst.character_id, 0) + 1

    lines = []
    for character_id in char_order:
        char = ch.get_character(character_id)
        if char is None:
            continue
        count = char_counts[character_id]
        reiatsu_count = reiatsu_counts.get(character_id, 0)
        label = _label(char, client)
        line = f"{label} x{count}" if count > 1 else label
        if reiatsu_count:
            # Reiatsu copies (see reiatsu.py) are flagged - a bare bolt when
            # the only copy is one, otherwise how many of the copies are.
            line += f" {REIATSU_EMOJI}" if count == 1 else f" ({REIATSU_EMOJI} x{reiatsu_count})"
        lines.append(line)
    return lines, len(owned_chars)


def _build_weapon_lines(target: discord.abc.User, client: discord.Client) -> tuple[list[str], int]:
    owned_weapons = coll.list_owned_weapons(target.id)
    weapon_counts: dict[int, int] = {}
    weapon_order: list[int] = []
    for inst in owned_weapons:
        if inst.weapon_id not in weapon_counts:
            weapon_order.append(inst.weapon_id)
        weapon_counts[inst.weapon_id] = weapon_counts.get(inst.weapon_id, 0) + 1

    lines = []
    for weapon_id in weapon_order:
        weapon = wp.get_weapon(weapon_id)
        if weapon is None:
            continue
        count = weapon_counts[weapon_id]
        label = _weapon_label(weapon, client)
        lines.append(f"{label} x{count}" if count > 1 else label)
    return lines, len(owned_weapons)


def _build_drop_lines(target: discord.abc.User, client: discord.Client) -> tuple[list[str], int]:
    owned_drops = inv.list_inventory(target.id)  # [(drop_name, quantity)]
    emoji_keys = _drop_emoji_keys()

    lines = []
    for drop_name, quantity in owned_drops:
        label = _drop_label(drop_name, emoji_keys.get(drop_name, ""), client)
        lines.append(f"{label} x{quantity}" if quantity > 1 else label)
    return lines, len(owned_drops)


CATEGORIES = {
    "souls": ("Souls", _build_char_lines),
    "weapons": ("Weapons", _build_weapon_lines),
    "drops": ("Drops", _build_drop_lines),
}


class InventoryView(discord.ui.View):
    def __init__(self, owner_id: int, target: discord.abc.User):
        super().__init__(timeout=180)
        self.owner_id = owner_id
        self.target = target
        self.category: Optional[str] = None
        self.chunks: list[list[str]] = [[]]
        self.count = 0
        self.page = 0
        self.message: Optional[discord.Message] = None
        self._update_button_states()

    def _update_button_states(self):
        has_category = self.category is not None
        total_pages = len(self.chunks)
        self.previous_button.disabled = not has_category or self.page == 0
        self.next_button.disabled = not has_category or self.page >= total_pages - 1

    def _load_category(self, category: str, client: discord.Client):
        self.category = category
        _, builder = CATEGORIES[category]
        lines, count = builder(self.target, client)
        self.chunks = _chunk_lines(lines)
        self.count = count
        self.page = 0

        for option in self.category_select.options:
            option.default = option.value == category

    def build_embed(self) -> discord.Embed:
        embed = discord.Embed(title=f"{self.target.display_name}'s inventory", color=discord.Color.blurple())
        if self.category is None:
            embed.description = "Pick a category below to see what you own."
            return embed

        label, _ = CATEGORIES[self.category]
        text = "\n".join(self.chunks[self.page]) if self.page < len(self.chunks) else ""
        embed.add_field(
            name=f"{label} ({self.count})",
            value=text if text else "None yet.",
            inline=False,
        )
        embed.set_footer(text=f"Page {self.page + 1}/{len(self.chunks)}")
        return embed

    async def _guard(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "Only the person who ran this command can use this.", ephemeral=True
            )
            return False
        return True

    @discord.ui.select(
        placeholder="Choose a category...",
        options=[
            discord.SelectOption(label="Souls", value="souls"),
            discord.SelectOption(label="Weapons", value="weapons"),
            discord.SelectOption(label="Drops", value="drops"),
        ],
    )
    async def category_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        if not await self._guard(interaction):
            return
        self._load_category(select.values[0], interaction.client)
        self._update_button_states()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary, row=1)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._guard(interaction):
            return
        self.page = max(self.page - 1, 0)
        self._update_button_states()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="Quit", style=discord.ButtonStyle.danger, row=1)
    async def quit_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._guard(interaction):
            return
        self.stop()
        await interaction.response.edit_message(view=None)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary, row=1)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._guard(interaction):
            return
        self.page = min(self.page + 1, len(self.chunks) - 1)
        self._update_button_states()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


# ---------------------------------------------------------------------------
# /collection completion
# ---------------------------------------------------------------------------

PAGE_CHAR_LIMIT = 3800  # embed descriptions cap at 4096; leave headroom for headers

# key, button label, button emoji, plural noun used in the embed
TABS = [
    ("souls",       "Souls",        "\U0001F47B", "souls"),
    ("weapons",     "Weapons",      "\u2694\ufe0f", "weapons"),
    ("craftable",   "Craftable",    "\U0001F528", "craftables"),
    ("soul_reaper", "Soul Reapers", "\U0001F5E1\ufe0f", "Soul Reapers"),
    ("vizard",      "Vizard",       "\U0001F3AD", "Vizards"),
    ("hollow",      "Hollow",       "\U0001F480", "Hollows"),
    ("quincy",      "Quincy",       "\U0001F3F9", "Quincy"),
    ("fullbringer", "Full Bringer", "\U0001F52E", "Full Bringers"),
    ("all",         "All",          "",            "collectibles"),
]
TAB_INFO = {key: (label, icon, noun) for key, label, icon, noun in TABS}


@dataclass
class _Entry:
    id: int
    name: str
    emoji: str
    is_weapon: bool = False


def _token(entry: _Entry, client: discord.Client) -> str:
    """Emoji only, never the name. An item with no emoji set yet shows
    the FALLBACK_EMOJI placeholder so the owned/missing counts still
    add up - set its emoji with /admin emoji and it swaps in."""
    mention = resolve_emoji(client, entry.emoji)
    return mention if mention else FALLBACK_EMOJI


class _PagePacker:
    """Packs [(title, tokens, empty_text), ...] into description pages
    under PAGE_CHAR_LIMIT. A section that spills onto the next page gets
    its header repeated with (cont.)."""

    def __init__(self, limit: int = PAGE_CHAR_LIMIT):
        self.limit = limit
        self.pages: list[str] = []
        self.blocks: list[str] = []
        self.used = 0

    def _close_page(self):
        if self.blocks:
            self.pages.append("\n\n".join(self.blocks))
        self.blocks, self.used = [], 0

    def _add_block(self, block: str):
        self.blocks.append(block)
        self.used += len(block) + 2

    def add_section(self, title: str, tokens: list[str], empty_text: str):
        if not tokens:
            block = f"**{title}**\n{empty_text}"
            if self.used and self.used + len(block) + 2 > self.limit:
                self._close_page()
            self._add_block(block)
            return

        cont = False
        run: list[str] = []
        run_len = 0
        for tok in tokens:
            head = f"**{title}**" + (" (cont.)" if cont else "")
            projected = self.used + len(head) + 1 + run_len + len(tok) + 1 + 2
            if projected > self.limit:
                if run:
                    self._add_block(f"{head}\n{' '.join(run)}")
                    run, run_len = [], 0
                    cont = True
                self._close_page()
            run.append(tok)
            run_len += len(tok) + 1
        head = f"**{title}**" + (" (cont.)" if cont else "")
        self._add_block(f"{head}\n{' '.join(run)}")

    def finish(self) -> list[str]:
        self._close_page()
        return self.pages or [""]


class CompletionView(discord.ui.View):
    def __init__(self, owner_id: int, target: discord.abc.User):
        super().__init__(timeout=180)
        self.owner_id = owner_id
        self.target = target
        self.message: Optional[discord.Message] = None

        self.tab = "souls"
        self.mode = "normal"   # "normal" | "reiatsu"
        self.page = 0
        self.pages: list[str] = [""]
        self.owned_count = 0
        self.total_count = 0
        self.overall_percent = 0.0

        # roster is loaded once per view; ownership is re-read on every tab switch
        self._chars: Optional[list[ch.Character]] = None
        self._weapons: Optional[list[wp.Weapon]] = None
        self._owned_char_ids: set[int] = set()      # plain copies (normal mode)
        self._owned_reiatsu_ids: set[int] = set()   # Reiatsu copies (reiatsu mode)
        self._owned_weapon_ids: set[int] = set()

        self._tab_buttons: dict[str, discord.ui.Button] = {}
        for index, (key, label, icon, _noun) in enumerate(TABS):
            button = discord.ui.Button(label=label, row=index // 5,
                                       style=discord.ButtonStyle.secondary)
            button.callback = self._make_tab_callback(key)
            self._tab_buttons[key] = button
            self.add_item(button)

        # Bottom row: [previous] [Normal] [Reiatsu] [next]
        self.previous_button = discord.ui.Button(label="\u25c0", row=2, style=discord.ButtonStyle.secondary)
        self.next_button = discord.ui.Button(label="\u25b6", row=2, style=discord.ButtonStyle.secondary)
        self.previous_button.callback = self._on_previous
        self.next_button.callback = self._on_next
        self.add_item(self.previous_button)

        self._mode_buttons: dict[str, discord.ui.Button] = {}
        for mode, label, emoji in (("normal", "Normal", None), ("reiatsu", "Reiatsu", REIATSU_EMOJI)):
            button = discord.ui.Button(label=label, emoji=emoji, row=2, style=discord.ButtonStyle.secondary)
            button.callback = self._make_mode_callback(mode)
            self._mode_buttons[mode] = button
            self.add_item(button)

        self.add_item(self.next_button)

    # -- data (DB only - safe to run in a thread) --------------------------

    def load(self):
        if self._chars is None:
            # craftables count toward completion even though packs/spawns
            # never hand them out - you get them via /craft.
            self._chars = ch.list_characters(enabled_only=True, include_craftable_only=True)
            self._weapons = wp.list_weapons(enabled_only=True)
        self._owned_char_ids, self._owned_reiatsu_ids = coll.get_owned_character_ids_split(self.target.id)
        self._owned_weapon_ids = coll.get_owned_weapon_ids(self.target.id)

    # -- rendering (main thread - resolves emoji from the client cache) ----

    def _entries_for(self, tab: str) -> list[_Entry]:
        # Weapons have no Reiatsu variant, so Reiatsu mode never lists them.
        weapons = [] if self.mode == "reiatsu" else [
            _Entry(w.id, w.name, w.emoji, is_weapon=True) for w in self._weapons
        ]
        craftables = sorted((c for c in self._chars if c.craftable_only), key=lambda c: c.id)  # recipe-chain order
        souls = [c for c in self._chars if not c.craftable_only]

        if tab == "weapons":
            return weapons
        if tab == "craftable":
            return [_Entry(c.id, c.name, c.emoji) for c in craftables]
        if tab == "souls":
            return [_Entry(c.id, c.name, c.emoji) for c in souls]
        if tab == "all":
            return (
                [_Entry(c.id, c.name, c.emoji) for c in souls]
                + [_Entry(c.id, c.name, c.emoji) for c in craftables]
                + weapons
            )
        return [_Entry(c.id, c.name, c.emoji) for c in souls if completion_group(c.name) == tab]

    def _is_owned(self, e: _Entry) -> bool:
        if e.is_weapon:
            return e.id in self._owned_weapon_ids
        return e.id in (self._owned_reiatsu_ids if self.mode == "reiatsu" else self._owned_char_ids)

    def render(self, client: discord.Client):
        all_chars, all_weapons = self._chars, self._weapons
        if self.mode == "reiatsu":
            total = len(all_chars)
            owned = sum(1 for c in all_chars if c.id in self._owned_reiatsu_ids)
        else:
            total = len(all_chars) + len(all_weapons)
            owned = (
                sum(1 for c in all_chars if c.id in self._owned_char_ids)
                + sum(1 for w in all_weapons if w.id in self._owned_weapon_ids)
            )
        self.overall_percent = (owned / total * 100) if total else 0.0

        entries = self._entries_for(self.tab)
        have = [e for e in entries if self._is_owned(e)]
        missing = [e for e in entries if not self._is_owned(e)]
        self.owned_count, self.total_count = len(have), len(entries)

        _label, _icon, noun = TAB_INFO[self.tab]
        if self.mode == "reiatsu":
            noun = f"Reiatsu {noun}"
        packer = _PagePacker()
        packer.add_section(f"Owned {noun}", [_token(e, client) for e in have], "Nothing yet.")
        packer.add_section(f"Missing {noun}", [_token(e, client) for e in missing], "Nothing missing - complete!")
        self.pages = packer.finish()
        self.page = min(self.page, len(self.pages) - 1)

        for key, button in self._tab_buttons.items():
            button.style = discord.ButtonStyle.primary if key == self.tab else discord.ButtonStyle.secondary
            button.disabled = self.mode == "reiatsu" and key == "weapons"
        for mode, button in self._mode_buttons.items():
            button.style = discord.ButtonStyle.success if mode == self.mode else discord.ButtonStyle.secondary
        self.previous_button.disabled = self.page == 0
        self.next_button.disabled = self.page >= len(self.pages) - 1

    def build_embed(self) -> discord.Embed:
        name = self.target.display_name
        label, icon, noun = TAB_INFO[self.tab]
        reiatsu = self.mode == "reiatsu"
        if reiatsu:
            noun = f"Reiatsu {noun}"
        prefix = "Reiatsu " if reiatsu else ""
        if self.tab == "souls":
            title = (f"{name}'s Reiatsu progression: {self.overall_percent:.1f}%" if reiatsu
                     else f"{name}'s BleachDex progression: {self.overall_percent:.1f}%")
        elif self.tab == "all":
            title = f"{name}'s Complete {prefix}Collection"
        else:
            title = f"{name}'s {prefix}{label} Completion"

        percent = (self.owned_count / self.total_count * 100) if self.total_count else 0.0
        header = f"**{self.owned_count}/{self.total_count} {noun}** \u2022 {percent:.1f}%"
        embed = discord.Embed(
            title=title,
            description=f"{header}\n\n{self.pages[self.page]}",
            color=discord.Color(REIATSU_COLOR) if reiatsu else discord.Color.gold(),
        )
        footer = (f"Reiatsu progression: {self.overall_percent:.1f}%" if reiatsu
                  else f"BleachDex progression: {self.overall_percent:.1f}%")
        if len(self.pages) > 1:
            footer += f"  \u2022  Page {self.page + 1}/{len(self.pages)}"
        embed.set_footer(text=footer)
        return embed

    # -- interaction plumbing ----------------------------------------------

    async def _guard(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "Only the person who ran this command can use this.", ephemeral=True
            )
            return False
        return True

    def _make_tab_callback(self, key: str):
        async def callback(interaction: discord.Interaction):
            if not await self._guard(interaction):
                return
            await interaction.response.defer()
            await asyncio.to_thread(self.load)
            self.tab, self.page = key, 0
            self.render(interaction.client)
            await interaction.edit_original_response(embed=self.build_embed(), view=self)
        return callback

    def _make_mode_callback(self, mode: str):
        async def callback(interaction: discord.Interaction):
            if not await self._guard(interaction):
                return
            await interaction.response.defer()
            await asyncio.to_thread(self.load)
            self.mode, self.page = mode, 0
            if mode == "reiatsu" and self.tab == "weapons":
                self.tab = "souls"  # no Reiatsu weapons - fall back to the main page
            self.render(interaction.client)
            await interaction.edit_original_response(embed=self.build_embed(), view=self)
        return callback

    async def _turn_page(self, interaction: discord.Interaction, delta: int):
        if not await self._guard(interaction):
            return
        self.page = max(0, min(self.page + delta, len(self.pages) - 1))
        self.previous_button.disabled = self.page == 0
        self.next_button.disabled = self.page >= len(self.pages) - 1
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def _on_previous(self, interaction: discord.Interaction):
        await self._turn_page(interaction, -1)

    async def _on_next(self, interaction: discord.Interaction):
        await self._turn_page(interaction, +1)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


class CollectionGroup(app_commands.Group):
    def __init__(self):
        super().__init__(name="collection", description="View your character collection")

    @app_commands.command(name="completion", description="See your collection progress")
    async def completion(
        self, interaction: discord.Interaction, user: Optional[discord.User] = None
    ):
        target = user or interaction.user
        await interaction.response.defer()
        view = CompletionView(owner_id=interaction.user.id, target=target)
        await asyncio.to_thread(view.load)
        view.render(interaction.client)
        view.message = await interaction.followup.send(embed=view.build_embed(), view=view, wait=True)

    @app_commands.command(name="inventory", description="Pick a category to see what you own: weapons, souls, or drops")
    async def inventory(
        self, interaction: discord.Interaction, user: Optional[discord.User] = None
    ):
        target = user or interaction.user
        view = InventoryView(owner_id=interaction.user.id, target=target)
        await interaction.response.send_message(embed=view.build_embed(), view=view)
        view.message = await interaction.original_response()


class Collection(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.bot.tree.add_command(CollectionGroup())


async def setup(bot: commands.Bot):
    await bot.add_cog(Collection(bot))