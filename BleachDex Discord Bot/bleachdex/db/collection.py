"""
Ownership: who owns which character/weapon instances, and the equip
mechanic linking one owned weapon to one owned character (its
boost_type/boost_percent then applies as a % in battle).
"""

import time
from dataclasses import dataclass
from typing import Optional

from db.connection import get_connection
from db.characters import get_character
from db.weapons import get_weapon
from reiatsu import roll_reiatsu


@dataclass
class OwnedCharacter:
    id: int
    character_id: int
    owner_discord_id: int
    health: int
    attack: int
    equipped_weapon_instance_id: Optional[int]
    caught_at: int
    is_reiatsu: int = 0        # 1 = awakened Reiatsu copy (see reiatsu.py)


@dataclass
class OwnedWeapon:
    id: int
    weapon_id: int
    owner_discord_id: int
    attack_bonus: int          # deprecated - kept for old rows, no longer used
    caught_at: int
    boost_type: str = "damage"
    boost_percent: int = 0


def resync_owned_character_stats() -> int:
    """Re-stamp every owned_characters row's health/attack to match its
    character's CURRENT master hp/attack.

    grant_character() below only snapshots hp/attack into an owned
    instance once, at catch time - rebalancing a character in the
    characters table (e.g. via seed_roster.py) never touches copies
    people already own, since battle.py/boss.py read the instance's
    own health/attack, not the master row. Run this once after any
    stat rebalance to bring existing copies in line with the new
    numbers. Returns the number of instances updated.
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT oc.id, c.hp AS new_health, c.attack AS new_attack
               FROM owned_characters oc
               JOIN characters c ON c.id = oc.character_id
               WHERE oc.health != c.hp OR oc.attack != c.attack"""
        ).fetchall()
        for row in rows:
            conn.execute(
                "UPDATE owned_characters SET health = ?, attack = ? WHERE id = ?",
                (row["new_health"], row["new_attack"], row["id"]),
            )
        conn.commit()
        return len(rows)
    finally:
        conn.close()


def resync_owned_weapon_stats() -> int:
    """Re-stamp every owned_weapons row's boost_type/boost_percent to
    match its weapon's CURRENT master values.

    grant_weapon() below only snapshots boost_type/boost_percent into an
    owned instance once, at catch time - fixing/rebalancing a weapon's
    boost in the weapons table (e.g. via seed_roster.py) never touches
    copies people already own, since battle.py/boss.py read the
    instance's own boost_type/boost_percent, not the master row. Run
    this once after any weapon boost fix/rebalance to bring existing
    copies in line with the new numbers. Returns the number of
    instances updated.
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT ow.id, w.boost_type AS new_boost_type, w.boost_percent AS new_boost_percent
               FROM owned_weapons ow
               JOIN weapons w ON w.id = ow.weapon_id
               WHERE ow.boost_type != w.boost_type OR ow.boost_percent != w.boost_percent"""
        ).fetchall()
        for row in rows:
            conn.execute(
                "UPDATE owned_weapons SET boost_type = ?, boost_percent = ? WHERE id = ?",
                (row["new_boost_type"], row["new_boost_percent"], row["id"]),
            )
        conn.commit()
        return len(rows)
    finally:
        conn.close()


def grant_character(character_id: int, owner_discord_id: int, roll_reiatsu_chance: bool = True) -> int:
    """Adds one copy of a character to a player's collection and returns
    the new instance id.

    Every copy has a REIATSU_CHANCE (10%, see reiatsu.py) of being an
    awakened Reiatsu copy. Callers that want to show it just read
    get_owned_character_instance(<returned id>).is_reiatsu. Pass
    roll_reiatsu_chance=False for grants that aren't a catch/pull/craft
    (e.g. the merchant's exchange board) so those never roll for it.
    """
    character = get_character(character_id)
    if character is None:
        raise ValueError("Unknown character id")
    is_reiatsu = 1 if (roll_reiatsu_chance and roll_reiatsu()) else 0
    conn = get_connection()
    try:
        cur = conn.execute(
            """INSERT INTO owned_characters
               (character_id, owner_discord_id, health, attack, caught_at, is_reiatsu)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (character_id, owner_discord_id, character.hp, character.attack,
             int(time.time()), is_reiatsu),
        )
        conn.execute(
            "INSERT INTO catch_log (discord_id, kind, item_id, caught_at, is_reiatsu) "
            "VALUES (?, 'character', ?, ?, ?)",
            (owner_discord_id, character_id, int(time.time()), is_reiatsu),
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
               (weapon_id, owner_discord_id, attack_bonus, boost_type, boost_percent, caught_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (weapon_id, owner_discord_id, 0, weapon.boost_type, weapon.boost_percent,
             int(time.time())),
        )
        conn.execute(
            "INSERT INTO catch_log (discord_id, kind, item_id, caught_at) VALUES (?, 'weapon', ?, ?)",
            (owner_discord_id, weapon_id, int(time.time())),
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


def get_owned_character_ids_split(owner_discord_id: int) -> tuple[set[int], set[int]]:
    """(normal_ids, reiatsu_ids): which characters the player owns a plain
    copy of, and which they own a Reiatsu copy of. A character can be in
    both. Used by /collection completion, which lists the two separately."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT DISTINCT character_id, is_reiatsu FROM owned_characters WHERE owner_discord_id = ?",
            (owner_discord_id,),
        ).fetchall()
    finally:
        conn.close()
    normal = {r["character_id"] for r in rows if not r["is_reiatsu"]}
    reiatsu = {r["character_id"] for r in rows if r["is_reiatsu"]}
    return normal, reiatsu


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


