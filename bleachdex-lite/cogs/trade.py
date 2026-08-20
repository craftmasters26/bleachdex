"""
/trade start   - propose a trade: you offer one of your items, they offer one of theirs
/trade cancel  - cancel a trade you're part of

Nobody's items move until BOTH sides press Accept. Either side can
press Decline/Cancel any time before that to back out.
"""

from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from db import trades as tr, characters as ch, weapons as wp, collection as coll, achievements as ach


async def _your_item_autocomplete(interaction: discord.Interaction, current: str):
    item_type = getattr(interaction.namespace, "your_item_type", None)
    kind = item_type.value if isinstance(item_type, app_commands.Choice) else item_type
    if kind not in ("character", "weapon"):
        return []
    current = (current or "").lower()
    if kind == "character":
        names = [ch.get_character(o.character_id).name for o in coll.list_owned_characters(interaction.user.id)]
    else:
        names = [wp.get_weapon(o.weapon_id).name for o in coll.list_owned_weapons(interaction.user.id)]
    names = sorted({n for n in names if current in n.lower()})
    return [app_commands.Choice(name=n, value=n) for n in names[:25]]


async def _their_item_autocomplete(interaction: discord.Interaction, current: str):
    partner = getattr(interaction.namespace, "partner", None)
    if partner is None:
        return []
    partner_id = partner.id if hasattr(partner, "id") else int(partner)
    item_type = getattr(interaction.namespace, "their_item_type", None)
    kind = item_type.value if isinstance(item_type, app_commands.Choice) else item_type
    if kind not in ("character", "weapon"):
        return []
    current = (current or "").lower()
    if kind == "character":
        names = [ch.get_character(o.character_id).name for o in coll.list_owned_characters(partner_id)]
    else:
        names = [wp.get_weapon(o.weapon_id).name for o in coll.list_owned_weapons(partner_id)]
    names = sorted({n for n in names if current in n.lower()})
    return [app_commands.Choice(name=n, value=n) for n in names[:25]]


def _describe_offer(offer: dict) -> str:
    if offer["kind"] == "character":
        inst = coll.get_owned_character_instance(offer["instance_id"])
        char = ch.get_character(inst.character_id) if inst else None
        return f"🧍 {char.name}" if char else "(unknown character)"
    else:
        inst = coll.get_owned_weapon_instance(offer["instance_id"])
        weapon = wp.get_weapon(inst.weapon_id) if inst else None
        return f"🗡️ {weapon.name}" if weapon else "(unknown weapon)"


def _trade_embed(trade: tr.Trade, user_a: discord.abc.User, user_b: discord.abc.User) -> discord.Embed:
    embed = discord.Embed(
        title="🔄 Trade proposal",
        description="Both sides must press **Accept** for this trade to go through.",
        color=discord.Color.teal(),
    )
    a_status = "✅ accepted" if trade.user_a_accepted else "⏳ waiting"
    b_status = "✅ accepted" if trade.user_b_accepted else "⏳ waiting"
    embed.add_field(
        name=f"{user_a.display_name} offers ({a_status})",
        value=_describe_offer(trade.user_a_offer), inline=True,
    )
    embed.add_field(
        name=f"{user_b.display_name} offers ({b_status})",
        value=_describe_offer(trade.user_b_offer), inline=True,
    )
    embed.set_footer(text=f"Trade #{trade.id} — status: {trade.status}")
    return embed


