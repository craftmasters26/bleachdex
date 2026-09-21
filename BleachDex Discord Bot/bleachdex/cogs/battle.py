"""
Shared battle-stat helpers.

_effective_attack() / _effective_hp() compute an owned character's
attack/health after applying its equipped weapon's boost (see
db/weapons.py - boost_type is 'damage' or 'hp', boost_percent is
applied multiplicatively, e.g. +40% -> x1.40 to that one stat only).

This module is intentionally NOT a cog (no setup()/Cog class here) and
is not in bot.py's EXTENSIONS list - it used to duplicate the entire
boss-battle Cog that lives in cogs/boss.py, which made the bot crash
on startup with CommandAlreadyRegistered ('bossbattle' registered
twice). cogs/boss.py is the sole owner of that cog and imports these
two helpers from here (lazily, inside its Challenge handler, so the
two modules never have to fight over which one finishes initializing
first at bot startup).

Note: there's currently no PvP /battle command anywhere in the
codebase - logic/battle.py's TeamBattleState/Fighter classes (a 3v3
simultaneous team-battle simulator) exist but aren't wired up to any
cog yet. If you want a real /battle command, that's a separate feature
to build, not part of this crash fix.
"""

from db import collection as coll


def _effective_attack(inst) -> int:
    """An owned character's attack, after applying its equipped weapon's
    boost if that weapon boosts 'damage' (see db/weapons.py - boost_type/
    boost_percent is applied multiplicatively, e.g. +40% -> x1.40)."""
    attack = inst.attack
    if inst.equipped_weapon_instance_id is not None:
        weapon = coll.get_owned_weapon_instance(inst.equipped_weapon_instance_id)
        if weapon is not None and weapon.boost_type == "damage":
            attack = round(attack * (1 + weapon.boost_percent / 100))
    return attack


def _effective_hp(inst) -> int:
    """An owned character's health, after applying its equipped weapon's
    boost if that weapon boosts 'hp' (see _effective_attack above)."""
    health = inst.health
    if inst.equipped_weapon_instance_id is not None:
        weapon = coll.get_owned_weapon_instance(inst.equipped_weapon_instance_id)
        if weapon is not None and weapon.boost_type == "hp":
            health = round(health * (1 + weapon.boost_percent / 100))
    return health