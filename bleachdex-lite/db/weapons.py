"""
Weapons: Zanpakuto and other equippable items. Kept in a separate
table from characters on purpose (per your instruction to split
"weapon = zanpakuto" from "character = everything else").

A weapon can be equipped onto an owned character instance to add its
attack_bonus during battle - see db/collection.py.
"""

import random
import time
from dataclasses import dataclass
from typing import Optional

from db.connection import get_connection, TIERS, TIER_WEIGHTS


@dataclass
class Weapon:
    id: int
    name: str
    position: str
    image_path: str
    attack_bonus: int
    tier: str
    rarity: int
    emoji: str
    card_template_path: str
    enabled: bool
    created_at: int = 0
    ability_name: str = ""
    ability_description: str = ""
    card_image_path: str = ""

    @classmethod
    def from_row(cls, row) -> "Weapon":
        data = dict(row)
        data["enabled"] = bool(data["enabled"])
        data.setdefault("card_template_path", "")
        data.setdefault("ability_name", "")
        data.setdefault("ability_description", "")
        data.setdefault("card_image_path", "")
        return cls(**data)


def add_weapon(
    name: str,
    image_path: str,
    attack_bonus: int = 1,
    tier: str = "common",
    rarity: int = 100,
    emoji: str = "",
    position: str = "",
    ability_name: str = "",
    ability_description: str = "",
) -> int:
    if tier not in TIERS:
        raise ValueError(f"tier must be one of {TIERS}")
    conn = get_connection()
    try:
        cur = conn.execute(
            """INSERT INTO weapons
               (name, position, image_path, attack_bonus, tier, rarity,
                emoji, ability_name, ability_description, enabled, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)""",
            (name, position, image_path, attack_bonus, tier, rarity,
             emoji, ability_name, ability_description, int(time.time())),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def list_weapons(enabled_only: bool = True) -> list[Weapon]:
    conn = get_connection()
    try:
        query = "SELECT * FROM weapons"
        if enabled_only:
            query += " WHERE enabled = 1"
        query += " ORDER BY name"
        rows = conn.execute(query).fetchall()
        return [Weapon.from_row(r) for r in rows]
    finally:
        conn.close()


def get_weapon(weapon_id: int) -> Optional[Weapon]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM weapons WHERE id = ?", (weapon_id,)).fetchone()
        return Weapon.from_row(row) if row else None
    finally:
        conn.close()


def find_weapon_by_name(name: str, enabled_only: bool = True) -> Optional[Weapon]:
    conn = get_connection()
    try:
        query = "SELECT * FROM weapons WHERE LOWER(name) = LOWER(?)"
        if enabled_only:
            query += " AND enabled = 1"
        row = conn.execute(query, (name,)).fetchone()
        return Weapon.from_row(row) if row else None
    finally:
        conn.close()


def update_weapon_image(weapon_id: int, new_image_path: str) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE weapons SET image_path = ? WHERE id = ?",
            (new_image_path, weapon_id),
        )
        conn.commit()
    finally:
        conn.close()


def update_weapon_card(
    weapon_id: int,
    attack_bonus: Optional[int] = None,
    card_template_path: Optional[str] = None,
    card_image_path: Optional[str] = None,
    ability_name: Optional[str] = None,
    ability_description: Optional[str] = None,
) -> None:
    """Used by /edit card weapon to fill in (or update) a weapon's actual
    CARD: its attack bonus, its per-card background template, its
    ability text, and optionally replacement art FOR THE CARD ONLY.

    Deliberately never touches `image_path` - see the matching note on
    update_character_card in db/characters.py for why."""
    fields, params = [], []
    if attack_bonus is not None:
        fields.append("attack_bonus = ?")
        params.append(attack_bonus)
    if card_template_path is not None:
        fields.append("card_template_path = ?")
        params.append(card_template_path)
    if card_image_path is not None:
        fields.append("card_image_path = ?")
        params.append(card_image_path)
    if ability_name is not None:
        fields.append("ability_name = ?")
        params.append(ability_name)
    if ability_description is not None:
        fields.append("ability_description = ?")
        params.append(ability_description)
    if not fields:
        return
    params.append(weapon_id)
    conn = get_connection()
    try:
        conn.execute(f"UPDATE weapons SET {', '.join(fields)} WHERE id = ?", params)
        conn.commit()
    finally:
        conn.close()


def delete_weapon(weapon_id: int) -> None:
    conn = get_connection()
    try:
        conn.execute("UPDATE weapons SET enabled = 0 WHERE id = ?", (weapon_id,))
        conn.commit()
    finally:
        conn.close()


def pick_random_weapon() -> Optional[Weapon]:
    weapons = list_weapons(enabled_only=True)
    if not weapons:
        return None
    by_tier: dict[str, list[Weapon]] = {}
    for w in weapons:
        by_tier.setdefault(w.tier, []).append(w)
    available_tiers = list(by_tier.keys())
    weights = [TIER_WEIGHTS.get(t, 1) for t in available_tiers]
    chosen_tier = random.choices(available_tiers, weights=weights, k=1)[0]
    return random.choice(by_tier[chosen_tier])