class TradeView(discord.ui.View):
    def __init__(self, trade_id: int, user_a: discord.abc.User, user_b: discord.abc.User):
        super().__init__(timeout=600)  # 10 minutes to resolve
        self.trade_id = trade_id
        self.user_a = user_a
        self.user_b = user_b

    async def _refresh_or_close(self, interaction: discord.Interaction, trade: tr.Trade):
        embed = _trade_embed(trade, self.user_a, self.user_b)
        if trade.status == "completed":
            embed.title = "✅ Trade completed!"
            embed.color = discord.Color.green()
            self.stop()
            await interaction.response.edit_message(embed=embed, view=None)
            for user in (self.user_a, self.user_b):
                newly_earned = ach.check_and_grant(user.id)
                for a in newly_earned:
                    await interaction.followup.send(
                        f"🏅 {user.mention} unlocked the **{a.name}** achievement — {a.description}!"
                    )
        else:
            await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in (self.user_a.id, self.user_b.id):
            await interaction.response.send_message(
                "This isn't your trade.", ephemeral=True
            )
            return
        try:
            trade = tr.accept_trade(self.trade_id, interaction.user.id)
        except tr.TradeError as e:
            await interaction.response.send_message(f"❌ {e}", ephemeral=True)
            return
        await self._refresh_or_close(interaction, trade)

    @discord.ui.button(label="Decline / Cancel", style=discord.ButtonStyle.danger)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in (self.user_a.id, self.user_b.id):
            await interaction.response.send_message(
                "This isn't your trade.", ephemeral=True
            )
            return
        try:
            trade = tr.cancel_trade(self.trade_id, interaction.user.id)
        except tr.TradeError as e:
            await interaction.response.send_message(f"❌ {e}", ephemeral=True)
            return
        embed = _trade_embed(trade, self.user_a, self.user_b)
        embed.title = "❌ Trade cancelled"
        embed.color = discord.Color.red()
        self.stop()
        await interaction.response.edit_message(embed=embed, view=None)


class TradeGroup(app_commands.Group):
    def __init__(self):
        super().__init__(name="trade", description="Trade characters/weapons with another player")

    @app_commands.command(name="start", description="Propose a trade with another player")
    @app_commands.describe(
        their_item_type="Is the item you're asking for a character or a weapon?",
        their_item_name="Name of the character/weapon they own that you want",
        your_item_type="Is the item you're offering a character or a weapon?",
        your_item_name="Name of the character/weapon you own that you're offering",
    )
    @app_commands.choices(
        their_item_type=[
            app_commands.Choice(name="Character", value="character"),
            app_commands.Choice(name="Weapon", value="weapon"),
        ],
        your_item_type=[
            app_commands.Choice(name="Character", value="character"),
            app_commands.Choice(name="Weapon", value="weapon"),
        ],
    )
    @app_commands.autocomplete(your_item_name=_your_item_autocomplete, their_item_name=_their_item_autocomplete)
    async def start(
        self,
        interaction: discord.Interaction,
        partner: discord.User,
        your_item_type: app_commands.Choice[str],
        your_item_name: str,
        their_item_type: app_commands.Choice[str],
        their_item_name: str,
    ):
        if partner.bot:
            await interaction.response.send_message("You can't trade with a bot.", ephemeral=True)
            return

        you = interaction.user

        def _find_instance(user_id: int, kind: str, name: str) -> Optional[int]:
            if kind == "character":
                inst = coll.find_owned_character_by_name(user_id, name)
            else:
                inst = coll.find_owned_weapon_by_name(user_id, name)
            return inst.id if inst else None

        your_instance_id = _find_instance(you.id, your_item_type.value, your_item_name)
        if your_instance_id is None:
            await interaction.response.send_message(
                f"You don't own a {your_item_type.value} named **{your_item_name}**.",
                ephemeral=True,
            )
            return

        their_instance_id = _find_instance(partner.id, their_item_type.value, their_item_name)
        if their_instance_id is None:
            await interaction.response.send_message(
                f"{partner.display_name} doesn't own a {their_item_type.value} "
                f"named **{their_item_name}**.",
                ephemeral=True,
            )
            return

        try:
            trade_id = tr.create_trade(
                user_a_id=you.id,
                user_a_offer={"kind": your_item_type.value, "instance_id": your_instance_id},
                user_b_id=partner.id,
                user_b_offer={"kind": their_item_type.value, "instance_id": their_instance_id},
            )
        except tr.TradeError as e:
            await interaction.response.send_message(f"❌ {e}", ephemeral=True)
            return

        trade = tr.get_trade(trade_id)
        embed = _trade_embed(trade, you, partner)
        view = TradeView(trade_id, you, partner)
        await interaction.response.send_message(
            content=f"{partner.mention}, {you.mention} wants to trade with you!",
            embed=embed, view=view,
        )


class Trade(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.bot.tree.add_command(TradeGroup())


async def setup(bot: commands.Bot):
    await bot.add_cog(Trade(bot))