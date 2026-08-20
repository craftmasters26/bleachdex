"""
Characters: the roster of pullable Bleach characters (everything that
isn't a weapon/zanpakuto - see weapons.py for those).
"""

import random
import time
from dataclasses import dataclass
from typing import Optional

from db.connection import get_connection, TIERS, TIER_WEIGHTS


@dataclass
class Character:
    id: int
    name: str
    position: str
    image_path: str
    hp: int
    attack: int
    tier: str
    rarity: int
    ability_name: str
    ability_description: str
    emoji: str
    card_template_path: str
    card_image_path: str
    enabled: bool
    created_at: int = 0

    @classmethod
    def from_row(cls, row) -> "Character":
        data = dict(row)
        data["enabled"] = bool(data["enabled"])
        data.setdefault("card_template_path", "")
        data.setdefault("card_image_path", "")
        return cls(**data)


def add_character(
    name: str,
    image_path: str,
    hp: int = 1,
    attack: int = 1,
    tier: str = "common",
    rarity: int = 100,
    ability_name: str = "",
    ability_description: str = "",
    emoji: str = "",
    position: str = "",
) -> int:
    if tier not in TIERS:
        raise ValueError(f"tier must be one of {TIERS}")
    conn = get_connection()
    try:
        cur = conn.execute(
            """INSERT INTO characters
               (name, position, image_path, hp, attack, tier, rarity,
                ability_name, ability_description, emoji, enabled, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)""",
            (name, position, image_path, hp, attack, tier, rarity,
             ability_name, ability_description, emoji, int(time.time())),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def list_characters(enabled_only: bool = True, min_tier: Optional[str] = None) -> list[Character]:
    conn = get_connection()
    try:
        query = "SELECT * FROM characters WHERE 1=1"
        params: list = []
        if enabled_only:
            query += " AND enabled = 1"
        if min_tier:
            allowed = TIERS[TIERS.index(min_tier):]
            placeholders = ",".join("?" for _ in allowed)
            query += f" AND tier IN ({placeholders})"
            params.extend(allowed)
        query += " ORDER BY name"
        rows = conn.execute(query, params).fetchall()
        return [Character.from_row(r) for r in rows]
    finally:
        conn.close()


def get_character(character_id: int) -> Optional[Character]:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM characters WHERE id = ?", (character_id,)
        ).fetchone()
        return Character.from_row(row) if row else None
    finally:
        conn.close()


def find_character_by_name(name: str, enabled_only: bool = True) -> Optional[Character]:
    conn = get_connection()
    try:
        query = "SELECT * FROM characters WHERE LOWER(name) = LOWER(?)"
        if enabled_only:
            query += " AND enabled = 1"
        row = conn.execute(query, (name,)).fetchone()
        return Character.from_row(row) if row else None
    finally:
        conn.close()


def update_character_image(character_id: int, new_image_path: str) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE characters SET image_path = ? WHERE id = ?",
            (new_image_path, character_id),
        )
        conn.commit()
    finally:
        conn.close()


def update_character_emoji(character_id: int, emoji_id: str) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE characters SET emoji = ? WHERE id = ?",
            (emoji_id, character_id),
        )
        conn.commit()
    finally:
        conn.close()


def update_character_card(
    character_id: int,
    hp: Optional[int] = None,
    attack: Optional[int] = None,
    card_template_path: Optional[str] = None,
    card_image_path: Optional[str] = None,
    ability_name: Optional[str] = None,
    ability_description: Optional[str] = None,
) -> None:
    """Used by /edit card character to fill in (or update) a character's
    actual CARD: its stats, its per-card background template, its
    ability text, and optionally replacement art FOR THE CARD ONLY.

    Deliberately never touches `image_path` - that's the plain image
    used when this character spawns in the wild, and it's only ever
    set by /character add or /change character. card_image_path is a
    separate field: when set, /pack daily reveals and /card view use
    it instead of image_path; if it's never set, they fall back to
    image_path automatically (see cards/render.py callers)."""
    fields, params = [], []
    if hp is not None:
        fields.append("hp = ?")
        params.append(hp)
    if attack is not None:
        fields.append("attack = ?")
        params.append(attack)
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
    params.append(character_id)
    conn = get_connection()
    try:
        conn.execute(f"UPDATE characters SET {', '.join(fields)} WHERE id = ?", params)
        conn.commit()
    finally:
        conn.close()


def delete_character(character_id: int) -> None:
    conn = get_connection()
    try:
        conn.execute("UPDATE characters SET enabled = 0 WHERE id = ?", (character_id,))
        conn.commit()
    finally:
        conn.close()


def pick_random_character(min_tier: Optional[str] = None) -> Optional[Character]:
    """
    Two-stage weighted pick: first pick a tier (mythic much rarer than
    common), then pick uniformly among enabled characters in that tier.
    Falls back to any available tier if the chosen one has no characters.
    """
    chars = list_characters(enabled_only=True, min_tier=min_tier)
    if not chars:
        return None

    by_tier: dict[str, list[Character]] = {}
    for c in chars:
        by_tier.setdefault(c.tier, []).append(c)

    available_tiers = list(by_tier.keys())
    weights = [TIER_WEIGHTS.get(t, 1) for t in available_tiers]
    chosen_tier = random.choices(available_tiers, weights=weights, k=1)[0]
    return random.choice(by_tier[chosen_tier])