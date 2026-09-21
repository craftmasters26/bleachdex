"""
What players actually HOLD from boss drops. db/bosses.py's
resolve_defeat() only decides/announces who gets what when a boss
dies - this is the real inventory that gets credited at that moment
and spent later by /craft.
"""

from db.connection import get_connection


def add(discord_id: int, drop_name: str, qty: int = 1) -> None:
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO owned_boss_drops (discord_id, drop_name, quantity) VALUES (?, ?, ?)
               ON CONFLICT(discord_id, drop_name) DO UPDATE SET quantity = quantity + excluded.quantity""",
            (discord_id, drop_name, qty),
        )
        conn.commit()
    finally:
        conn.close()


def get_quantity(discord_id: int, drop_name: str) -> int:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT quantity FROM owned_boss_drops WHERE discord_id = ? AND drop_name = ?",
            (discord_id, drop_name),
        ).fetchone()
        return row["quantity"] if row else 0
    finally:
        conn.close()


def list_inventory(discord_id: int) -> list[tuple[str, int]]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT drop_name, quantity FROM owned_boss_drops WHERE discord_id = ? AND quantity > 0 ORDER BY drop_name",
            (discord_id,),
        ).fetchall()
        return [(r["drop_name"], r["quantity"]) for r in rows]
    finally:
        conn.close()


class InsufficientDrops(Exception):
    pass


def spend(discord_id: int, drop_name: str, qty: int) -> None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT quantity FROM owned_boss_drops WHERE discord_id = ? AND drop_name = ?",
            (discord_id, drop_name),
        ).fetchone()
        have = row["quantity"] if row else 0
        if have < qty:
            raise InsufficientDrops(
                f"You need {qty}x {drop_name}, but you only have {have}."
            )
        conn.execute(
            "UPDATE owned_boss_drops SET quantity = quantity - ? WHERE discord_id = ? AND drop_name = ?",
            (qty, discord_id, drop_name),
        )
        conn.commit()
    finally:
        conn.close()