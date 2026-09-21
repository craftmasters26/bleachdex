"""
The spawn engine's data layer - MESSAGE-DRIVEN, not timer-driven.

How it works now:

1. Admin runs /set spawn #channel - stored in guild_settings, along
   with last_spawn_at (when the guild last got a spawn) reset to "now".

2. Every message sent in the configured channel calls record_message(),
   which bumps message_count_since_spawn by 1 and immediately checks
   spawn_readiness_score() against SPAWN_THRESHOLD. There is NO
   background polling loop anymore - a spawn can only ever be
   triggered by an actual incoming message, matching "only spawns if
   a user sends a message."

3. The readiness formula:

       score = scaled_message_count + TIME_MULTIPLIER * minutes_elapsed

   where scaled_message_count is message_count_since_spawn capped at
   MESSAGE_CAP (so a burst of spam can't force an instant spawn) and
   minutes_elapsed is time since last_spawn_at. With the defaults
   below (MESSAGE_CAP=5, TIME_MULTIPLIER=1.0, THRESHOLD=10.0), an
   extremely active channel can't spawn faster than a 5-minute floor
   (5 message-points + 5 minutes x 1.0 = 10), and a quiet channel with
   only occasional messages will still eventually cross the threshold
   around the 10-minute mark from time alone - landing spawns roughly
   in the 5-10 minute range you asked for, scaled by how chatty the
   channel actually is.

4. When record_message() reports ready=True, the caller (cogs/spawn.py)
   posts the spawn and calls reset_after_spawn() to zero the counter
   and restart the clock.

5. The spawn is recorded in active_spawns with caught_by = NULL.
   Catching is a race - whoever's /catch guess lands first while
   caught_by is still NULL AND the catch window hasn't expired wins.
   resolve_catch() uses an atomic UPDATE ... WHERE caught_by IS NULL
   so two simultaneous correct guesses can't both "win".
"""

import time
from dataclasses import dataclass
from typing import Optional

from db.connection import get_connection

# Once a spawn goes out, only this many seconds to catch it - after
# that, resolve_catch() below refuses even a correct guess.
CATCH_WINDOW_SECONDS = 5 * 60

# --- Spawn readiness tuning ---
# score = min(message_count, MESSAGE_CAP) + TIME_MULTIPLIER * minutes_elapsed
SPAWN_THRESHOLD = 20.0
MESSAGE_CAP = 5.0
TIME_MULTIPLIER = 1.0


# ---------- Guild spawn config ----------

def set_spawn_channel(guild_id: int, channel_id: int) -> None:
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO guild_settings
                 (guild_id, spawn_channel_id, last_spawn_at, message_count_since_spawn)
               VALUES (?, ?, ?, 0)
               ON CONFLICT(guild_id) DO UPDATE SET spawn_channel_id = excluded.spawn_channel_id""",
            (guild_id, channel_id, int(time.time())),
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


def spawn_readiness_score(message_count: int, minutes_elapsed: float) -> float:
    """Pure function, no DB access - kept separate from record_message()
    so the scoring math itself is easy to unit test."""
    scaled_message_count = min(message_count, MESSAGE_CAP)
    return scaled_message_count + TIME_MULTIPLIER * minutes_elapsed


def record_message(guild_id: int) -> bool:
    """
    Call this for every message sent in a guild's configured spawn
    channel. Increments the message counter, computes readiness, and
    returns True if a spawn should fire right now.

    IMPORTANT: when this returns True, the counter has ALREADY been
    reset back to 0 (and last_spawn_at updated) as part of this same
    call - not left for the caller to reset after posting the spawn.
    That used to be a real bug: posting a spawn involves awaiting I/O
    (rendering the card image, uploading it to Discord), and during
    that await, more messages could arrive and each independently call
    record_message() again before the counter was reset - since the
    score was already over threshold, every one of them ALSO returned
    True, causing 2-3 duplicate spawns from a single burst of chat.
    Resetting immediately, before any async work happens, closes that
    window - the next message right after this one starts counting
    from zero again regardless of how long spawn_now() takes.
    """
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT last_spawn_at, message_count_since_spawn FROM guild_settings WHERE guild_id = ?",
            (guild_id,),
        ).fetchone()
        if row is None:
            return False

        new_count = row["message_count_since_spawn"] + 1
        minutes_elapsed = (int(time.time()) - (row["last_spawn_at"] or 0)) / 60.0
        score = spawn_readiness_score(new_count, minutes_elapsed)
        ready = score >= SPAWN_THRESHOLD

        if ready:
            conn.execute(
                """UPDATE guild_settings SET message_count_since_spawn = 0, last_spawn_at = ?
                   WHERE guild_id = ?""",
                (int(time.time()), guild_id),
            )
        else:
            conn.execute(
                "UPDATE guild_settings SET message_count_since_spawn = ? WHERE guild_id = ?",
                (new_count, guild_id),
            )
        conn.commit()
        return ready
    finally:
        conn.close()


def reset_after_spawn(guild_id: int) -> None:
    """
    No longer needed for the normal spawn flow - record_message() now
    resets the counter itself the instant it decides to spawn, before
    any async work happens (see its docstring for why). Kept around
    only in case anything wants to manually force a guild's counter
    back to zero (e.g. an admin "reset the spawn meter" command).
    """
    conn = get_connection()
    try:
        conn.execute(
            """UPDATE guild_settings SET message_count_since_spawn = 0, last_spawn_at = ?
               WHERE guild_id = ?""",
            (int(time.time()), guild_id),
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
    claimed it yet AND the catch window hasn't expired. Returns True
    if this call won the race, False otherwise (already caught, OR too
    slow). Safe to call concurrently.
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