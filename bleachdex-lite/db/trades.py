"""
Trades: user A offers one of their items, user B offers one of theirs.
BOTH must explicitly accept before anything actually moves. Either can
cancel any time before it completes.
"""

import json
import time
from dataclasses import dataclass
from typing import Optional

from db.connection import get_connection
from db import collection as coll


@dataclass
class Trade:
    id: int
    user_a_id: int
    user_b_id: int
    user_a_offer: dict
    user_b_offer: dict
    user_a_accepted: bool
    user_b_accepted: bool
    status: str
    created_at: int

    @classmethod
    def from_row(cls, row) -> "Trade":
        data = dict(row)
        data["user_a_offer"] = json.loads(data["user_a_offer"])
        data["user_b_offer"] = json.loads(data["user_b_offer"])
        data["user_a_accepted"] = bool(data["user_a_accepted"])
        data["user_b_accepted"] = bool(data["user_b_accepted"])
        return cls(**data)


class TradeError(Exception):
    pass


def _validate_ownership(offer: dict, owner_id: int) -> None:
    kind, instance_id = offer["kind"], offer["instance_id"]
    if kind == "character":
        inst = coll.get_owned_character_instance(instance_id)
    elif kind == "weapon":
        inst = coll.get_owned_weapon_instance(instance_id)
    else:
        raise TradeError(f"Unknown item kind: {kind}")
    if inst is None or inst.owner_discord_id != owner_id:
        raise TradeError("You don't own that item.")


def create_trade(user_a_id: int, user_a_offer: dict, user_b_id: int, user_b_offer: dict) -> int:
    """
    offer dicts look like: {"kind": "character", "instance_id": 5}
    Neither side is auto-accepted - both must accept explicitly, even
    the person who ran the command, so a trade can't complete on a
    single button click.
    """
    if user_a_id == user_b_id:
        raise TradeError("You can't trade with yourself.")
    _validate_ownership(user_a_offer, user_a_id)
    _validate_ownership(user_b_offer, user_b_id)

    conn = get_connection()
    try:
        cur = conn.execute(
            """INSERT INTO trades
               (user_a_id, user_b_id, user_a_offer, user_b_offer,
                user_a_accepted, user_b_accepted, status, created_at)
               VALUES (?, ?, ?, ?, 0, 0, 'pending', ?)""",
            (user_a_id, user_b_id, json.dumps(user_a_offer), json.dumps(user_b_offer),
             int(time.time())),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_trade(trade_id: int) -> Optional[Trade]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM trades WHERE id = ?", (trade_id,)).fetchone()
        return Trade.from_row(row) if row else None
    finally:
        conn.close()


def accept_trade(trade_id: int, user_id: int) -> Trade:
    """
    Marks this user's side as accepted. If both sides are now
    accepted, executes the transfer atomically and marks completed.
    Returns the updated Trade.
    """
    trade = get_trade(trade_id)
    if trade is None:
        raise TradeError("Trade not found.")
    if trade.status != "pending":
        raise TradeError(f"This trade is already {trade.status}.")
    if user_id not in (trade.user_a_id, trade.user_b_id):
        raise TradeError("You're not part of this trade.")

    # Re-validate ownership at accept time too - items may have moved
    # (traded away, etc.) since the trade was proposed.
    _validate_ownership(trade.user_a_offer, trade.user_a_id)
    _validate_ownership(trade.user_b_offer, trade.user_b_id)

    conn = get_connection()
    try:
        column = "user_a_accepted" if user_id == trade.user_a_id else "user_b_accepted"
        conn.execute(f"UPDATE trades SET {column} = 1 WHERE id = ?", (trade_id,))
        conn.commit()
    finally:
        conn.close()

    trade = get_trade(trade_id)
    if trade.user_a_accepted and trade.user_b_accepted:
        _execute_transfer(trade)
        conn = get_connection()
        try:
            conn.execute("UPDATE trades SET status = 'completed' WHERE id = ?", (trade_id,))
            conn.commit()
        finally:
            conn.close()
        trade = get_trade(trade_id)

    return trade


def cancel_trade(trade_id: int, user_id: int) -> Trade:
    trade = get_trade(trade_id)
    if trade is None:
        raise TradeError("Trade not found.")
    if trade.status != "pending":
        raise TradeError(f"This trade is already {trade.status}.")
    if user_id not in (trade.user_a_id, trade.user_b_id):
        raise TradeError("You're not part of this trade.")

    conn = get_connection()
    try:
        conn.execute("UPDATE trades SET status = 'cancelled' WHERE id = ?", (trade_id,))
        conn.commit()
    finally:
        conn.close()
    return get_trade(trade_id)


def _execute_transfer(trade: Trade) -> None:
    a_kind, a_id = trade.user_a_offer["kind"], trade.user_a_offer["instance_id"]
    b_kind, b_id = trade.user_b_offer["kind"], trade.user_b_offer["instance_id"]

    if a_kind == "character":
        coll.transfer_character(a_id, trade.user_b_id)
    else:
        coll.transfer_weapon(a_id, trade.user_b_id)

    if b_kind == "character":
        coll.transfer_character(b_id, trade.user_a_id)
    else:
        coll.transfer_weapon(b_id, trade.user_a_id)
