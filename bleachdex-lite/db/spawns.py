"""
The spawn engine's data layer.

How it fits together (mirrors BallsDex's countryballs spawn mechanic,
adapted to a single SQLite file instead of Postgres):

1. Admin runs /set spawn #channel — stored in guild_settings.
2. Every message sent in that channel flips channel_has_activity to 1
   (see cogs/spawn.py's on_message listener).
3. A background loop checks each configured guild on a random 5-10
   minute interval. If channel_has_activity is 1, it spawns a random
   character/weapon there and resets the flag to 0 (so a quiet channel
   never spawns things nobody's around to catch).
4. The spawn is recorded in active_spawns with caught_by = NULL.
   Catching is a race - whoever's /catch guess lands first while
   caught_by is still NULL wins. resolve_catch() uses an atomic
   UPDATE ... WHERE caught_by IS NULL so two simultaneous correct
   guesses can't both "win".
"""

import random
import time
from dataclasses import dataclass
from typing import Optional

from db.connection import get_connection

# Once a spawn goes out, only this many seconds to catch it - after
# that, resolve_catch() below refuses even a correct guess.
CATCH_WINDOW_SECONDS = 5 * 60


# ---------- Guild spawn config ----------

def set_spawn_channel(guild_id: int, channel_id: int) -> None:
    conn = get_connection()
    try:
        due = int(time.time()) + next_spawn_delay_seconds()
        conn.execute(
            """INSERT INTO guild_settings (guild_id, spawn_channel_id, channel_has_activity, last_spawn_at, next_check_at)
               VALUES (?, ?, 0, 0, ?)
               ON CONFLICT(guild_id) DO UPDATE SET spawn_channel_id = excluded.spawn_channel_id""",
            (guild_id, channel_id, due),
        )
        conn.commit()
    finally:
        conn.close()


def get_spawn_channel(guild_id: int) -> Optional[int]:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT spawn_channel_id FROM guild_settings WHERE guild_id = ?", (guild_id,)
        ).fetchone()
        return row["spawn_channel_id"] if row else None
    finally:
        conn.close()


def list_configured_guilds() -> list[int]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT guild_id FROM guild_settings WHERE spawn_channel_id IS NOT NULL"
        ).fetchall()
        return [r["guild_id"] for r in rows]
    finally:
        conn.close()


def mark_channel_active(guild_id: int) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE guild_settings SET channel_has_activity = 1 WHERE guild_id = ?",
            (guild_id,),
        )
        conn.commit()
    finally:
        conn.close()


def has_activity_since_last_check(guild_id: int) -> bool:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT channel_has_activity FROM guild_settings WHERE guild_id = ?", (guild_id,)
        ).fetchone()
        return bool(row["channel_has_activity"]) if row else False
    finally:
        conn.close()


def reset_activity_and_record_spawn(guild_id: int) -> None:
    conn = get_connection()
    try:
        conn.execute(
            """UPDATE guild_settings SET channel_has_activity = 0, last_spawn_at = ?
               WHERE guild_id = ?""",
            (int(time.time()), guild_id),
        )
        conn.commit()
    finally:
        conn.close()


def next_spawn_delay_seconds() -> int:
    """Random delay between 5 and 10 minutes, matching the spec."""
    return random.randint(5 * 60, 10 * 60)


def is_check_due(guild_id: int) -> bool:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT next_check_at FROM guild_settings WHERE guild_id = ?", (guild_id,)
        ).fetchone()
        if row is None:
            return False
        return int(time.time()) >= (row["next_check_at"] or 0)
    finally:
        conn.close()


def advance_next_check(guild_id: int, clear_activity: bool) -> None:
    """Called every time the periodic check actually runs for a guild,
    whether or not it resulted in a spawn - schedules the next check
    5-10 minutes out and (usually) clears the activity flag so the next
    window starts fresh."""
    conn = get_connection()
    try:
        next_due = int(time.time()) + next_spawn_delay_seconds()
        if clear_activity:
            conn.execute(
                "UPDATE guild_settings SET next_check_at = ?, channel_has_activity = 0 WHERE guild_id = ?",
                (next_due, guild_id),
            )
        else:
            conn.execute(
                "UPDATE guild_settings SET next_check_at = ? WHERE guild_id = ?",
                (next_due, guild_id),
            )
        conn.commit()
    finally:
        conn.close()


# ---------- Active spawns / catching ----------

@dataclass
class ActiveSpawn:
    id: int
    guild_id: int
    channel_id: int
    message_id: Optional[int]
    kind: str  # 'character' or 'weapon'
    collectible_id: int
    caught_by: Optional[int]
    spawned_at: int


def create_active_spawn(guild_id: int, channel_id: int, kind: str, collectible_id: int) -> int:
    conn = get_connection()
    try:
        cur = conn.execute(
            """INSERT INTO active_spawns (guild_id, channel_id, kind, collectible_id, spawned_at)
               VALUES (?, ?, ?, ?, ?)""",
            (guild_id, channel_id, kind, collectible_id, int(time.time())),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def attach_message_id(spawn_id: int, message_id: int) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE active_spawns SET message_id = ? WHERE id = ?", (message_id, spawn_id)
        )
        conn.commit()
    finally:
        conn.close()


def get_active_spawn(spawn_id: int) -> Optional[ActiveSpawn]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM active_spawns WHERE id = ?", (spawn_id,)).fetchone()
        return ActiveSpawn(**dict(row)) if row else None
    finally:
        conn.close()


def resolve_catch(spawn_id: int, guesser_discord_id: int) -> bool:
    """
    Atomically claims the spawn for guesser_discord_id IF nobody has
    claimed it yet AND the 5-minute catch window hasn't expired.
    Returns True if this call won the race, False otherwise (already
    caught, OR too slow). Safe to call concurrently.
    """
    conn = get_connection()
    try:
        cutoff = int(time.time()) - CATCH_WINDOW_SECONDS
        cur = conn.execute(
            """UPDATE active_spawns SET caught_by = ?
               WHERE id = ? AND caught_by IS NULL AND spawned_at >= ?""",
            (guesser_discord_id, spawn_id, cutoff),
        )
        conn.commit()
        return cur.rowcount == 1
    finally:
        conn.close()


def is_catch_window_expired(spawn: "ActiveSpawn") -> bool:
    return int(time.time()) - spawn.spawned_at >= CATCH_WINDOW_SECONDS