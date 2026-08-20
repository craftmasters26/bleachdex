"""
Ownership: who owns which character/weapon instances, and the equip
mechanic linking one owned weapon to one owned character (its
attack_bonus then applies in battle).
"""

import time
from dataclasses import dataclass
from typing import Optional

from db.connection import get_connection
from db.characters import get_character
from db.weapons import get_weapon


@dataclass
class OwnedCharacter:
    id: int
    character_id: int
    owner_discord_id: int
    health: int
    attack: int
    equipped_weapon_instance_id: Optional[int]
    caught_at: int


@dataclass
class OwnedWeapon:
    id: int
    weapon_id: int
    owner_discord_id: int
    attack_bonus: int
    caught_at: int


def grant_character(character_id: int, owner_discord_id: int) -> int:
    character = get_character(character_id)
    if character is None:
        raise ValueError("Unknown character id")
    conn = get_connection()
    try:
        cur = conn.execute(
            """INSERT INTO owned_characters
               (character_id, owner_discord_id, health, attack, caught_at)
               VALUES (?, ?, ?, ?, ?)""",
            (character_id, owner_discord_id, character.hp, character.attack,
             int(time.time())),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def grant_weapon(weapon_id: int, owner_discord_id: int) -> int:
    weapon = get_weapon(weapon_id)
    if weapon is None:
        raise ValueError("Unknown weapon id")
    conn = get_connection()
    try:
        cur = conn.execute(
            """INSERT INTO owned_weapons
               (weapon_id, owner_discord_id, attack_bonus, caught_at)
               VALUES (?, ?, ?, ?)""",
            (weapon_id, owner_discord_id, weapon.attack_bonus, int(time.time())),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_owned_character_ids(owner_discord_id: int) -> set[int]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT DISTINCT character_id FROM owned_characters WHERE owner_discord_id = ?",
            (owner_discord_id,),
        ).fetchall()
        return {r["character_id"] for r in rows}
    finally:
        conn.close()


def get_owned_weapon_ids(owner_discord_id: int) -> set[int]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT DISTINCT weapon_id FROM owned_weapons WHERE owner_discord_id = ?",
            (owner_discord_id,),
        ).fetchall()
        return {r["weapon_id"] for r in rows}
    finally:
        conn.close()


def list_owned_characters(owner_discord_id: int) -> list[OwnedCharacter]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM owned_characters WHERE owner_discord_id = ? ORDER BY caught_at DESC",
            (owner_discord_id,),
        ).fetchall()
        return [OwnedCharacter(**dict(r)) for r in rows]
    finally:
        conn.close()


def list_owned_weapons(owner_discord_id: int) -> list[OwnedWeapon]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM owned_weapons WHERE owner_discord_id = ? ORDER BY caught_at DESC",
            (owner_discord_id,),
        ).fetchall()
        return [OwnedWeapon(**dict(r)) for r in rows]
    finally:
        conn.close()


def get_owned_character_instance(instance_id: int) -> Optional[OwnedCharacter]:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM owned_characters WHERE id = ?", (instance_id,)
        ).fetchone()
        return OwnedCharacter(**dict(row)) if row else None
    finally:
        conn.close()


def get_owned_weapon_instance(instance_id: int) -> Optional[OwnedWeapon]:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM owned_weapons WHERE id = ?", (instance_id,)
        ).fetchone()
        return OwnedWeapon(**dict(row)) if row else None
    finally:
        conn.close()


def find_owned_character_by_name(owner_discord_id: int, name: str) -> Optional[OwnedCharacter]:
    """Finds the player's most recently caught instance of a character by name."""
    conn = get_connection()
    try:
        row = conn.execute(
            """SELECT oc.* FROM owned_characters oc
               JOIN characters c ON c.id = oc.character_id
               WHERE oc.owner_discord_id = ? AND LOWER(c.name) = LOWER(?)
               ORDER BY oc.caught_at DESC LIMIT 1""",
            (owner_discord_id, name),
        ).fetchone()
        return OwnedCharacter(**dict(row)) if row else None
    finally:
        conn.close()


def find_owned_weapon_by_name(owner_discord_id: int, name: str) -> Optional[OwnedWeapon]:
    conn = get_connection()
    try:
        row = conn.execute(
            """SELECT ow.* FROM owned_weapons ow
               JOIN weapons w ON w.id = ow.weapon_id
               WHERE ow.owner_discord_id = ? AND LOWER(w.name) = LOWER(?)
               ORDER BY ow.caught_at DESC LIMIT 1""",
            (owner_discord_id, name),
        ).fetchone()
        return OwnedWeapon(**dict(row)) if row else None
    finally:
        conn.close()


def equip_weapon(character_instance_id: int, weapon_instance_id: int, owner_discord_id: int) -> None:
    char = get_owned_character_instance(character_instance_id)
    weapon = get_owned_weapon_instance(weapon_instance_id)
    if char is None or char.owner_discord_id != owner_discord_id:
        raise ValueError("You don't own that character.")
    if weapon is None or weapon.owner_discord_id != owner_discord_id:
        raise ValueError("You don't own that weapon.")

    conn = get_connection()
    try:
        conn.execute(
            "UPDATE owned_characters SET equipped_weapon_instance_id = ? WHERE id = ?",
            (weapon_instance_id, character_instance_id),
        )
        conn.commit()
    finally:
        conn.close()


def unequip_weapon(character_instance_id: int, owner_discord_id: int) -> None:
    char = get_owned_character_instance(character_instance_id)
    if char is None or char.owner_discord_id != owner_discord_id:
        raise ValueError("You don't own that character.")
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE owned_characters SET equipped_weapon_instance_id = NULL WHERE id = ?",
            (character_instance_id,),
        )
        conn.commit()
    finally:
        conn.close()


def transfer_character(instance_id: int, new_owner_discord_id: int) -> None:
    conn = get_connection()
    try:
        # Trading unequips first - the weapon stays with its original owner.
        conn.execute(
            "UPDATE owned_characters SET equipped_weapon_instance_id = NULL WHERE id = ?",
            (instance_id,),
        )
        conn.execute(
            "UPDATE owned_characters SET owner_discord_id = ? WHERE id = ?",
            (new_owner_discord_id, instance_id),
        )
        conn.commit()
    finally:
        conn.close()


def transfer_weapon(instance_id: int, new_owner_discord_id: int) -> None:
    conn = get_connection()
    try:
        # If this weapon was equipped on one of the old owner's characters,
        # unequip it there first so ownership stays consistent.
        conn.execute(
            "UPDATE owned_characters SET equipped_weapon_instance_id = NULL "
            "WHERE equipped_weapon_instance_id = ?",
            (instance_id,),
        )
        conn.execute(
            "UPDATE owned_weapons SET owner_discord_id = ? WHERE id = ?",
            (new_owner_discord_id, instance_id),
        )
        conn.commit()
    finally:
        conn.close()
