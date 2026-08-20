"""
Saved teams: each player can register exactly 3 owned character
instances (slots 1-3) via /team add. /battle then pits the challenger's
team against the opponent's team, 3v3, instead of picking one fighter
per battle.

Equipped weapons still come from the existing /equip mechanic (see
db/collection.py) - a team slot just points at an owned_characters.id,
and whatever weapon is equipped on that instance applies automatically
in battle.
"""

from dataclasses import dataclass
from typing import Optional

from db.connection import get_connection
from db.collection import get_owned_character_instance, OwnedCharacter


def set_team_slot(owner_discord_id: int, slot: int, character_instance_id: int) -> None:
    if slot not in (1, 2, 3):
        raise ValueError("slot must be 1, 2, or 3")
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO teams (owner_discord_id, slot, character_instance_id)
               VALUES (?, ?, ?)
               ON CONFLICT(owner_discord_id, slot)
               DO UPDATE SET character_instance_id = excluded.character_instance_id""",
            (owner_discord_id, slot, character_instance_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_team(owner_discord_id: int) -> Optional[list[OwnedCharacter]]:
    """
    Returns the player's 3 team members in slot order (1, 2, 3), or None
    if they haven't filled all 3 slots yet. If a slot points at a
    character instance that no longer exists (e.g. traded away), that
    slot is treated as unset too.
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT slot, character_instance_id FROM teams "
            "WHERE owner_discord_id = ? ORDER BY slot",
            (owner_discord_id,),
        ).fetchall()
    finally:
        conn.close()

    if len(rows) != 3:
        return None

    members = []
    for row in rows:
        inst = get_owned_character_instance(row["character_instance_id"])
        if inst is None or inst.owner_discord_id != owner_discord_id:
            return None
        members.append(inst)
    return members


def clear_team(owner_discord_id: int) -> None:
    conn = get_connection()
    try:
        conn.execute("DELETE FROM teams WHERE owner_discord_id = ?", (owner_discord_id,))
        conn.commit()
    finally:
        conn.close()
