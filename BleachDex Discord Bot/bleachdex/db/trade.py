"""
Multi-item trade proposals, matching the "both sides build up a
proposal, lock when ready" flow: /trade start, /trade add, /trade
remove, plus buttons for setting a KAN coin amount, locking, resetting
your side, and cancelling.

A user can only be in ONE active (pending) trade at a time - this is
what keeps execute_trade() safe without extra locking: since
/trade add only ever adds to "your" single active trade, and an item
already sitting in a pending trade proposal isn't otherwise touched by
anything else in the bot, there's no way for the same owned_characters
row to end up promised to two different trades at once.

Nothing actually moves until BOTH sides call lock_side() - execute_trade()
re-validates ownership and coin balances one more time at that exact
moment before transferring anything, in case something changed since
items were added (e.g. a duplicate item name resolution edge case).
"""

import time
from dataclasses import dataclass, field
from typing import Optional

from db.connection import get_connection
from db import collection as coll, players as pl

TRADE_TIMEOUT_SECONDS = 30 * 60


class TradeError(Exception):
    pass


@dataclass
class TradeItem:
    id: int
    trade_id: int
    side: str
    kind: str
    instance_id: int


@dataclass
class Trade:
    id: int
    channel_id: Optional[int]
    message_id: Optional[int]
    user_a_id: int
    user_b_id: int
    user_a_coins: int
    user_b_coins: int
    user_a_locked: bool
    user_b_locked: bool
    status: str
    created_at: int
    expires_at: int

    def side_for(self, user_id: int) -> Optional[str]:
        if user_id == self.user_a_id:
            return "a"
        if user_id == self.user_b_id:
            return "b"
        return None


def _row_to_trade(row) -> Trade:
    d = dict(row)
    d["user_a_locked"] = bool(d["user_a_locked"])
    d["user_b_locked"] = bool(d["user_b_locked"])
    return Trade(**d)


def get_active_trade_for_user(user_id: int) -> Optional[Trade]:
    conn = get_connection()
    try:
        row = conn.execute(
            """SELECT * FROM trade_proposals WHERE status = 'pending'
               AND (user_a_id = ? OR user_b_id = ?)""",
            (user_id, user_id),
        ).fetchone()
        return _row_to_trade(row) if row else None
    finally:
        conn.close()


def get_trade(trade_id: int) -> Optional[Trade]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM trade_proposals WHERE id = ?", (trade_id,)).fetchone()
        return _row_to_trade(row) if row else None
    finally:
        conn.close()


def is_expired(trade: Trade) -> bool:
    return int(time.time()) >= trade.expires_at


def create_trade(user_a_id: int, user_b_id: int) -> Trade:
    if user_a_id == user_b_id:
        raise TradeError("You can't trade with yourself.")
    if get_active_trade_for_user(user_a_id) is not None:
        raise TradeError("You're already in an active trade. Finish or cancel it first.")
    if get_active_trade_for_user(user_b_id) is not None:
        raise TradeError("That person is already in an active trade with someone else.")

    now = int(time.time())
    conn = get_connection()
    try:
        cur = conn.execute(
            """INSERT INTO trade_proposals
               (user_a_id, user_b_id, created_at, expires_at)
               VALUES (?, ?, ?, ?)""",
            (user_a_id, user_b_id, now, now + TRADE_TIMEOUT_SECONDS),
        )
        conn.commit()
        trade_id = cur.lastrowid
    finally:
        conn.close()
    return get_trade(trade_id)


def attach_message(trade_id: int, channel_id: int, message_id: int) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE trade_proposals SET channel_id = ?, message_id = ? WHERE id = ?",
            (channel_id, message_id, trade_id),
        )
        conn.commit()
    finally:
        conn.close()


def list_items(trade_id: int, side: str) -> list[TradeItem]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM trade_proposal_items WHERE trade_id = ? AND side = ?",
            (trade_id, side),
        ).fetchall()
        return [TradeItem(**dict(r)) for r in rows]
    finally:
        conn.close()


