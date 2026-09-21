"""
Reiatsu - a rare "awakened" variant of any character you own.

Every time a character is added to a player's collection (wild catch,
/pack daily, /pack weekly, /shop pack, /craft) there's a REIATSU_CHANCE
(10%) that the copy they get is a Reiatsu copy - shown as e.g.
"Ichigo Kurosaki (Reiatsu)".

A Reiatsu copy is the SAME character (same name for catching/crafting,
same collection entry, same team/equip/trade behaviour) - it's just a
different physical copy that:
  * fights with +20% damage and +10% HP (applied in battle on top of any
    equipped-weapon boost - see cogs/battle.py), and
  * renders with a different card (spirit-energy aura, cyan title,
    REIATSU badge, boosted stats) - see cards/render.py.

The base health/attack stored on the owned copy are NOT changed -
db/collection.py's resync_owned_character_stats() keeps working as
before, and the boost is applied at battle/display time using the
helpers below, so retuning the multipliers here takes effect for every
existing Reiatsu copy immediately.
"""

import random

REIATSU_CHANCE = 0.10        # 10% per character added to a collection
REIATSU_DAMAGE_MULT = 1.20   # +20% damage
REIATSU_HP_MULT = 1.10       # +10% HP

REIATSU_EMOJI = "⚡"
REIATSU_SUFFIX = "(Reiatsu)"
REIATSU_PERK_TEXT = "+20% damage, +10% HP"


def roll_reiatsu() -> bool:
    """True with probability REIATSU_CHANCE."""
    return random.random() < REIATSU_CHANCE


def reiatsu_name(name: str) -> str:
    """'Ichigo Kurosaki' -> 'Ichigo Kurosaki (Reiatsu)'."""
    return f"{name} {REIATSU_SUFFIX}"


def display_name(name: str, is_reiatsu: bool) -> str:
    return reiatsu_name(name) if is_reiatsu else name


def boosted_hp(hp: int) -> int:
    return round(hp * REIATSU_HP_MULT)


def boosted_attack(attack: int) -> int:
    return round(attack * REIATSU_DAMAGE_MULT)