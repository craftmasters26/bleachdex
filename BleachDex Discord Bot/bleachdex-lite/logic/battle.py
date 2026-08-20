"""
Turn-based battle: two fighters take turns attacking using their
attack stat (plus equipped weapon bonus, if any) against the other's
remaining HP, until one hits 0.

Battles don't permanently damage owned cards - HP resets each fight.
This is a pure function (no Discord, no DB writes) so it's easy to
test and easy to reuse if you want a different presentation later.
"""

from dataclasses import dataclass


@dataclass
class Fighter:
    name: str
    max_hp: int
    attack: int
    owner_label: str  # e.g. the Discord display name, for the log


@dataclass
class BattleResult:
    log: list[str]
    winner: Fighter
    loser: Fighter
    rounds: int


def simulate_battle(fighter_a: Fighter, fighter_b: Fighter, max_rounds: int = 100) -> BattleResult:
    if fighter_a.max_hp <= 0 or fighter_b.max_hp <= 0:
        raise ValueError("Fighters must start with positive HP.")
    if fighter_a.attack <= 0 or fighter_b.attack <= 0:
        raise ValueError("Fighters must have positive attack to ever land a hit.")

    hp_a, hp_b = fighter_a.max_hp, fighter_b.max_hp
    log: list[str] = [
        f"⚔️ {fighter_a.name} ({fighter_a.owner_label}, {hp_a} HP / {fighter_a.attack} ATK) "
        f"vs {fighter_b.name} ({fighter_b.owner_label}, {hp_b} HP / {fighter_b.attack} ATK)"
    ]

    attacker, defender = fighter_a, fighter_b
    attacker_hp, defender_hp = hp_a, hp_b
    rounds = 0

    while attacker_hp > 0 and defender_hp > 0 and rounds < max_rounds:
        rounds += 1
        defender_hp -= attacker.attack
        defender_hp = max(defender_hp, 0)
        log.append(
            f"Round {rounds}: {attacker.name} hits {defender.name} for "
            f"{attacker.attack} — {defender.name} has {defender_hp} HP left."
        )
        if defender_hp <= 0:
            break
        # swap roles for the next round
        attacker, defender = defender, attacker
        attacker_hp, defender_hp = defender_hp, attacker_hp

    # after the loop, `defender` is the one who just dropped to 0 (the loser),
    # unless we hit max_rounds without a knockout
    if defender_hp <= 0:
        winner, loser = attacker, defender
        log.append(f"🏆 {winner.name} wins!")
    else:
        # round cap reached - higher remaining HP wins as a tiebreak
        if attacker_hp >= defender_hp:
            winner, loser = attacker, defender
        else:
            winner, loser = defender, attacker
        log.append(f"⏱️ Round limit reached — {winner.name} wins on remaining HP.")

    return BattleResult(log=log, winner=winner, loser=loser, rounds=rounds)


@dataclass
class TeamBattleResult:
    log: list[str]
    winning_team_label: str
    losing_team_label: str
    rounds: int


def simulate_team_battle(
    team_a: list[Fighter],
    team_b: list[Fighter],
    team_a_label: str,
    team_b_label: str,
    max_rounds: int = 300,
) -> TeamBattleResult:
    """
    3v3 sequential team battle. Fighters go in slot order (index 0 is
    sent out first). A fighter who wins a matchup stays in and keeps
    fighting at their CURRENT remaining HP (not refilled) against the
    next opponent - so wearing down the other team's frontline matters.
    A team loses once all 3 of its fighters have been knocked out.
    """
    for team, label in ((team_a, team_a_label), (team_b, team_b_label)):
        for f in team:
            if f.max_hp <= 0 or f.attack <= 0:
                raise ValueError(
                    f"{label}'s fighter {f.name} must have positive HP and attack."
                )

    idx_a, idx_b = 0, 0
    hp_a = team_a[0].max_hp
    hp_b = team_b[0].max_hp

    log: list[str] = [
        f"⚔️ **{team_a_label}** ({', '.join(f.name for f in team_a)}) vs "
        f"**{team_b_label}** ({', '.join(f.name for f in team_b)})"
    ]

    rounds = 0
    # Whoever's turn it is to attack first each matchup alternates starting
    # with team A's first fighter attacking first.
    a_attacks_first = True

    while idx_a < len(team_a) and idx_b < len(team_b) and rounds < max_rounds:
        fighter_a, fighter_b = team_a[idx_a], team_b[idx_b]
        log.append(
            f"\n🥊 {team_a_label}'s **{fighter_a.name}** ({hp_a} HP) enters "
            f"against {team_b_label}'s **{fighter_b.name}** ({hp_b} HP)."
        )

        if a_attacks_first:
            attacker_side, defender_side = "a", "b"
        else:
            attacker_side, defender_side = "b", "a"

        while hp_a > 0 and hp_b > 0 and rounds < max_rounds:
            rounds += 1
            if attacker_side == "a":
                hp_b -= fighter_a.attack
                hp_b = max(hp_b, 0)
                log.append(
                    f"Round {rounds}: {fighter_a.name} hits {fighter_b.name} for "
                    f"{fighter_a.attack} — {fighter_b.name} has {hp_b} HP left."
                )
                attacker_side, defender_side = "b", "a"
            else:
                hp_a -= fighter_b.attack
                hp_a = max(hp_a, 0)
                log.append(
                    f"Round {rounds}: {fighter_b.name} hits {fighter_a.name} for "
                    f"{fighter_b.attack} — {fighter_a.name} has {hp_a} HP left."
                )
                attacker_side, defender_side = "a", "b"

        if hp_a <= 0:
            log.append(f"💀 {fighter_a.name} is knocked out!")
            idx_a += 1
            a_attacks_first = False
            if idx_a < len(team_a):
                hp_a = team_a[idx_a].max_hp
        if hp_b <= 0:
            log.append(f"💀 {fighter_b.name} is knocked out!")
            idx_b += 1
            a_attacks_first = True
            if idx_b < len(team_b):
                hp_b = team_b[idx_b].max_hp

    if idx_b >= len(team_b):
        winner_label, loser_label = team_a_label, team_b_label
    else:
        winner_label, loser_label = team_b_label, team_a_label

    log.append(f"\n🏆 **{winner_label}** wins the team battle!")

    return TeamBattleResult(
        log=log, winning_team_label=winner_label, losing_team_label=loser_label, rounds=rounds
    )
