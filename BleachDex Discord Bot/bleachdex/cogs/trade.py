"""
/trade start partner:@user - propose a trade
/trade add item:<name> kind:<character|weapon> - add one of YOUR
    owned items to your side of your active trade
/trade remove item:<name> kind:<character|weapon> - remove one

The embed also has buttons/dropdowns for everything (matching the
reference UI): a dropdown per side to remove an item, a "Change"
button per side to set a KAN coin amount, and Lock proposal / Reset /
Cancel trade. Both sides must press Lock for anything to actually
move - editing either side (item or coins) unlocks BOTH sides again,
so nobody can lock in a stale version of the other person's offer.
Trade proposals expire after 30 minutes.
"""

from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from db import trade as tr, characters as ch, weapons as wp, collection as coll, achievements as ach, player_stats as pstats
from discord_utils import kan_label
from reiatsu import display_name


def _item_label(item: tr.TradeItem) -> str:
    if item.kind == "character":
        inst = coll.get_owned_character_instance(item.instance_id)
        char = ch.get_character(inst.character_id) if inst else None
        # A Reiatsu copy is labelled as one, so the other side can see it
        # before locking the trade.
        return display_name(char.name, bool(inst.is_reiatsu)) if char else "(unknown character)"
    else:
        inst = coll.get_owned_weapon_instance(item.instance_id)
        weapon = wp.get_weapon(inst.weapon_id) if inst else None
        return weapon.name if weapon else "(unknown weapon)"


def _side_text(trade: tr.Trade, side: str, kan: str = "KAN") -> str:
    items = tr.list_items(trade.id, side)
    coins = trade.user_a_coins if side == "a" else trade.user_b_coins
    locked = trade.user_a_locked if side == "a" else trade.user_b_locked

    lines = [f"{len(items)} item(s) selected"]
    for item in items:
        lines.append(f"- {_item_label(item)} ({item.kind})")
    lines.append(f"{kan} proposed: {coins}")
    lines.append("Locked" if locked else "Not locked")
    return "\n".join(lines)


def build_trade_embed(
    trade: tr.Trade, user_a: discord.abc.User, user_b: discord.abc.User, kan: str = "KAN"
) -> discord.Embed:
    embed = discord.Embed(
        title="Trade proposal",
        description="Edit with `/trade add` and `/trade remove`, or the dropdowns below. "
                    "Both sides must Lock before anything moves.",
        color=discord.Color.teal(),
    )
    embed.add_field(name=f"{user_a.display_name}'s proposal", value=_side_text(trade, "a", kan), inline=True)
    embed.add_field(name=f"{user_b.display_name}'s proposal", value=_side_text(trade, "b", kan), inline=True)
    if trade.status != "pending":
        embed.color = discord.Color.green() if trade.status == "completed" else discord.Color.red()
        embed.title = f"Trade {trade.status}"
    embed.set_footer(text=f"Trade #{trade.id} - expires in 30 minutes from creation if not completed")
    return embed


class CoinsModal(discord.ui.Modal, title="Set your KAN offer"):
    coins = discord.ui.TextInput(label="KAN coins to offer (0 for none)", default="0", required=True)

    def __init__(self, trade_id: int, side: str, cog: "Trade"):
        super().__init__()
        self.trade_id = trade_id
        self.side = side
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amount = int(self.coins.value)
            tr.set_coins(self.trade_id, self.side, amount)
        except (ValueError, tr.TradeError) as e:
            await interaction.response.send_message(f"{e}", ephemeral=True)
            return
        await self.cog.refresh(interaction, self.trade_id)


class RemoveItemSelect(discord.ui.Select):
    def __init__(self, trade_id: int, side: str, owner_id: int, items: list, cog: "Trade"):
        options = [
            discord.SelectOption(label=_item_label(item)[:100], value=f"{item.kind}:{item.instance_id}")
            for item in items[:25]
        ]
        super().__init__(placeholder="Remove an item...", options=options, row=0 if side == "a" else 1)
        self.trade_id = trade_id
        self.side = side
        self.owner_id = owner_id
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("That's not your side of the trade.", ephemeral=True)
            return
        kind, instance_id = self.values[0].split(":")
        tr.remove_item(self.trade_id, self.side, kind, int(instance_id))
        await self.cog.refresh(interaction, self.trade_id)


