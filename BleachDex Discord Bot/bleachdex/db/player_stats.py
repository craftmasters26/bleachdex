"""
Generic per-player counters, for achievements that don't have an
existing table/column to read progress from (battle wins, trade
counts, etc. already have their own homes - this is for the rest,
like "beat the server owner in a battle" or "traded with an admin").
"""
 
from db.connection import get_connection
 
 
def increment(discord_id: int, stat_key: str, by: int = 1) -> None:
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO player_stats (discord_id, stat_key, value) VALUES (?, ?, ?)
               ON CONFLICT(discord_id, stat_key) DO UPDATE SET value = value + excluded.value""",
            (discord_id, stat_key, by),
        )
        conn.commit()
    finally:
        conn.close()
 
 
def get(discord_id: int, stat_key: str) -> int:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT value FROM player_stats WHERE discord_id = ? AND stat_key = ?",
            (discord_id, stat_key),
        ).fetchone()
        return row["value"] if row else 0
    finally:
        conn.close()