"""
Achievements - only ones this bot can actually track are included.
Skipped from the reference screenshot: Favorite'd/Favorite list (no
favoriting feature exists), Perfect stats (characters don't have
rollable/randomized stats, so there's no "perfect" to hit), and
anything that read as seasonal/franchise-specific (Spooky, Pink
blessing, Birthday celebrations, Sons of Whitebeard, 5-sword style,
Nakama, Fruit basket, Haki knot master, Shiny).

Call check_and_grant(discord_id) after any action that could complete
one of these (a catch, a completed trade, a battle win). It's cheap -
just a few COUNT queries - and safe to call every time.
"""

from dataclasses import dataclass
from typing import Callable

from db.connection import get_connection
from db import collection as coll


@dataclass
class Achievement:
    key: str
    name: str
    description: str
    threshold: int
    progress_fn: Callable[[int], int]


def _total_items_owned(discord_id: int) -> int:
    return len(coll.list_owned_characters(discord_id)) + len(coll.list_owned_weapons(discord_id))


def _completed_trades(discord_id: int) -> int:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM trades WHERE status = 'completed' "
            "AND (user_a_id = ? OR user_b_id = ?)",
            (discord_id, discord_id),
        ).fetchone()
        return row["c"]
    finally:
        conn.close()


def _battle_wins(discord_id: int) -> int:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT battle_wins FROM players WHERE discord_id = ?", (discord_id,)
        ).fetchone()
        return row["battle_wins"] if row else 0
    finally:
        conn.close()


ACHIEVEMENTS: list[Achievement] = [
    Achievement("trading_beginner", "Trading Beginner", "Complete 1 trade", 1, _completed_trades),
    Achievement("trading_novice", "Trading Novice", "Complete 5 trades", 5, _completed_trades),
    Achievement("semi_pro", "Semi-Pro Trader", "Complete 15 trades", 15, _completed_trades),
    Achievement("trading_expert", "Trading Expert", "Complete 30 trades", 30, _completed_trades),
    Achievement("trading_professional", "Trading Professional", "Complete 50 trades", 50, _completed_trades),
    Achievement("hoarder", "Hoarder", "Own 100 total characters/weapons", 100, _total_items_owned),
    Achievement("fighter", "Fighter", "Win 10 battles", 10, _battle_wins),
]


def earned_keys(discord_id: int) -> set[str]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT achievement_key FROM player_achievements WHERE discord_id = ?",
            (discord_id,),
        ).fetchall()
        return {r["achievement_key"] for r in rows}
    finally:
        conn.close()


def check_and_grant(discord_id: int) -> list[Achievement]:
    """Checks every achievement's progress and grants any newly-met
    ones. Returns the list of Achievements newly earned THIS call (so
    you can announce them) - empty list if nothing new."""
    import time

    already = earned_keys(discord_id)
    newly_earned = []
    conn = get_connection()
    try:
        for ach in ACHIEVEMENTS:
            if ach.key in already:
                continue
            if ach.progress_fn(discord_id) >= ach.threshold:
                conn.execute(
                    "INSERT OR IGNORE INTO player_achievements "
                    "(discord_id, achievement_key, earned_at) VALUES (?, ?, ?)",
                    (discord_id, ach.key, int(time.time())),
                )
                newly_earned.append(ach)
        conn.commit()
    finally:
        conn.close()
    return newly_earned