"""
/shop — 2 characters + 2 weapons, re-rolled every 24 hours. Prices
scale with tier so a Mythic pull isn't the same price as a Common one.
"""

import random
import time
from dataclasses import dataclass
from typing import Optional

from db.connection import get_connection, TIER_WEIGHTS
from db import characters as ch, weapons as wp, players as pl, collection as coll

SHOP_ROTATION_SECONDS = 24 * 60 * 60

# Cheaper for common tiers, pricier for rare ones - roughly inverse of
# pull weight so a hard-to-pull tier costs meaningfully more.
TIER_PRICES = {
    "common": 40,
    "uncommon": 80,
    "rare": 150,
    "epic": 300,
    "legendary": 600,
    "mythic": 1500,
}


@dataclass
class ShopSlot:
    slot: int
    kind: str  # 'character' or 'weapon'
    item_id: int
    price: int


def _price_for(tier: str) -> int:
    return TIER_PRICES.get(tier, 100)


def _generate_new_shop() -> list[ShopSlot]:
    all_characters = ch.list_characters(enabled_only=True)
    all_weapons = wp.list_weapons(enabled_only=True)

    slots: list[ShopSlot] = []
    chosen_characters = random.sample(all_characters, k=min(2, len(all_characters)))
    for i, c in enumerate(chosen_characters, start=1):
        slots.append(ShopSlot(slot=i, kind="character", item_id=c.id, price=_price_for(c.tier)))

    chosen_weapons = random.sample(all_weapons, k=min(2, len(all_weapons)))
    for i, w in enumerate(chosen_weapons, start=3):
        slots.append(ShopSlot(slot=i, kind="weapon", item_id=w.id, price=_price_for(w.tier)))

    conn = get_connection()
    try:
        values = {"generated_at": int(time.time())}
        for s in slots:
            values[f"slot{s.slot}_kind"] = s.kind
            values[f"slot{s.slot}_id"] = s.item_id
            values[f"slot{s.slot}_price"] = s.price
        for i in range(1, 5):
            values.setdefault(f"slot{i}_kind", None)
            values.setdefault(f"slot{i}_id", None)
            values.setdefault(f"slot{i}_price", None)

        conn.execute(
            """INSERT INTO shop_state
               (id, generated_at, slot1_kind, slot1_id, slot1_price,
                slot2_kind, slot2_id, slot2_price,
                slot3_kind, slot3_id, slot3_price,
                slot4_kind, slot4_id, slot4_price)
               VALUES (1, :generated_at, :slot1_kind, :slot1_id, :slot1_price,
                       :slot2_kind, :slot2_id, :slot2_price,
                       :slot3_kind, :slot3_id, :slot3_price,
                       :slot4_kind, :slot4_id, :slot4_price)
               ON CONFLICT(id) DO UPDATE SET
                 generated_at=excluded.generated_at,
                 slot1_kind=excluded.slot1_kind, slot1_id=excluded.slot1_id, slot1_price=excluded.slot1_price,
                 slot2_kind=excluded.slot2_kind, slot2_id=excluded.slot2_id, slot2_price=excluded.slot2_price,
                 slot3_kind=excluded.slot3_kind, slot3_id=excluded.slot3_id, slot3_price=excluded.slot3_price,
                 slot4_kind=excluded.slot4_kind, slot4_id=excluded.slot4_id, slot4_price=excluded.slot4_price
            """,
            values,
        )
        conn.commit()
    finally:
        conn.close()

    return slots


def get_current_shop() -> list[ShopSlot]:
    """Returns the current shop, generating a fresh one if none exists
    yet or if the last one is more than 24h old."""
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM shop_state WHERE id = 1").fetchone()
    finally:
        conn.close()

    now = int(time.time())
    if row is None or (now - row["generated_at"]) >= SHOP_ROTATION_SECONDS:
        return _generate_new_shop()

    slots = []
    for i in range(1, 5):
        kind = row[f"slot{i}_kind"]
        if kind is None:
            continue
        slots.append(ShopSlot(slot=i, kind=kind, item_id=row[f"slot{i}_id"], price=row[f"slot{i}_price"]))
    return slots


def seconds_until_rotation() -> int:
    conn = get_connection()
    try:
        row = conn.execute("SELECT generated_at FROM shop_state WHERE id = 1").fetchone()
    finally:
        conn.close()
    if row is None:
        return 0
    elapsed = int(time.time()) - row["generated_at"]
    return max(0, SHOP_ROTATION_SECONDS - elapsed)


class PurchaseError(Exception):
    pass


def buy_slot(buyer_discord_id: int, slot_number: int) -> ShopSlot:
    slots = get_current_shop()
    slot = next((s for s in slots if s.slot == slot_number), None)
    if slot is None:
        raise PurchaseError("That shop slot is empty or the shop hasn't rolled yet.")

    if not pl.spend_coins(buyer_discord_id, slot.price):
        balance = pl.get_balance(buyer_discord_id)
        raise PurchaseError(
            f"You need {slot.price} KAN but only have {balance}. Come back after `/daily`."
        )

    if slot.kind == "character":
        coll.grant_character(slot.item_id, buyer_discord_id)
    else:
        coll.grant_weapon(slot.item_id, buyer_discord_id)
    return slot