class ChangeCoinsButton(discord.ui.Button):
    def __init__(self, trade_id: int, side: str, owner_id: int, label_name: str, cog: "Trade"):
        super().__init__(label=f"Change {label_name}'s KAN", style=discord.ButtonStyle.secondary, row=2)
        self.trade_id = trade_id
        self.side = side
        self.owner_id = owner_id
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("That's not your side of the trade.", ephemeral=True)
            return
        await interaction.response.send_modal(CoinsModal(self.trade_id, self.side, self.cog))


class LockButton(discord.ui.Button):
    def __init__(self, trade_id: int, cog: "Trade"):
        super().__init__(label="Lock proposal", style=discord.ButtonStyle.success, row=3)
        self.trade_id = trade_id
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        try:
            trade = tr.lock_side(self.trade_id, interaction.user.id)
        except tr.TradeError as e:
            await interaction.response.send_message(f"{e}", ephemeral=True)
            return

        await self.cog.refresh(interaction, self.trade_id)

        if trade.status == "completed" and interaction.guild is not None:
            guild = interaction.guild

            async def _is_admin(user_id: int) -> bool:
                member = guild.get_member(user_id)
                if member is None:
                    try:
                        member = await guild.fetch_member(user_id)
                    except discord.HTTPException:
                        return False
                return member.guild_permissions.administrator

            a_is_admin = await _is_admin(trade.user_a_id)
            b_is_admin = await _is_admin(trade.user_b_id)
            if b_is_admin:
                pstats.increment(trade.user_a_id, "traded_with_admin")
            if a_is_admin:
                pstats.increment(trade.user_b_id, "traded_with_admin")

            owner_id = guild.owner_id
            if trade.user_b_id == owner_id:
                pstats.increment(trade.user_a_id, "traded_with_owner")
            if trade.user_a_id == owner_id:
                pstats.increment(trade.user_b_id, "traded_with_owner")

            newly_a = ach.check_and_grant(trade.user_a_id)
            newly_b = ach.check_and_grant(trade.user_b_id)
            for uid, earned in ((trade.user_a_id, newly_a), (trade.user_b_id, newly_b)):
                for a in earned:
                    await interaction.followup.send(
                        f"<@{uid}> unlocked the **{a.name}** achievement — {a.description}!"
                    )


class ResetButton(discord.ui.Button):
    def __init__(self, trade_id: int, cog: "Trade"):
        super().__init__(label="Reset", style=discord.ButtonStyle.secondary, row=3)
        self.trade_id = trade_id
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        trade = tr.get_trade(self.trade_id)
        side = trade.side_for(interaction.user.id) if trade else None
        if side is None:
            await interaction.response.send_message("You're not part of this trade.", ephemeral=True)
            return
        tr.reset_side(self.trade_id, side)
        await self.cog.refresh(interaction, self.trade_id)


class CancelButton(discord.ui.Button):
    def __init__(self, trade_id: int, cog: "Trade"):
        super().__init__(label="Cancel trade", style=discord.ButtonStyle.danger, row=3)
        self.trade_id = trade_id
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        trade = tr.get_trade(self.trade_id)
        if trade is None or trade.side_for(interaction.user.id) is None:
            await interaction.response.send_message("You're not part of this trade.", ephemeral=True)
            return
        tr.cancel_trade(self.trade_id)
        await self.cog.refresh(interaction, self.trade_id)


