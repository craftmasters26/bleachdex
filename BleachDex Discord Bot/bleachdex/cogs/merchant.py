"""
/merchant - one command. Running it posts an embed showing this
window's 6 rotating recipes from the fixed conversion menu, each as
an exact, specific character to hand over and an exact, specific
character you get back - with a dropdown on the same message so
picking one executes it immediately, no second command.

Unlike a tier-based system, these are the literal characters pictured
- you need to actually own the one shown (in the quantity shown) to
make that trade, and you get back exactly the one shown, not a
random roll of that tier. See db/merchant.py for the recipe table,
the rotation, and the consume/grant logic this file wraps.
"""

import discord
from discord import app_commands
from discord.ext import commands

from db import merchant as mch
from discord_utils import resolve_emoji, refresh_application_emoji_cache, get_emoji_object


def _face(client: discord.Client, character, qty: int = 1) -> str:
    if character is None:
        return "???"
    mention = resolve_emoji(client, character.emoji)
    name = f"{mention} {character.name}" if mention else character.name
    return f"{qty}x {name}" if qty != 1 else name


def _select_emoji(client: discord.Client, character):
    if character is None:
        return None
    return get_emoji_object(client, character.emoji)


def _board_embed(client: discord.Client) -> discord.Embed:
    offers = mch.get_active_offers()
    _, end_utc = mch.get_window()

    lines = [
        f"{_face(client, o['give_character'], o['give_qty'])} **→** "
        f"{_face(client, o['receive_character'], o['receive_qty'])}"
        for o in offers
    ]

    embed = discord.Embed(
        title="The Merchant",
        description="\n".join(lines),
        color=discord.Color.dark_gold(),
    )
    embed.set_footer(text="Board rotates every 3 hours")
    embed.add_field(name="Next rotation", value=f"<t:{int(end_utc.timestamp())}:R>", inline=False)
    return embed


class TradeSelect(discord.ui.Select):
    def __init__(self, owner_id: int, client: discord.Client):
        self.owner_id = owner_id
        start_utc, _ = mch.get_window()
        self.window_start = int(start_utc.timestamp())
        offers = mch.get_active_offers()

        options = []
        for i, o in enumerate(offers):
            give_name = o["give_character"].name if o["give_character"] else o["give_tier"]
            receive_name = o["receive_character"].name if o["receive_character"] else o["receive_tier"]
            give_label = f"{o['give_qty']}x {give_name}" if o["give_qty"] != 1 else give_name
            receive_label = f"{o['receive_qty']}x {receive_name}" if o["receive_qty"] != 1 else receive_name
            options.append(
                discord.SelectOption(
                    label=f"{give_label} → {receive_label}",
                    value=f"{self.window_start}:{i}",
                    emoji=_select_emoji(client, o["give_character"]),
                )
            )
        super().__init__(placeholder="Exchange", options=options)

    async def callback(self, interaction: discord.Interaction):
        window_start_s, index_s = self.values[0].split(":")
        current_start, _ = mch.get_window()

        if int(window_start_s) != int(current_start.timestamp()):
            await interaction.response.send_message(
                "That trade isn't on the board anymore — the merchant just rotated. "
                "Run `/merchant` again to see the new offers.",
                ephemeral=True,
            )
            return

        offers = mch.get_active_offers()
        offer = offers[int(index_s)]
        give_char, receive_char = offer["give_character"], offer["receive_character"]
        if give_char is None or receive_char is None:
            await interaction.response.send_message(
                "That trade can't be completed right now (missing character data).",
                ephemeral=True,
            )
            return

        try:
            mch.consume_specific_character(interaction.user.id, give_char.id, offer["give_qty"])
            mch.grant_specific_character(interaction.user.id, receive_char.id, offer["receive_qty"])
        except mch.MerchantError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return

        client = interaction.client
        give_face = _face(client, give_char, offer["give_qty"])
        receive_face = _face(client, receive_char, offer["receive_qty"])

        embed = discord.Embed(
            title="Trade complete!",
            color=discord.Color.dark_gold(),
        )
        embed.add_field(name="Handed over", value=give_face, inline=True)
        embed.add_field(name="Received", value=receive_face, inline=True)

        await interaction.response.send_message(
            content=(
                f"{interaction.user.mention} exchanged **{offer['give_qty']}x {give_char.name}** "
                f"for **{offer['receive_qty']}x {receive_char.name}**!"
            ),
            embed=embed,
        )


class MerchantView(discord.ui.View):
    def __init__(self, owner_id: int, client: discord.Client):
        super().__init__(timeout=300)
        self.owner_id = owner_id
        self.add_item(TradeSelect(owner_id, client))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "This isn't your merchant menu — run /merchant yourself.", ephemeral=True
            )
            return False
        return True


class Merchant(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="merchant",
        description="See this window's rotating trades and make one",
    )
    async def merchant(self, interaction: discord.Interaction):
        await refresh_application_emoji_cache(interaction.client)
        embed = _board_embed(interaction.client)
        view = MerchantView(interaction.user.id, interaction.client)
        await interaction.response.send_message(embed=embed, view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(Merchant(bot))