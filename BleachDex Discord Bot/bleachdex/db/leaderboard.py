"""
/leaderboard — top players by total items owned (characters + weapons
combined), by how many of one specific character/weapon they own, or by
how many KAN coins they hold right now.

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


@dataclass
class RankedEntry:
    rank: int
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


def overall_rank(discord_id: int) -> Optional[RankedEntry]:
    """This specific player's own rank/count, even if they're way
    outside the top N shown by overall_leaderboard(). None if they
    don't own anything at all."""
    conn = get_connection()
    try:
        row = conn.execute(
            """
            WITH counts AS (
                SELECT owner_discord_id AS discord_id, COUNT(*) AS count FROM (
                    SELECT owner_discord_id FROM owned_characters
                    UNION ALL
                    SELECT owner_discord_id FROM owned_weapons
                )
                GROUP BY owner_discord_id
            ),
            ranked AS (
                SELECT discord_id, count, RANK() OVER (ORDER BY count DESC) AS rank
                FROM counts
            )
            SELECT rank, discord_id, count FROM ranked WHERE discord_id = ?
            """,
            (discord_id,),
        ).fetchone()
        return RankedEntry(row["rank"], row["discord_id"], row["count"]) if row else None
    finally:
        conn.close()


def character_rank(character_id: int, discord_id: int) -> Optional[RankedEntry]:
    conn = get_connection()
    try:
        row = conn.execute(
            """
            WITH counts AS (
                SELECT owner_discord_id AS discord_id, COUNT(*) AS count
                FROM owned_characters WHERE character_id = ?
                GROUP BY owner_discord_id
            ),
            ranked AS (
                SELECT discord_id, count, RANK() OVER (ORDER BY count DESC) AS rank
                FROM counts
            )
            SELECT rank, discord_id, count FROM ranked WHERE discord_id = ?
            """,
            (character_id, discord_id),
        ).fetchone()
        return RankedEntry(row["rank"], row["discord_id"], row["count"]) if row else None
    finally:
        conn.close()


def weapon_rank(weapon_id: int, discord_id: int) -> Optional[RankedEntry]:
    conn = get_connection()
    try:
        row = conn.execute(
            """
            WITH counts AS (
                SELECT owner_discord_id AS discord_id, COUNT(*) AS count
                FROM owned_weapons WHERE weapon_id = ?
                GROUP BY owner_discord_id
            ),
            ranked AS (
                SELECT discord_id, count, RANK() OVER (ORDER BY count DESC) AS rank
                FROM counts
            )
            SELECT rank, discord_id, count FROM ranked WHERE discord_id = ?
            """,
            (weapon_id, discord_id),
        ).fetchone()
        return RankedEntry(row["rank"], row["discord_id"], row["count"]) if row else None
    finally:
        conn.close()


def kan_leaderboard(limit: int = 10) -> list[LeaderboardEntry]:
    """Players with the most KAN right now (current balance, not lifetime
    earnings). `count` is the KAN balance. Players with 0 KAN are left out."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT discord_id, kan_coins AS count FROM players
               WHERE kan_coins > 0
               ORDER BY kan_coins DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [LeaderboardEntry(r["discord_id"], r["count"]) for r in rows]
    finally:
        conn.close()


def kan_rank(discord_id: int) -> Optional[RankedEntry]:
    """This player's own KAN rank/balance, even if they're outside the top N.
    None if they have no KAN."""
    conn = get_connection()
    try:
        row = conn.execute(
            """
            WITH ranked AS (
                SELECT discord_id, kan_coins AS count,
                       RANK() OVER (ORDER BY kan_coins DESC) AS rank
                FROM players WHERE kan_coins > 0
            )
            SELECT rank, discord_id, count FROM ranked WHERE discord_id = ?
            """,
            (discord_id,),
        ).fetchone()
        return RankedEntry(row["rank"], row["discord_id"], row["count"]) if row else None
    finally:
        conn.close()