class TradeView(discord.ui.View):
    def __init__(self, trade_id: int, user_a: discord.abc.User, user_b: discord.abc.User, cog: "Trade"):
        super().__init__(timeout=tr.TRADE_TIMEOUT_SECONDS)
        self.trade_id = trade_id
        self.user_a = user_a
        self.user_b = user_b
        self.cog = cog
        self._rebuild()

    def _rebuild(self):
        self.clear_items()
        a_items = tr.list_items(self.trade_id, "a")
        b_items = tr.list_items(self.trade_id, "b")
        if a_items:
            self.add_item(RemoveItemSelect(self.trade_id, "a", self.user_a.id, a_items, self.cog))
        if b_items:
            self.add_item(RemoveItemSelect(self.trade_id, "b", self.user_b.id, b_items, self.cog))
        self.add_item(ChangeCoinsButton(self.trade_id, "a", self.user_a.id, self.user_a.display_name, self.cog))
        self.add_item(ChangeCoinsButton(self.trade_id, "b", self.user_b.id, self.user_b.display_name, self.cog))
        self.add_item(LockButton(self.trade_id, self.cog))
        self.add_item(ResetButton(self.trade_id, self.cog))
        self.add_item(CancelButton(self.trade_id, self.cog))

    async def on_timeout(self):
        trade = tr.get_trade(self.trade_id)
        if trade and trade.status == "pending":
            tr.expire_trade(self.trade_id)


def _resolve_owned_item(user_id: int, kind: str, name: str):
    if kind == "character":
        # spare_first: a name-based trade offers a plain copy before a Reiatsu one
        return coll.find_owned_character_by_name(user_id, name, spare_first=True)
    return coll.find_owned_weapon_by_name(user_id, name)


