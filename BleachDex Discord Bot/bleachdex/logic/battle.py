"""
logic/battle.py - 3v3 simultaneous team battle simulator.

Every round, each fighter still standing on a team attacks a randomly
chosen alive fighter on the OTHER team. All of a round's attacks are
resolved against HP as it stood at the START of that round (a
simultaneous exchange, not sequential turns) - so two fighters can
both go down in the same round if fate has them targeting each other
and neither survives the hit.

The battle ends the instant one team has zero fighters left standing
after a round resolves. If both teams are wiped in the exact same
round, it's a draw (winner_label is None). As a safety net against a
pathological all-zero-attack matchup looping forever, MAX_ROUNDS caps
it and falls back to whichever team has more total remaining HP.
"""

import random
from dataclasses import dataclass, field
from typing import Optional

MAX_ROUNDS = 100


@dataclass
class Fighter:
    name: str
    max_hp: int
    attack: int
    owner_label: str
    current_hp: int = field(init=False)
    is_ko: bool = field(init=False, default=False)

    def __post_init__(self):
        self.current_hp = self.max_hp

    def take_damage(self, amount: int) -> None:
        self.current_hp = max(0, self.current_hp - amount)
        if self.current_hp == 0:
            self.is_ko = True


@dataclass
class RoundResult:
    round_number: int
    log_line: str


class TeamBattleState:
    def __init__(self, team_a: list[Fighter], team_b: list[Fighter], label_a: str, label_b: str):
        if not team_a or not team_b:
            raise ValueError("Both teams need at least one fighter.")
        self.team_a = team_a
        self.team_b = team_b
        self.label_a = label_a
        self.label_b = label_b
        self.round_number = 1
        self.finished = False
        self.winner_label: Optional[str] = None
        self._started = False

    def _alive(self, team: list[Fighter]) -> list[Fighter]:
        return [f for f in team if not f.is_ko]

    def advance_round(self) -> Optional[RoundResult]:
        if self.finished:
            return None

        # round_number is bumped at the START of every call after the
        # first (it's already correctly 1 to begin with) - this keeps
        # state.round_number matching whichever round's log_line is in
        # the result that's about to be returned, since the caller reads
        # BOTH from the state object right after this call returns.
        if self._started:
            self.round_number += 1
        self._started = True

        alive_a = self._alive(self.team_a)
        alive_b = self._alive(self.team_b)
        if not alive_a or not alive_b:
            # Shouldn't normally happen (finished should already be set by
            # the previous call), but never crash the bot over it.
            self.finished = True
            return None

        events: list[str] = []
        pending_damage: dict[int, int] = {}

        for attacker in alive_a:
            target = random.choice(alive_b)
            pending_damage[id(target)] = pending_damage.get(id(target), 0) + attacker.attack
            events.append(f"{attacker.name} hits {target.name} for {attacker.attack}")
        for attacker in alive_b:
            target = random.choice(alive_a)
            pending_damage[id(target)] = pending_damage.get(id(target), 0) + attacker.attack
            events.append(f"{attacker.name} hits {target.name} for {attacker.attack}")

        for fighter in alive_a + alive_b:
            dmg = pending_damage.get(id(fighter))
            if dmg:
                fighter.take_damage(dmg)

        ko_events = [f"💀 {f.name} was knocked out!" for f in alive_a + alive_b if f.is_ko]

        # Keep the embed field readable - a 3v3 can have up to 6 hits a
        # round, which is already a lot of lines; trim further if needed.
        log_parts = events[:4]
        if len(events) > 4:
            log_parts.append(f"...and {len(events) - 4} more hit(s)")
        log_parts.extend(ko_events)
        result = RoundResult(round_number=self.round_number, log_line="\n".join(log_parts))

        a_wiped = not self._alive(self.team_a)
        b_wiped = not self._alive(self.team_b)

        if a_wiped and b_wiped:
            self.finished, self.winner_label = True, None
        elif a_wiped:
            self.finished, self.winner_label = True, self.label_b
        elif b_wiped:
            self.finished, self.winner_label = True, self.label_a
        elif self.round_number >= MAX_ROUNDS:
            # Safety net: force a decision by total remaining HP rather
            # than let a degenerate matchup (e.g. 0-attack fighters) loop
            # forever.
            hp_a = sum(f.current_hp for f in self.team_a)
            hp_b = sum(f.current_hp for f in self.team_b)
            self.finished = True
            if hp_a == hp_b:
                self.winner_label = None
            else:
                self.winner_label = self.label_a if hp_a > hp_b else self.label_b

        return result