def find_owned_characters_matching(owner_discord_id: int, query: str) -> list["OwnedCharacter"]:
    """Case-insensitive partial-name search across the player's WHOLE
    collection - not capped at 25 like a dropdown's option list. Used
    by /team add's character picker (a modal text box) so players can
    reach any owned character by typing part of its name, not just
    their 25 most recently caught. Returns one instance per distinct
    character name (the most recently caught copy of it, matching how
    /team add treats repeat catches elsewhere), ordered most-recent
    first."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT oc.* FROM owned_characters oc
               JOIN characters c ON c.id = oc.character_id
               WHERE oc.owner_discord_id = ? AND LOWER(c.name) LIKE LOWER(?)
               ORDER BY oc.is_reiatsu DESC, oc.caught_at DESC""",
            (owner_discord_id, f"%{query}%"),
        ).fetchall()
    finally:
        conn.close()

    seen_character_ids: set[int] = set()
    matches: list[OwnedCharacter] = []
    for row in rows:
        inst = OwnedCharacter(**dict(row))
        if inst.character_id in seen_character_ids:
            continue
        seen_character_ids.add(inst.character_id)
        matches.append(inst)
    return matches


def find_owned_character_instances_matching(owner_discord_id: int, query: str) -> list["OwnedCharacter"]:
    """Like find_owned_characters_matching, but NOT deduped - returns every
    owned copy whose character name contains `query` (case-insensitive),
    most recently caught first.

    /team add needs this: the deduped version only ever hands back the
    newest copy of each character, so a player who owns exactly one Soul
    King and one who owns three both got the same single instance back -
    which is how one Soul King ended up filling all 3 team slots. Callers
    use this list to pick a copy that isn't already in the team, and to
    tell the player when they've run out of copies."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT oc.* FROM owned_characters oc
               JOIN characters c ON c.id = oc.character_id
               WHERE oc.owner_discord_id = ? AND LOWER(c.name) LIKE LOWER(?)
               ORDER BY oc.is_reiatsu DESC, oc.caught_at DESC, oc.id DESC""",
            (owner_discord_id, f"%{query}%"),
        ).fetchall()
    finally:
        conn.close()
    return [OwnedCharacter(**dict(r)) for r in rows]


def find_owned_weapons_matching(owner_discord_id: int, query: str) -> list["OwnedWeapon"]:
    """Same idea as find_owned_characters_matching, but for weapons -
    case-insensitive partial-name search across the player's whole
    weapon collection, deduped to one instance per distinct weapon
    name (the most recently caught copy), most-recent first."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT ow.* FROM owned_weapons ow
               JOIN weapons w ON w.id = ow.weapon_id
               WHERE ow.owner_discord_id = ? AND LOWER(w.name) LIKE LOWER(?)
               ORDER BY ow.caught_at DESC""",
            (owner_discord_id, f"%{query}%"),
        ).fetchall()
    finally:
        conn.close()

    seen_weapon_ids: set[int] = set()
    matches: list[OwnedWeapon] = []
    for row in rows:
        inst = OwnedWeapon(**dict(row))
        if inst.weapon_id in seen_weapon_ids:
            continue
        seen_weapon_ids.add(inst.weapon_id)
        matches.append(inst)
    return matches


def find_owned_weapon_instances_matching(owner_discord_id: int, query: str) -> list["OwnedWeapon"]:
    """Weapon twin of find_owned_character_instances_matching - every
    owned copy whose weapon name contains `query`, newest first, NOT
    deduped."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT ow.* FROM owned_weapons ow
               JOIN weapons w ON w.id = ow.weapon_id
               WHERE ow.owner_discord_id = ? AND LOWER(w.name) LIKE LOWER(?)
               ORDER BY ow.caught_at DESC, ow.id DESC""",
            (owner_discord_id, f"%{query}%"),
        ).fetchall()
    finally:
        conn.close()
    return [OwnedWeapon(**dict(r)) for r in rows]


def get_equipped_weapon_map(owner_discord_id: int) -> dict[int, int]:
    """{weapon_instance_id: character_instance_id} for every weapon this
    player currently has equipped on one of their characters."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT id, equipped_weapon_instance_id FROM owned_characters
               WHERE owner_discord_id = ? AND equipped_weapon_instance_id IS NOT NULL""",
            (owner_discord_id,),
        ).fetchall()
    finally:
        conn.close()
    return {r["equipped_weapon_instance_id"]: r["id"] for r in rows}


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


def find_owned_character_by_name(
    owner_discord_id: int, name: str, spare_first: bool = False
) -> Optional[OwnedCharacter]:
    """Finds one of the player's copies of a character by exact name.

    Default: their BEST copy - a Reiatsu copy if they have one, otherwise
    the most recently caught. That's what /equip and /card view want.

    spare_first=True flips it for anything that gives a copy away (/give,
    /trade): a non-Reiatsu copy goes first, so a name-based give/trade
    never hands over the awakened copy while a plain one is sitting there.
    """
    reiatsu_order = "ASC" if spare_first else "DESC"
    conn = get_connection()
    try:
        row = conn.execute(
            f"""SELECT oc.* FROM owned_characters oc
               JOIN characters c ON c.id = oc.character_id
               WHERE oc.owner_discord_id = ? AND LOWER(c.name) = LOWER(?)
               ORDER BY oc.is_reiatsu {reiatsu_order}, oc.caught_at DESC LIMIT 1""",
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
        # One physical weapon can only be held by one character - equipping
        # it here takes it off whoever else had it. Without this, a single
        # weapon could be equipped on every character at once and its boost
        # counted once per holder.
        conn.execute(
            "UPDATE owned_characters SET equipped_weapon_instance_id = NULL "
            "WHERE equipped_weapon_instance_id = ? AND id != ?",
            (weapon_instance_id, character_instance_id),
        )
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