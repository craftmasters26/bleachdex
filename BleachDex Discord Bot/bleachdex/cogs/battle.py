""""
/battle - challenge another player to a full team battle (3v3).

Both players need a team set up first via /team add. Fighters go out
in slot order; a fighter who wins their matchup keeps their remaining
HP into the next fight. First team fully knocked out loses.

Battling doesn't consume or damage your cards - HP resets between
battles. Say the word if you want stakes (e.g. wager KAN coins, or
losers give up a card) added on top of this.
"""

import io

import discord
from discord import app_commands
from discord.ext import commands

from db import collection as coll, characters as ch, teams, players as pl, achievements as ach
from logic.battle import simulate_team_battle, Fighter

MAX_EMBED_DESCRIPTION = 4000  # Discord's real cap is 4096; leave a little headroom


def _effective_attack(owned_char) -> int:
    """Base attack plus equipped weapon's attack_bonus, if any."""
    base = owned_char.attack
    if owned_char.equipped_weapon_instance_id:
        weapon_inst = coll.get_owned_weapon_instance(owned_char.equipped_weapon_instance_id)
        if weapon_inst:
            base += weapon_inst.attack_bonus
    return base


def _build_fighters(team, owner_display_name: str) -> list[Fighter]:
    fighters = []
    for inst in team:
        char = ch.get_character(inst.character_id)
        fighters.append(
            Fighter(
                name=char.name,
                max_hp=inst.health,
                attack=_effective_attack(inst),
                owner_label=owner_display_name,
            )
        )
    return fighters


class BattleCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="battle", description="Challenge another player to a 3v3 team battle")
    async def battle(self, interaction: discord.Interaction, opponent: discord.User):
        if opponent.bot:
            await interaction.response.send_message("You can't battle a bot.", ephemeral=True)
            return
        if opponent.id == interaction.user.id:
            await interaction.response.send_message("You can't battle yourself.", ephemeral=True)
            return

        challenger_team = teams.get_team(interaction.user.id)
        if challenger_team is None:
            await interaction.response.send_message(
                "You don't have a full 3-character team set up yet — use "
                "`/team add` first.",
                ephemeral=True,
            )
            return

        opponent_team = teams.get_team(opponent.id)
        if opponent_team is None:
            await interaction.response.send_message(
                f"{opponent.display_name} doesn't have a full 3-character team "
                f"set up yet — they need to use `/team add` first.",
                ephemeral=True,
            )
            return

        fighters_a = _build_fighters(challenger_team, interaction.user.display_name)
        fighters_b = _build_fighters(opponent_team, opponent.display_name)

        result = simulate_team_battle(
            fighters_a, fighters_b,
            team_a_label=interaction.user.display_name,
            team_b_label=opponent.display_name,
        )

        full_log = "\n".join(result.log)
        embed = discord.Embed(
            title=f"🏆 {result.winning_team_label}'s team wins!",
            color=discord.Color.orange(),
        )

        winner_user = interaction.user if result.winning_team_label == interaction.user.display_name else opponent
        loser_user = opponent if winner_user is interaction.user else interaction.user
        pl.record_battle_win(winner_user.id)
        pl.record_battle_loss(loser_user.id)

        if len(full_log) <= MAX_EMBED_DESCRIPTION:
            embed.description = full_log
            await interaction.response.send_message(embed=embed)
        else:
            # Long battle logs (lots of rounds) can exceed Discord's embed
            # limit - post a short summary and attach the full log as a file.
            embed.description = (
                f"Full battle log attached below ({result.rounds} rounds)."
            )
            file = discord.File(
                io.BytesIO(full_log.encode("utf-8")), filename="battle_log.txt"
            )
            await interaction.response.send_message(embed=embed, file=file)

        newly_earned = ach.check_and_grant(winner_user.id)
        for a in newly_earned:
            await interaction.followup.send(
                f"🏅 {winner_user.mention} unlocked the **{a.name}** achievement — {a.description}!"
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(BattleCog(bot))