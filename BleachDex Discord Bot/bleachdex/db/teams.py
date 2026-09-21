"""
Saved teams: each player can keep up to 2 separate "presets" (numbered
1-2), each holding its own full 3-character team (its own slots 1-3) -
so, for example, you can keep a boss-battle team in preset 1 and a
totally different PvP team in preset 2, and switch between them with
/team use instead of having to /team add from scratch every time.

/battle and /admin bossbattle's Challenge button both read whichever
preset is currently "active" for that player (get_team() with no
explicit preset argument) - see team_active_preset in db/connection.py.

Equipped weapons still come from the existing /equip mechanic (see
db/collection.py) - a team slot just points at an owned_characters.id,
and whatever weapon is equipped on that instance applies automatically
in battle, same as before.

Backward compatible on purpose: get_team(user_id) and
set_team_slot(user_id, slot, instance_id) still work with no preset
argument at all - they just operate on that user's active preset
(preset 1 by default), exactly like the old single-team version of
this file did.

Note: the underlying team_presets table's CHECK constraint still
allows a preset value of 3 (from before presets were capped at 2) -
SQLite can't cheaply narrow a CHECK constraint on an existing table,
so instead VALID_PRESETS below is what actually enforces the 2-slot
limit; nothing in the app will ever read or write preset 3.
"""

from dataclasses import dataclass
from typing import Optional

from db.connection import get_connection, get_setting, set_setting
from db.collection import get_owned_character_instance, OwnedCharacter

DEFAULT_PRESET = 1
VALID_PRESETS = (1, 2)


def _migrate_legacy_teams_once() -> None:
    """One-time copy of any rows still sitting in the old single-preset
    `teams` table into team_presets under preset 1, so upgrading to
    multi-preset teams doesn't silently wipe out someone's existing
    /team add. Safe to call on every startup - it no-ops (via the
    bot_settings flag) after the first successful run."""
    try:
        if get_setting("team_presets_migrated") == "1":
            return
        conn = get_connection()
        try:
            legacy_rows = conn.execute(
                "SELECT owner_discord_id, slot, character_instance_id FROM teams"
            ).fetchall()
            for row in legacy_rows:
                conn.execute(
                    """INSERT INTO team_presets (owner_discord_id, preset, slot, character_instance_id)
                       VALUES (?, 1, ?, ?)
                       ON CONFLICT(owner_discord_id, preset, slot) DO NOTHING""",
                    (row["owner_discord_id"], row["slot"], row["character_instance_id"]),
                )
            conn.commit()
        finally:
            conn.close()
        set_setting("team_presets_migrated", "1")
    except Exception:
        # Best-effort - if the DB/tables aren't ready yet (e.g. this file
        # got imported before init_db() ran), just skip for now; it'll
        # try again next time this module is (re)imported.
        pass


def get_active_preset(owner_discord_id: int) -> int:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT preset FROM team_active_preset WHERE owner_discord_id = ?",
            (owner_discord_id,),
        ).fetchone()
        return row["preset"] if row else DEFAULT_PRESET
    finally:
        conn.close()


def set_active_preset(owner_discord_id: int, preset: int) -> None:
    if preset not in VALID_PRESETS:
        raise ValueError("preset must be 1 or 2")
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO team_active_preset (owner_discord_id, preset) VALUES (?, ?)
               ON CONFLICT(owner_discord_id) DO UPDATE SET preset = excluded.preset""",
            (owner_discord_id, preset),
        )
        conn.commit()
    finally:
        conn.close()


def set_team_slot(
    owner_discord_id: int,
    slot: int,
    character_instance_id: int,
    preset: Optional[int] = None,
) -> None:
    if slot not in (1, 2, 3):
        raise ValueError("slot must be 1, 2, or 3")
    if preset is None:
        preset = get_active_preset(owner_discord_id)
    if preset not in VALID_PRESETS:
        raise ValueError("preset must be 1 or 2")
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO team_presets (owner_discord_id, preset, slot, character_instance_id)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(owner_discord_id, preset, slot)
               DO UPDATE SET character_instance_id = excluded.character_instance_id""",
            (owner_discord_id, preset, slot, character_instance_id),
        )
        conn.commit()
    finally:
        conn.close()


