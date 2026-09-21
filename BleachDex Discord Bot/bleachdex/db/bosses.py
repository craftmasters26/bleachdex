"""
Preset boss battles - solo fights spawned from the Boss.txt list (see
seed_bossbattle.py). Each challenger gets their own private 10-round
fight against a fresh copy of the boss's HP, using their own /team
roster - see cogs/boss.py's BossChallengeView for the fight loop.

Drops are independent rolls: every drop on a boss is rolled separately
against its own percentage, so a player can walk away with none, some,
or all of them. They're credited into owned_boss_drops (db/inventory.py),
so /craft can spend "Hollow Mask" / "Hogyoku" / etc. Drops live in the
bossbattle_drops table (one row per boss per drop, any number allowed)
rather than fixed columns on bossbattle_bosses.

Bosses reach a channel two ways:
  - /admin bossbattle - an admin manually spawns one right now.
  - The hourly auto-spawn task in cogs/boss.py, which posts a random
    boss once an hour (on the hour, GMT+8) into the SAME channel
    that's already configured for regular Soul spawns (db/spawns.py's
    spawn_channel_id on guild_settings) - there's no separate boss
    channel to configure. last_boss_spawn_hour_key (also on
    guild_settings) just remembers the last hour a boss went out for
    that guild, so a bot restart mid-hour can't double-spawn.
"""

import random
import time
from dataclasses import dataclass, field

from db.connection import get_connection


@dataclass
class BossDrop:
    item_name: str
    rate: float
    emoji_key: str = ""


@dataclass
class PresetBoss:
    id: int
    category: str
    name: str
    image_path: str
    max_hp: int
    dmg_per_round: int
    enabled: bool
    drops: list[BossDrop] = field(default_factory=list)


def _row_to_preset_boss(row, drops: list[BossDrop]) -> PresetBoss:
    return PresetBoss(
        row["id"], row["category"], row["name"], row["image_path"],
        row["max_hp"], row["dmg_per_round"], bool(row["enabled"]), drops,
    )


def _get_drops(conn, boss_id: int) -> list[BossDrop]:
    rows = conn.execute(
        "SELECT item_name, rate, emoji_key FROM bossbattle_drops "
        "WHERE boss_id = ? ORDER BY sort_order",
        (boss_id,),
    ).fetchall()
    return [BossDrop(r["item_name"], r["rate"], r["emoji_key"]) for r in rows]


def upsert_preset_boss(
    category: str,
    name: str,
    image_path: str,
    max_hp: int,
    dmg_per_round: int,
    drops: list[tuple[str, float, str]] = (),
) -> PresetBoss:
    """Creates or updates a preset bossbattle boss by name - safe to call
    repeatedly (e.g. every startup via seed_bossbattle.py) since it's an
    upsert, not an insert. `drops` is a list of (item_name, rate,
    emoji_key) tuples - any number of them, replacing whatever the
    boss's drop list was before."""
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO bossbattle_bosses
                 (category, name, image_path, max_hp, dmg_per_round, enabled, created_at)
               VALUES (?, ?, ?, ?, ?, 1, ?)
               ON CONFLICT(name) DO UPDATE SET
                 category = excluded.category,
                 image_path = excluded.image_path,
                 max_hp = excluded.max_hp,
                 dmg_per_round = excluded.dmg_per_round""",
            (category, name, image_path, max_hp, dmg_per_round, int(time.time())),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM bossbattle_bosses WHERE name = ?", (name,)).fetchone()
        boss_id = row["id"]

        # Replace this boss's drop list wholesale rather than trying to
        # diff it - simplest way to keep re-running seed_bossbattle.py
        # idempotent even when a drop is renamed, added, or removed.
        conn.execute("DELETE FROM bossbattle_drops WHERE boss_id = ?", (boss_id,))
        conn.executemany(
            "INSERT INTO bossbattle_drops (boss_id, item_name, rate, emoji_key, sort_order) "
            "VALUES (?, ?, ?, ?, ?)",
            [(boss_id, d_name, d_rate, d_emoji, i) for i, (d_name, d_rate, d_emoji) in enumerate(drops)],
        )
        conn.commit()

        return _row_to_preset_boss(row, _get_drops(conn, boss_id))
    finally:
        conn.close()


def list_preset_bosses(enabled_only: bool = True) -> list[PresetBoss]:
    conn = get_connection()
    try:
        q = "SELECT * FROM bossbattle_bosses" + (" WHERE enabled = 1" if enabled_only else "")
        rows = conn.execute(q + " ORDER BY category, max_hp").fetchall()
        return [_row_to_preset_boss(r, _get_drops(conn, r["id"])) for r in rows]
    finally:
        conn.close()


def get_preset_boss_by_name(name: str) -> PresetBoss | None:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM bossbattle_bosses WHERE name = ?", (name,)).fetchone()
        return _row_to_preset_boss(row, _get_drops(conn, row["id"])) if row else None
    finally:
        conn.close()


def get_preset_boss_by_id(boss_id: int) -> PresetBoss | None:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM bossbattle_bosses WHERE id = ?", (boss_id,)).fetchone()
        return _row_to_preset_boss(row, _get_drops(conn, boss_id)) if row else None
    finally:
        conn.close()


def pick_random_preset_boss(categories=None) -> PresetBoss | None:
    """Picks any one enabled preset boss at random (no weighting by
    tier/HP). Used by the hourly auto-spawn task in cogs/boss.py (no
    filter) and by /admin bossbattle's faction option, which passes the
    set of boss categories that belong to the chosen faction."""
    bosses = list_preset_bosses(enabled_only=True)
    if categories is not None:
        bosses = [b for b in bosses if b.category in categories]
    if not bosses:
        return None
    return random.choice(bosses)


def roll_preset_drops(boss: PresetBoss) -> list[tuple[str, str]]:
    """Rolls every one of the boss's drops independently against its
    own percentage chance (0-100). Returns a list of (drop_name,
    emoji_key) for each one that hit - can be empty, or any combination
    of however many drops the boss has."""
    won: list[tuple[str, str]] = []
    for d in boss.drops:
        if d.item_name and random.uniform(0, 100) < d.rate:
            won.append((d.item_name, d.emoji_key))
    return won


# ---------------------------------------------------------------------------
# hourly auto-spawn (GMT+8) - see cogs/boss.py's hourly_boss_spawn task
# loop. Deliberately reuses the SAME channel as regular Soul spawns
# (db/spawns.py's spawn_channel_id / set_spawn_channel(), set via
# /set spawn) rather than a separate boss-only channel setting - so
# there's only one spawn channel per server to configure at all.
# ---------------------------------------------------------------------------

def list_hourly_spawn_targets() -> list[tuple[int, int, str]]:
    """Returns (guild_id, spawn_channel_id, last_boss_spawn_hour_key)
    for every guild that has a Soul spawn channel configured - that's
    also where the hourly boss spawn posts."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT guild_id, spawn_channel_id, last_boss_spawn_hour_key "
            "FROM guild_settings WHERE spawn_channel_id IS NOT NULL"
        ).fetchall()
        return [
            (r["guild_id"], r["spawn_channel_id"], r["last_boss_spawn_hour_key"] or "")
            for r in rows
        ]
    finally:
        conn.close()


def mark_boss_spawned(guild_id: int, hour_key: str) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE guild_settings SET last_boss_spawn_hour_key = ? WHERE guild_id = ?",
            (hour_key, guild_id),
        )
        conn.commit()
    finally:
        conn.close()