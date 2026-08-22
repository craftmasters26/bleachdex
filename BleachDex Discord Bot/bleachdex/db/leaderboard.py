"""
/leaderboard — top players by total items owned (characters + weapons
combined), or by how many of one specific character/weapon they own.

This counts CURRENT ownership (owned_characters/owned_weapons rows),
not a permanent "lifetime catches" log - so a trade moves the count
to the new owner. If you want lifetime-catch tracking that survives
trades, say so and I'll add a separate catches table for that.
"""

from dataclasses import dataclass
from typing import Optional

from db.connection import get_connection


@dataclass
class LeaderboardEntry:
    discord_id: int
    count: int


def overall_leaderboard(limit: int = 10) -> list[LeaderboardEntry]:
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT owner_discord_id AS discord_id, COUNT(*) AS count FROM (
                SELECT owner_discord_id FROM owned_characters
                UNION ALL
                SELECT owner_discord_id FROM owned_weapons
            )
            GROUP BY owner_discord_id
            ORDER BY count DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [LeaderboardEntry(r["discord_id"], r["count"]) for r in rows]
    finally:
        conn.close()


def character_leaderboard(character_id: int, limit: int = 10) -> list[LeaderboardEntry]:
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT owner_discord_id AS discord_id, COUNT(*) AS count
               FROM owned_characters WHERE character_id = ?
               GROUP BY owner_discord_id ORDER BY count DESC LIMIT ?""",
            (character_id, limit),
        ).fetchall()
        return [LeaderboardEntry(r["discord_id"], r["count"]) for r in rows]
    finally:
        conn.close()


def weapon_leaderboard(weapon_id: int, limit: int = 10) -> list[LeaderboardEntry]:
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT owner_discord_id AS discord_id, COUNT(*) AS count
               FROM owned_weapons WHERE weapon_id = ?
               GROUP BY owner_discord_id ORDER BY count DESC LIMIT ?""",
            (weapon_id, limit),
        ).fetchall()
        return [LeaderboardEntry(r["discord_id"], r["count"]) for r in rows]
    finally:
        conn.close()