class Trade(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def refresh(self, interaction: discord.Interaction, trade_id: int):
        """Re-fetches trade state and edits the message in place -
        shared by every button/select callback so the embed always
        reflects the current DB state, not stale data from when the
        view was first built."""
        trade = tr.get_trade(trade_id)
        user_a = await self.bot.fetch_user(trade.user_a_id)
        user_b = await self.bot.fetch_user(trade.user_b_id)
        embed = build_trade_embed(trade, user_a, user_b, kan_label(interaction.client))

        if trade.status != "pending":
            if interaction.response.is_done():
                await interaction.edit_original_response(embed=embed, view=None)
            else:
                await interaction.response.edit_message(embed=embed, view=None)
            return

        view = TradeView(trade_id, user_a, user_b, self)
        if interaction.response.is_done():
            await interaction.edit_original_response(embed=embed, view=view)
        else:
            await interaction.response.edit_message(embed=embed, view=view)

    trade_group = app_commands.Group(name="trade", description="Propose and manage trades")

    async def _give_name_autocomplete(self, interaction: discord.Interaction, current: str):
        current = (current or "").lower()
        names = []
        for inst in coll.list_owned_characters(interaction.user.id):
            char = ch.get_character(inst.character_id)
            if char and current in char.name.lower():
                names.append(char.name)
        for inst in coll.list_owned_weapons(interaction.user.id):
            weapon = wp.get_weapon(inst.weapon_id)
            if weapon and current in weapon.name.lower():
                names.append(weapon.name)
        seen, out = set(), []
        for n in names:
            if n not in seen:
                seen.add(n)
                out.append(n)
            if len(out) >= 25:
                break
        return [app_commands.Choice(name=n, value=n) for n in out]

    @app_commands.command(
        name="give", description="Give one of your owned characters/weapons directly to someone"
    )
    @app_commands.autocomplete(name=_give_name_autocomplete)
    async def give(self, interaction: discord.Interaction, user: discord.User, name: str):
        """One-way, immediate, unconditional transfer - no negotiation
        or acceptance needed, unlike /trade above. Use /trade instead
        if you want something back for it. Auto-detects whether `name`
        is a character or a weapon by checking your inventory for
        both - no need to specify which."""
        if user.bot:
            await interaction.response.send_message("You can't give something to a bot.", ephemeral=True)
            return
        if user.id == interaction.user.id:
            await interaction.response.send_message("You already own that.", ephemeral=True)
            return

        # spare_first: /give hands over a plain copy before a Reiatsu one
        char_inst = coll.find_owned_character_by_name(interaction.user.id, name, spare_first=True)
        weapon_inst = coll.find_owned_weapon_by_name(interaction.user.id, name)

        if char_inst and weapon_inst:
            await interaction.response.send_message(
                f"You own both a character AND a weapon named **{name}** - "
                f"rename one or ask an admin, `/give` can't tell them apart.",
                ephemeral=True,
            )
            return
        if char_inst:
            coll.transfer_character(char_inst.id, user.id)
        elif weapon_inst:
            coll.transfer_weapon(weapon_inst.id, user.id)
        else:
            await interaction.response.send_message(
                f"You don't own a character or weapon named **{name}**.", ephemeral=True
            )
            return

        await interaction.response.send_message(
            f"{interaction.user.mention} gave **{name}** to {user.mention}."
        )

    @trade_group.command(name="start", description="Propose a trade with another player")
    async def start(self, interaction: discord.Interaction, partner: discord.User):
        if partner.bot:
            await interaction.response.send_message("You can't trade with a bot.", ephemeral=True)
            return
        try:
            trade = tr.create_trade(interaction.user.id, partner.id)
        except tr.TradeError as e:
            await interaction.response.send_message(f"{e}", ephemeral=True)
            return

        embed = build_trade_embed(trade, interaction.user, partner, kan_label(interaction.client))
        view = TradeView(trade.id, interaction.user, partner, self)
        await interaction.response.send_message(
            content=f"Hey {partner.mention}, {interaction.user.mention} is proposing a trade!",
            embed=embed, view=view,
        )
        message = await interaction.original_response()
        tr.attach_message(trade.id, message.channel.id, message.id)

    @trade_group.command(name="add", description="Add one of your owned items to your active trade")
    @app_commands.choices(kind=[
        app_commands.Choice(name="Character", value="character"),
        app_commands.Choice(name="Weapon", value="weapon"),
    ])
    async def add(self, interaction: discord.Interaction, kind: app_commands.Choice[str], name: str):
        trade = tr.get_active_trade_for_user(interaction.user.id)
        if trade is None:
            await interaction.response.send_message("You don't have an active trade. Use `/trade start` first.", ephemeral=True)
            return
        side = trade.side_for(interaction.user.id)
        inst = _resolve_owned_item(interaction.user.id, kind.value, name)
        if inst is None:
            await interaction.response.send_message(f"You don't own a {kind.value} named **{name}**.", ephemeral=True)
            return
        try:
            tr.add_item(trade.id, side, kind.value, inst.id)
        except tr.TradeError as e:
            await interaction.response.send_message(f"{e}", ephemeral=True)
            return
        await interaction.response.send_message(f"Added **{name}** to your proposal.", ephemeral=True)
        await self._resend_public_update(interaction, trade.id)

    @trade_group.command(name="remove", description="Remove an item from your active trade")
    @app_commands.choices(kind=[
        app_commands.Choice(name="Character", value="character"),
        app_commands.Choice(name="Weapon", value="weapon"),
    ])
    async def remove(self, interaction: discord.Interaction, kind: app_commands.Choice[str], name: str):
        trade = tr.get_active_trade_for_user(interaction.user.id)
        if trade is None:
            await interaction.response.send_message("You don't have an active trade.", ephemeral=True)
            return
        side = trade.side_for(interaction.user.id)
        inst = _resolve_owned_item(interaction.user.id, kind.value, name)
        if inst is None or not tr.remove_item(trade.id, side, kind.value, inst.id):
            await interaction.response.send_message(f"**{name}** isn't in your proposal.", ephemeral=True)
            return
        await interaction.response.send_message(f"Removed **{name}** from your proposal.", ephemeral=True)
        await self._resend_public_update(interaction, trade.id)

    async def _resend_public_update(self, interaction: discord.Interaction, trade_id: int):
        """/trade add and /trade remove reply ephemerally (so the
        command invocation itself isn't spammy), but the actual trade
        message everyone can see still needs to reflect the change."""
        trade = tr.get_trade(trade_id)
        if not trade or not trade.channel_id or not trade.message_id:
            return
        channel = self.bot.get_channel(trade.channel_id)
        if channel is None:
            return
        try:
            message = await channel.fetch_message(trade.message_id)
        except discord.NotFound:
            return
        user_a = await self.bot.fetch_user(trade.user_a_id)
        user_b = await self.bot.fetch_user(trade.user_b_id)
        embed = build_trade_embed(trade, user_a, user_b, kan_label(interaction.client))
        view = TradeView(trade_id, user_a, user_b, self) if trade.status == "pending" else None
        await message.edit(embed=embed, view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(Trade(bot))