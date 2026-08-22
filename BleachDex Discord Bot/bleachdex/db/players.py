"""
Per-player state: KAN coin balance, and claim tracking for /daily,
/dailypack (a bucket of 3 pulls that refills once per day, not a
single once-a-day claim), and /weeklypack.
"""

import datetime
import time

from db.connection import get_connection

DAILY_COIN_COOLDOWN = 24 * 60 * 60
WEEKLY_PACK_COOLDOWN = 7 * 24 * 60 * 60
DAILY_PACK_LIMIT = 3
DAILY_COIN_AMOUNT = 100


def _today_str() -> str:
    return datetime.datetime.utcnow().strftime("%Y-%m-%d")


def ensure_player(discord_id: int) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO players (discord_id) VALUES (?)", (discord_id,)
        )
        conn.commit()
    finally:
        conn.close()


def get_player(discord_id: int):
    ensure_player(discord_id)
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT * FROM players WHERE discord_id = ?", (discord_id,)
        ).fetchone()
    finally:
        conn.close()


def get_balance(discord_id: int) -> int:
    return get_player(discord_id)["kan_coins"]


def add_coins(discord_id: int, amount: int) -> int:
    """Returns the new balance."""
    ensure_player(discord_id)
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE players SET kan_coins = kan_coins + ? WHERE discord_id = ?",
            (amount, discord_id),
        )
        conn.commit()
        row = conn.execute(
            "SELECT kan_coins FROM players WHERE discord_id = ?", (discord_id,)
        ).fetchone()
        return row["kan_coins"]
    finally:
        conn.close()


def spend_coins(discord_id: int, amount: int) -> bool:
    """Returns True if the player had enough and it was deducted."""
    ensure_player(discord_id)
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT kan_coins FROM players WHERE discord_id = ?", (discord_id,)
        ).fetchone()
        if row["kan_coins"] < amount:
            return False
        conn.execute(
            "UPDATE players SET kan_coins = kan_coins - ? WHERE discord_id = ?",
            (amount, discord_id),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def record_battle_win(discord_id: int) -> None:
    ensure_player(discord_id)
    conn = get_connection()
    try:
        conn.execute(
            """UPDATE players SET
                 battle_wins = battle_wins + 1,
                 current_win_streak = current_win_streak + 1,
                 best_win_streak = MAX(best_win_streak, current_win_streak + 1)
               WHERE discord_id = ?""",
            (discord_id,),
        )
        conn.commit()
    finally:
        conn.close()


def record_battle_loss(discord_id: int) -> None:
    """Resets the player's CURRENT win streak. best_win_streak is left
    untouched on purpose - an achievement earned from a past streak
    should never be un-earned just because a later battle is lost."""
    ensure_player(discord_id)
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE players SET current_win_streak = 0 WHERE discord_id = ?",
            (discord_id,),
        )
        conn.commit()
    finally:
        conn.close()


class OnCooldown(Exception):
    def __init__(self, seconds_remaining: int):
        self.seconds_remaining = seconds_remaining
        super().__init__(f"On cooldown for {seconds_remaining}s")


def claim_daily_coins(discord_id: int) -> int:
    """Returns coins granted. Raises OnCooldown if claimed too recently."""
    player = get_player(discord_id)
    now = int(time.time())
    elapsed = now - player["last_daily_coin_claim"]
    if elapsed < DAILY_COIN_COOLDOWN:
        raise OnCooldown(DAILY_COIN_COOLDOWN - elapsed)

    conn = get_connection()
    try:
        conn.execute(
            "UPDATE players SET last_daily_coin_claim = ? WHERE discord_id = ?",
            (now, discord_id),
        )
        conn.commit()
    finally:
        conn.close()
    return add_coins(discord_id, DAILY_COIN_AMOUNT)


def claim_daily_pack_slot(discord_id: int) -> int:
    """
    Daily pack is a bucket of DAILY_PACK_LIMIT pulls that resets at
    UTC midnight, not a single once-per-24h claim. Returns pulls
    remaining AFTER this claim. Raises OnCooldown (with seconds until
    next UTC midnight) if the bucket is empty.
    """
    player = get_player(discord_id)
    today = _today_str()

    conn = get_connection()
    try:
        if player["daily_pack_date"] != today:
            # new day - bucket refills
            conn.execute(
                "UPDATE players SET daily_pack_date = ?, daily_pack_pulls_used = 1 "
                "WHERE discord_id = ?",
                (today, discord_id),
            )
            conn.commit()
            return DAILY_PACK_LIMIT - 1

        if player["daily_pack_pulls_used"] >= DAILY_PACK_LIMIT:
            now = datetime.datetime.utcnow()
            tomorrow = (now + datetime.timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            seconds_remaining = int((tomorrow - now).total_seconds())
            raise OnCooldown(seconds_remaining)

        conn.execute(
            "UPDATE players SET daily_pack_pulls_used = daily_pack_pulls_used + 1 "
            "WHERE discord_id = ?",
            (discord_id,),
        )
        conn.commit()
        return DAILY_PACK_LIMIT - (player["daily_pack_pulls_used"] + 1)
    finally:
        conn.close()


def claim_weekly_pack_slot(discord_id: int) -> None:
    player = get_player(discord_id)
    now = int(time.time())
    elapsed = now - player["last_weekly_pack_claim"]
    if elapsed < WEEKLY_PACK_COOLDOWN:
        raise OnCooldown(WEEKLY_PACK_COOLDOWN - elapsed)

    conn = get_connection()
    try:
        conn.execute(
            "UPDATE players SET last_weekly_pack_claim = ? WHERE discord_id = ?",
            (now, discord_id),
        )
        conn.commit()
    finally:
        conn.close()


def format_remaining(seconds: int) -> str:
    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, _ = divmod(remainder, 60)
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"