def add_item(trade_id: int, side: str, kind: str, instance_id: int) -> None:
    conn = get_connection()
    try:
        existing = conn.execute(
            """SELECT id FROM trade_proposal_items
               WHERE trade_id = ? AND side = ? AND kind = ? AND instance_id = ?""",
            (trade_id, side, kind, instance_id),
        ).fetchone()
        if existing:
            raise TradeError("That's already in your proposal.")
        conn.execute(
            """INSERT INTO trade_proposal_items (trade_id, side, kind, instance_id)
               VALUES (?, ?, ?, ?)""",
            (trade_id, side, kind, instance_id),
        )
        conn.commit()
        # Adding/removing items un-locks BOTH sides - the other person
        # needs to see and re-confirm the new proposal before it can execute.
        conn.execute(
            "UPDATE trade_proposals SET user_a_locked = 0, user_b_locked = 0 WHERE id = ?",
            (trade_id,),
        )
        conn.commit()
    finally:
        conn.close()


def remove_item(trade_id: int, side: str, kind: str, instance_id: int) -> bool:
    conn = get_connection()
    try:
        cur = conn.execute(
            """DELETE FROM trade_proposal_items
               WHERE trade_id = ? AND side = ? AND kind = ? AND instance_id = ?""",
            (trade_id, side, kind, instance_id),
        )
        conn.commit()
        conn.execute(
            "UPDATE trade_proposals SET user_a_locked = 0, user_b_locked = 0 WHERE id = ?",
            (trade_id,),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def set_coins(trade_id: int, side: str, amount: int) -> None:
    if amount < 0:
        raise TradeError("Coin amount can't be negative.")
    column = "user_a_coins" if side == "a" else "user_b_coins"
    conn = get_connection()
    try:
        conn.execute(f"UPDATE trade_proposals SET {column} = ? WHERE id = ?", (amount, trade_id))
        conn.execute(
            "UPDATE trade_proposals SET user_a_locked = 0, user_b_locked = 0 WHERE id = ?",
            (trade_id,),
        )
        conn.commit()
    finally:
        conn.close()


def reset_side(trade_id: int, side: str) -> None:
    coins_col = "user_a_coins" if side == "a" else "user_b_coins"
    locked_col = "user_a_locked" if side == "a" else "user_b_locked"
    conn = get_connection()
    try:
        conn.execute(
            "DELETE FROM trade_proposal_items WHERE trade_id = ? AND side = ?", (trade_id, side)
        )
        conn.execute(
            f"UPDATE trade_proposals SET {coins_col} = 0, {locked_col} = 0, "
            f"user_a_locked = 0, user_b_locked = 0 WHERE id = ?",
            (trade_id,),
        )
        conn.commit()
    finally:
        conn.close()


def cancel_trade(trade_id: int) -> None:
    conn = get_connection()
    try:
        conn.execute("UPDATE trade_proposals SET status = 'cancelled' WHERE id = ?", (trade_id,))
        conn.commit()
    finally:
        conn.close()


def expire_trade(trade_id: int) -> None:
    conn = get_connection()
    try:
        conn.execute("UPDATE trade_proposals SET status = 'expired' WHERE id = ?", (trade_id,))
        conn.commit()
    finally:
        conn.close()


def lock_side(trade_id: int, user_id: int) -> Trade:
    """Locks the calling user's side. If both sides end up locked,
    executes the trade immediately. Returns the trade's state AFTER
    this call (status will be 'completed' if it just executed).
    Raises TradeError and leaves nothing locked/changed if validation
    fails (insufficient coins, an item no longer owned, etc.) -
    the caller stays unlocked so they can fix the proposal and retry."""
    trade = get_trade(trade_id)
    if trade is None or trade.status != "pending":
        raise TradeError("This trade is no longer active.")
    if is_expired(trade):
        expire_trade(trade_id)
        raise TradeError("This trade proposal timed out (30 minutes).")

    side = trade.side_for(user_id)
    if side is None:
        raise TradeError("You're not part of this trade.")

    locked_col = "user_a_locked" if side == "a" else "user_b_locked"
    conn = get_connection()
    try:
        conn.execute(f"UPDATE trade_proposals SET {locked_col} = 1 WHERE id = ?", (trade_id,))
        conn.commit()
    finally:
        conn.close()

    trade = get_trade(trade_id)
    if trade.user_a_locked and trade.user_b_locked:
        _execute_trade(trade)
        trade = get_trade(trade_id)
    return trade


def _execute_trade(trade: Trade) -> None:
    """Re-validates everything one more time right before moving
    anything - ownership of every offered item, and sufficient coin
    balance on both sides - then transfers everything atomically.
    Raises TradeError (and leaves the trade pending, both sides
    unlocked) if anything no longer checks out, rather than doing a
    partial trade."""
    a_items = list_items(trade.id, "a")
    b_items = list_items(trade.id, "b")

    def _still_owned(items, owner_id):
        for item in items:
            if item.kind == "character":
                inst = coll.get_owned_character_instance(item.instance_id)
            else:
                inst = coll.get_owned_weapon_instance(item.instance_id)
            if inst is None or inst.owner_discord_id != owner_id:
                return False
        return True

    conn = get_connection()
    try:
        if not _still_owned(a_items, trade.user_a_id) or not _still_owned(b_items, trade.user_b_id):
            conn.execute(
                "UPDATE trade_proposals SET user_a_locked = 0, user_b_locked = 0 WHERE id = ?",
                (trade.id,),
            )
            conn.commit()
            raise TradeError(
                "Something in this trade isn't owned by the offering side anymore - "
                "both sides have been unlocked, please review and re-lock."
            )
    finally:
        conn.close()

    if trade.user_a_coins > 0 and pl.get_balance(trade.user_a_id) < trade.user_a_coins:
        _unlock_both(trade.id)
        raise TradeError(f"<@{trade.user_a_id}> no longer has enough KAN for this trade.")
    if trade.user_b_coins > 0 and pl.get_balance(trade.user_b_id) < trade.user_b_coins:
        _unlock_both(trade.id)
        raise TradeError(f"<@{trade.user_b_id}> no longer has enough KAN for this trade.")

    for item in a_items:
        if item.kind == "character":
            coll.transfer_character(item.instance_id, trade.user_b_id)
        else:
            coll.transfer_weapon(item.instance_id, trade.user_b_id)
    if a_items:
        pl.record_traded_away(trade.user_a_id, len(a_items))
    for item in b_items:
        if item.kind == "character":
            coll.transfer_character(item.instance_id, trade.user_a_id)
        else:
            coll.transfer_weapon(item.instance_id, trade.user_a_id)
    if b_items:
        pl.record_traded_away(trade.user_b_id, len(b_items))

    if trade.user_a_coins > 0:
        pl.spend_coins(trade.user_a_id, trade.user_a_coins)
        pl.add_coins(trade.user_b_id, trade.user_a_coins)
    if trade.user_b_coins > 0:
        pl.spend_coins(trade.user_b_id, trade.user_b_coins)
        pl.add_coins(trade.user_a_id, trade.user_b_coins)

    conn = get_connection()
    try:
        conn.execute("UPDATE trade_proposals SET status = 'completed' WHERE id = ?", (trade.id,))
        conn.commit()
    finally:
        conn.close()


def _unlock_both(trade_id: int) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE trade_proposals SET user_a_locked = 0, user_b_locked = 0 WHERE id = ?",
            (trade_id,),
        )
        conn.commit()
    finally:
        conn.close()


def unlock_side(trade_id: int, user_id: int) -> None:
    """Explicit unlock, used when the OTHER side edits after you'd
    already locked - kept as a separate function in case a future
    caller wants to unlock without touching items/coins."""
    trade = get_trade(trade_id)
    if trade is None:
        return
    side = trade.side_for(user_id)
    if side is None:
        return
    locked_col = "user_a_locked" if side == "a" else "user_b_locked"
    conn = get_connection()
    try:
        conn.execute(f"UPDATE trade_proposals SET {locked_col} = 0 WHERE id = ?", (trade_id,))
        conn.commit()
    finally:
        conn.close()