"""
Achievements.

Catch-count achievements (Soul Collector, Hollow Hunter, Zanpakutō
Master, Bankai Achieved, etc.) read from catch_log - a permanent
record of every catch (pack pull, spawn catch, or shop purchase),
written automatically by db/collection.py's grant_character/
grant_weapon. Trading something away does NOT remove it from
catch_log, so these achievements track "have you ever caught N of
these", not "do you currently own N of these".

Ownership achievements (Collector, Hoarder, Pack Rat, Armory, Soul
Army) are the opposite on purpose - they read CURRENT holdings
(_total_items_owned), so trading everything away would drop your
progress. That's intentional: "hoarding" is about what you have right
now, not what you've ever touched.

Hollow-type and Bankai-type achievements depend on the `position`
field you set when adding a character/weapon (e.g. a character needs
"Hollow" somewhere in its position text; a weapon needs "Bankai").
Zanpakutō Master counts ALL weapon catches, since every weapon in this
bot's fiction is a Zanpakuto (see the very first design conversation
that established weapon = Zanpakuto).

Call check_and_grant(discord_id) after any action that could complete
one of these (a catch, a completed trade, a battle win/loss). It's
cheap - just a few COUNT queries - and safe to call every time.
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


# ---------- Progress-check helpers ----------

def _total_items_owned(discord_id: int) -> int:
    """CURRENT holdings - drops if you trade things away."""
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


def _battle_streak(discord_id: int) -> int:
    """Best win streak ever reached, not the current one - so this
    achievement stays earned even after a later loss resets the
    current streak. See db/players.py's record_battle_win/loss."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT best_win_streak FROM players WHERE discord_id = ?", (discord_id,)
        ).fetchone()
        return row["best_win_streak"] if row else 0
    finally:
        conn.close()


def _total_caught(discord_id: int) -> int:
    """Lifetime catches (characters + weapons combined), never reduced
    by trading things away."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM catch_log WHERE discord_id = ?", (discord_id,)
        ).fetchone()
        return row["c"]
    finally:
        conn.close()


def _hollow_count(discord_id: int) -> int:
    """Lifetime catches of characters whose position contains "Hollow"."""
    conn = get_connection()
    try:
        row = conn.execute(
            """SELECT COUNT(*) AS c FROM catch_log cl
               JOIN characters c ON c.id = cl.item_id
               WHERE cl.discord_id = ? AND cl.kind = 'character'
                 AND c.position LIKE '%Hollow%' COLLATE NOCASE""",
            (discord_id,),
        ).fetchone()
        return row["c"]
    finally:
        conn.close()


def _zanpakuto_count(discord_id: int) -> int:
    """Lifetime weapon catches - every weapon IS a Zanpakuto in this
    bot's fiction, so this is just every weapon ever caught."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM catch_log WHERE discord_id = ? AND kind = 'weapon'",
            (discord_id,),
        ).fetchone()
        return row["c"]
    finally:
        conn.close()


def _bankai_count(discord_id: int) -> int:
    """Lifetime catches of weapons whose position contains "Bankai"."""
    conn = get_connection()
    try:
        row = conn.execute(
            """SELECT COUNT(*) AS c FROM catch_log cl
               JOIN weapons w ON w.id = cl.item_id
               WHERE cl.discord_id = ? AND cl.kind = 'weapon'
                 AND w.position LIKE '%Bankai%' COLLATE NOCASE""",
            (discord_id,),
        ).fetchone()
        return row["c"]
    finally:
        conn.close()


# ---------- The achievement list ----------

ACHIEVEMENTS: list[Achievement] = [
    # ─── Collection / Catch ─────────────────────────────────────────
    Achievement("soul_collector", "Soul Collector", "Catch 50 items", 50, _total_caught),
    Achievement("reaper_apprentice", "Reaper Apprentice", "Catch 250 items", 250, _total_caught),
    Achievement("lieutenant_class", "Lieutenant-Class", "Catch 500 items", 500, _total_caught),
    Achievement("captain_class", "Captain-Class", "Catch 1,500 items", 1500, _total_caught),
    Achievement("head_captain", "Head-Captain", "Catch 3,000 items", 3000, _total_caught),

    # ─── Rarity-specific collection ─────────────────────────────────
    Achievement("hollow_hunter", "Hollow Hunter", "Obtain 5 Hollow-type items", 5, _hollow_count),
    Achievement("vasto_lorde", "Vasto Lorde", "Obtain 25 Hollow-type items", 25, _hollow_count),
    Achievement("zanpakuto_master", "Zanpakutō Master", "Obtain 50 Zanpakutō", 50, _zanpakuto_count),
    Achievement("bankai_achieved", "Bankai Achieved", "Obtain 5 Bankai-tier items", 5, _bankai_count),

    # ─── Trading ─────────────────────────────────────────────────────
    Achievement("first_deal", "First Deal", "Complete 1 trade", 1, _completed_trades),
    Achievement("negotiator", "Negotiator", "Complete 10 trades", 10, _completed_trades),
    Achievement("trade_adept", "Trade Adept", "Complete 25 trades", 25, _completed_trades),
    Achievement("soul_market", "Soul Market", "Complete 50 trades", 50, _completed_trades),
    Achievement("merchant_of_death", "Merchant of Death", "Complete 100 trades", 100, _completed_trades),
    Achievement("shadow_broker", "Shadow Broker", "Complete 200 trades", 200, _completed_trades),
    Achievement("zen_merchant", "Zen Merchant", "Complete 500 trades", 500, _completed_trades),

    # ─── Battle ──────────────────────────────────────────────────────
    Achievement("first_blood", "First Blood", "Win your first battle", 1, _battle_wins),
    Achievement("shinigami", "Shinigami", "Win 10 battles", 10, _battle_wins),
    Achievement("seated_officer", "Seated Officer", "Win 25 battles", 25, _battle_wins),
    Achievement("lieutenant", "Lieutenant", "Win 50 battles", 50, _battle_wins),
    Achievement("captain", "Captain", "Win 100 battles", 100, _battle_wins),
    Achievement("kenpachi", "Kenpachi", "Win 250 battles", 250, _battle_wins),
    Achievement("undefeated", "Undefeated", "Win 10 battles in a row", 10, _battle_streak),
    Achievement("consecutive_kills", "Consecutive Kills", "Win 25 battles in a row", 25, _battle_streak),

    # ─── Ownership / Hoarding ────────────────────────────────────────
    Achievement("collector", "Collector", "Own 100 items", 100, _total_items_owned),
    Achievement("hoarder", "Hoarder", "Own 250 items", 250, _total_items_owned),
    Achievement("pack_rat", "Pack Rat", "Own 500 items", 500, _total_items_owned),
    Achievement("armory", "Armory", "Own 1,000 items", 1000, _total_items_owned),
    Achievement("soul_army", "Soul Army", "Own 2,500 items", 2500, _total_items_owned),
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
        for a in ACHIEVEMENTS:
            if a.key in already:
                continue
            if a.progress_fn(discord_id) >= a.threshold:
                conn.execute(
                    "INSERT OR IGNORE INTO player_achievements "
                    "(discord_id, achievement_key, earned_at) VALUES (?, ?, ?)",
                    (discord_id, a.key, int(time.time())),
                )
                newly_earned.append(a)
        conn.commit()
    finally:
        conn.close()
    return newly_earned