"""
The merchant: every 3 hours, on the GMT+8 clock (00:00, 03:00, 06:00,
... 21:00), 6 random recipes go up from the fixed conversion menu
below - each shown as an exact, specific character to give up and an
exact, specific character you get back (not "any Common" - the
particular character pictured). Nothing is stored in the database;
everything for a given window is derived purely from the window's
own start time, so every shard/process/user sees the exact same 6
recipes (and the exact same two characters per recipe) without a
scheduler or a DB table, and it can't be regenerated early by asking
twice.
"""

import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from db.connection import get_connection, TIERS
from db.characters import Character, list_characters
from db.collection import grant_character


GMT8 = timezone(timedelta(hours=8))
WINDOW_HOURS = 3
OFFERS_PER_WINDOW = 6


class MerchantError(Exception):
    pass


@dataclass
class SpentCharacter:
    instance_id: int
    character_id: int
    name: str
    emoji: str


# ---------------------------------------------------------------------------
# the fixed conversion menu - (give_tier, give_qty, receive_tier, receive_qty)
# ---------------------------------------------------------------------------

_BUY_UP = [
    ("common", 3, "uncommon", 1), ("common", 5, "rare", 1), ("common", 10, "epic", 1),
    ("common", 15, "legendary", 1), ("common", 25, "mythic", 1),
    ("uncommon", 3, "rare", 1), ("uncommon", 5, "epic", 1), ("uncommon", 10, "legendary", 1),
    ("uncommon", 20, "mythic", 1),
    ("rare", 3, "epic", 1), ("rare", 9, "legendary", 1), ("rare", 18, "mythic", 1),
    ("epic", 5, "legendary", 1), ("epic", 15, "mythic", 1),
    ("legendary", 5, "mythic", 1),
]

_SELL_DOWN = [
    ("mythic", 1, "legendary", 2), ("mythic", 1, "epic", 4), ("mythic", 1, "rare", 6),
    ("mythic", 1, "uncommon", 8), ("mythic", 1, "common", 12),
    ("legendary", 1, "epic", 2), ("legendary", 1, "rare", 3), ("legendary", 1, "uncommon", 5),
    ("legendary", 1, "common", 10),
    ("epic", 1, "rare", 2), ("epic", 1, "uncommon", 4), ("epic", 1, "common", 8),
    ("rare", 1, "uncommon", 2), ("rare", 1, "common", 4),
    ("uncommon", 1, "common", 2),
]

RECIPES = _BUY_UP + _SELL_DOWN  # 30 total


# ---------------------------------------------------------------------------
# the rotating window
# ---------------------------------------------------------------------------

def _window_bounds_gmt8(now_utc: datetime) -> tuple[datetime, datetime]:
    now_gmt8 = now_utc.astimezone(GMT8)
    block_hour = (now_gmt8.hour // WINDOW_HOURS) * WINDOW_HOURS
    start_gmt8 = now_gmt8.replace(hour=block_hour, minute=0, second=0, microsecond=0)
    end_gmt8 = start_gmt8 + timedelta(hours=WINDOW_HOURS)
    return start_gmt8, end_gmt8


def get_window(now_utc: datetime | None = None):
    """Returns (start_utc, end_utc) for the exchange window `now_utc` falls in."""
    now_utc = now_utc or datetime.now(timezone.utc)
    start_gmt8, end_gmt8 = _window_bounds_gmt8(now_utc)
    return start_gmt8.astimezone(timezone.utc), end_gmt8.astimezone(timezone.utc)


def _characters_by_tier() -> dict[str, list[Character]]:
    by_tier: dict[str, list[Character]] = {t: [] for t in TIERS}
    for c in list_characters(enabled_only=True):
        if c.tier in by_tier:
            by_tier[c.tier].append(c)
    return by_tier


def _pick_character(rng: random.Random, pool: list[Character]) -> Character | None:
    """Prefers characters that actually have an emoji registered, so the
    board reliably shows one instead of silently falling back to plain
    text - but still picks something if none in the tier have one."""
    if not pool:
        return None
    with_emoji = [c for c in pool if c.emoji]
    return rng.choice(with_emoji) if with_emoji else rng.choice(pool)


def get_active_offers(now_utc: datetime | None = None) -> list[dict]:
    """
    This window's 6 offers, each a dict with the recipe's tiers/qtys
    AND the two specific Character objects picked for it:
      {give_tier, give_qty, give_character,
       receive_tier, receive_qty, receive_character}
    """
    start_utc, _ = get_window(now_utc)
    seed = int(start_utc.timestamp())
    rng = random.Random(seed)

    recipes = rng.sample(RECIPES, OFFERS_PER_WINDOW)
    by_tier = _characters_by_tier()

    offers = []
    for give_tier, give_qty, receive_tier, receive_qty in recipes:
        give_char = _pick_character(rng, by_tier.get(give_tier, []))
        receive_char = _pick_character(rng, by_tier.get(receive_tier, []))
        offers.append(
            {
                "give_tier": give_tier,
                "give_qty": give_qty,
                "give_character": give_char,
                "receive_tier": receive_tier,
                "receive_qty": receive_qty,
                "receive_character": receive_char,
            }
        )
    return offers


# ---------------------------------------------------------------------------
# carrying a trade out - by SPECIFIC character, not by tier
# ---------------------------------------------------------------------------

def consume_specific_character(discord_id: int, character_id: int, qty: int) -> list[SpentCharacter]:
    """Consumes exactly `qty` owned copies of one specific character."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT oc.id AS instance_id, c.id AS character_id, c.name AS name, c.emoji AS emoji
               FROM owned_characters oc
               JOIN characters c ON c.id = oc.character_id
               WHERE oc.owner_discord_id = ? AND c.id = ?
               ORDER BY oc.is_reiatsu ASC, oc.caught_at ASC""",
            (discord_id, character_id),
        ).fetchall()
    finally:
        conn.close()

    if len(rows) < qty:
        name = rows[0]["name"] if rows else None
        label = name or "that character"
        raise MerchantError(
            f"You need {qty}x {label} for that trade, but you only have {len(rows)}."
        )

    chosen = rows[:qty]
    spent = [
        SpentCharacter(r["instance_id"], r["character_id"], r["name"], r["emoji"])
        for r in chosen
    ]

    conn = get_connection()
    try:
        conn.executemany(
            "DELETE FROM owned_characters WHERE id = ? AND owner_discord_id = ?",
            [(s.instance_id, discord_id) for s in spent],
        )
        conn.commit()
    finally:
        conn.close()

    return spent


def grant_specific_character(discord_id: int, character_id: int, qty: int) -> None:
    # Merchant exchanges are a trade-in, not a catch/pull/craft, so they
    # never roll for Reiatsu (see reiatsu.py) - otherwise trading cards
    # back and forth would be a way to reroll the 10% chance.
    for _ in range(qty):
        grant_character(character_id, discord_id, roll_reiatsu_chance=False)