def set_team(owner_discord_id: int, preset: int, character_instance_ids: list[int]) -> None:
    """Saves all 3 slots of a preset at once, after checking that:
      - exactly 3 instance ids were given,
      - all 3 are DIFFERENT owned copies (the same instance can't fill
        more than one slot - owning one Soul King gets you one Soul King
        slot, owning three gets you three), and
      - every one of them currently belongs to this player.
    Raises ValueError with a player-readable message otherwise. Writes
    happen in a single transaction, so a preset is never left half-saved."""
    if preset not in VALID_PRESETS:
        raise ValueError("preset must be 1 or 2")
    if len(character_instance_ids) != 3:
        raise ValueError("A team needs exactly 3 characters.")
    if len(set(character_instance_ids)) != 3:
        raise ValueError("The same character copy can't be in more than one slot.")
    for instance_id in character_instance_ids:
        inst = get_owned_character_instance(instance_id)
        if inst is None or inst.owner_discord_id != owner_discord_id:
            raise ValueError("One of those characters isn't in your collection anymore.")

    conn = get_connection()
    try:
        for slot, instance_id in enumerate(character_instance_ids, start=1):
            conn.execute(
                """INSERT INTO team_presets (owner_discord_id, preset, slot, character_instance_id)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(owner_discord_id, preset, slot)
                   DO UPDATE SET character_instance_id = excluded.character_instance_id""",
                (owner_discord_id, preset, slot, instance_id),
            )
        conn.commit()
    finally:
        conn.close()


def get_team(owner_discord_id: int, preset: Optional[int] = None) -> Optional[list[OwnedCharacter]]:
    """
    Returns the player's 3 team members in slot order (1, 2, 3) for the
    given preset, or None if that preset hasn't got all 3 slots filled
    yet. If preset is omitted, uses whichever preset is currently
    "active" for that player (see get_active_preset()/set_active_preset()).
    If a slot points at a character instance that no longer exists
    (e.g. traded away), or the same instance fills more than one slot,
    that preset is treated as unset too.
    """
    if preset is None:
        preset = get_active_preset(owner_discord_id)

    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT slot, character_instance_id FROM team_presets "
            "WHERE owner_discord_id = ? AND preset = ? ORDER BY slot",
            (owner_discord_id, preset),
        ).fetchall()
    finally:
        conn.close()

    if len(rows) != 3:
        return None

    # The same owned copy in more than one slot is never a valid team -
    # this also invalidates teams saved before that was enforced (the
    # player just re-runs /team add), instead of letting them keep
    # fighting with one card counted 2-3 times.
    if len({row["character_instance_id"] for row in rows}) != 3:
        return None

    members = []
    for row in rows:
        inst = get_owned_character_instance(row["character_instance_id"])
        if inst is None or inst.owner_discord_id != owner_discord_id:
            return None
        members.append(inst)
    return members


def list_presets(owner_discord_id: int) -> dict[int, Optional[list[OwnedCharacter]]]:
    """{1: team_or_None, 2: team_or_None, 3: team_or_None} - one entry
    per preset slot, regardless of which (if any) is currently active."""
    return {p: get_team(owner_discord_id, preset=p) for p in VALID_PRESETS}


def clear_team(owner_discord_id: int, preset: Optional[int] = None) -> None:
    """Clears one preset (the active one if not specified). To wipe
    every preset for this player, call this once per preset number."""
    if preset is None:
        preset = get_active_preset(owner_discord_id)
    conn = get_connection()
    try:
        conn.execute(
            "DELETE FROM team_presets WHERE owner_discord_id = ? AND preset = ?",
            (owner_discord_id, preset),
        )
        conn.commit()
    finally:
        conn.close()


_migrate_legacy_teams_once()