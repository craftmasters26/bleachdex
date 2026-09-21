"""
/shop - a 6-page daily shop.

  pages 1-5   one per faction (Soul Reaper, Vizard, Quincy, Hollow,
              Full Bringer): 6 random characters OR weapons of that faction
  page 6      6 random boss drops

The 6 items on every page change every 24 hours (at 00:00 UTC) and are the
same for every player. Nothing is bought "at random" any more - you see the
item and its price, then buy that exact item.

Prices
  characters / weapons   by tier: mythic 15,000 - legendary 10,000 - epic 7,500
                         - rare 5,000 - uncommon 2,500 - common 1,000
  boss drops             only the drops in SHOP_DROP_NAMES (the real crafting
                         drops - nothing else that bosses happen to hold).
                         BOSS_DROP_SPECIAL_PRICES gives a fixed price to
                         specific named drops (Almighty Eye / Soul King's
                         Heart: 30,000 each) - every other drop is
                         BOSS_DROP_PRICE (15,000)

Which faction a character/weapon is in comes from factions.py. Craftable-only
characters are never sold (you make those with /craft). Today's rotation is
stored in bot_settings under "shop_rotation", so it survives restarts and
doesn't change mid-day if you add characters.
"""

import json
import random
import time
from dataclasses import dataclass

from db import characters as ch, weapons as wp, players as pl, collection as coll, inventory as inv, bosses as bs
from db.connection import get_setting, set_setting
from factions import ADMIN_FACTION_CHOICES, faction_of

ITEMS_PER_PAGE = 6
ROTATION_SECONDS = 24 * 60 * 60

TIER_PRICES = {
    "mythic": 15_000,
    "legendary": 10_000,
    "epic": 7_500,
    "rare": 5_000,
    "uncommon": 2_500,
    "common": 1_000,
}

BOSS_DROP_PRICE = 15_000
RARE_DROP_MAX_RATE = 10.0   # percent - average drop rate at or below this = a "rarer" drop (display only)

# Fixed prices for specific boss drops, overriding BOSS_DROP_PRICE.
BOSS_DROP_SPECIAL_PRICES = {
    "Almighty Eye": 30_000,
    "Soul King's Heart": 30_000,
}

# The only items the boss-drop page ever sells: the drop pictures in the
# "Boss Drops" art folder. Recipes and boss drop tables use exactly these
# names (Almighty Eyes -> "Almighty Eye", Execution Badge -> "Xcution Badge").
SHOP_DROP_NAMES = frozenset({
    "Almighty Eye", "Bellflower", "Bird of Paradise", "Camellia", "Chrysanthemum",
    "Cross of Scaffold", "Daffodil", "Xcution Badge", "Hogyoku", "Hollow Mask",
    "Horn of Salvation", "Iris", "Jigokuchō", "Lily of the Valley", "Marigold",
    "Pasque Flower", "Quincy Cross", "Sanrei Glove", "Shin'eiyaku",
    "Shinigami Badge", "Snowdrop", "Soul King's Heart", "Thistle", "Vasto Lorde",
    "White Poppy", "Yarrow",
})

DROPS_PAGE = "drops"

# (page key, page title) in page order: the 5 factions, then boss drops.
PAGES = [(key, label) for label, key in ADMIN_FACTION_CHOICES] + [(DROPS_PAGE, "Boss Drops")]

_SETTING_KEY = "shop_rotation"


class PurchaseError(Exception):
    pass


@dataclass
class ShopItem:
    kind: str            # 'character' | 'weapon' | 'drop'
    name: str
    price: int
    item_id: int = 0     # characters.id / weapons.id (0 for drops)
    tier: str = ""       # characters / weapons only
    detail: str = ""     # e.g. "HP 1620 / ATK 1623", "+40% Damage", "Rare drop"
    emoji: str = ""      # characters / weapons: emoji id. drops: emoji_key
    is_rare_drop: bool = False


# ---------------------------------------------------------------------------
# prices
# ---------------------------------------------------------------------------

def price_for_tier(tier: str) -> int:
    return TIER_PRICES.get(tier, TIER_PRICES["common"])


def price_for_drop(name: str, avg_rate: float) -> int:
    return BOSS_DROP_SPECIAL_PRICES.get(name, BOSS_DROP_PRICE)


# ---------------------------------------------------------------------------
# pools
# ---------------------------------------------------------------------------

def _faction_pool(faction: str) -> list[tuple[str, int]]:
    """[(kind, id)] for every enabled, non-craftable character and every
    enabled weapon in `faction`."""
    pool = []
    for c in ch.list_characters(enabled_only=True):          # excludes craftable-only
        if faction_of(c.name) == faction:
            pool.append(("character", c.id))
    for w in wp.list_weapons(enabled_only=True):
        if faction_of(w.name) == faction:
            pool.append(("weapon", w.id))
    return sorted(pool)


def _drop_pool() -> dict[str, dict]:
    """{drop name: {'rate': average drop rate over the bosses that drop it,
    'emoji_key': ..., 'bosses': how many bosses drop it}} - only names in
    SHOP_DROP_NAMES, over every enabled preset boss."""
    seen: dict[str, dict] = {}
    for boss in bs.list_preset_bosses(enabled_only=True):
        for d in boss.drops:
            if d.item_name not in SHOP_DROP_NAMES:
                continue
            e = seen.setdefault(d.item_name, {"total": 0.0, "emoji_key": "", "bosses": 0})
            e["total"] += d.rate
            e["bosses"] += 1
            if not e["emoji_key"] and d.emoji_key:
                e["emoji_key"] = d.emoji_key
    return {name: {"rate": e["total"] / e["bosses"], "emoji_key": e["emoji_key"], "bosses": e["bosses"]}
            for name, e in seen.items()}


# ---------------------------------------------------------------------------
# the daily rotation
# ---------------------------------------------------------------------------

def current_day() -> int:
    return int(time.time() // ROTATION_SECONDS)


def next_rotation_at() -> int:
    """Unix time of the next 00:00 UTC."""
    return (current_day() + 1) * ROTATION_SECONDS


def _generate(day: int) -> dict:
    pages: dict[str, list[dict]] = {}
    for key, _label in PAGES:
        rng = random.Random(f"bleachdex-shop:{day}:{key}")   # same picks for everyone
        if key == DROPS_PAGE:
            names = sorted(_drop_pool())
            picked = rng.sample(names, min(ITEMS_PER_PAGE, len(names)))
            pages[key] = [{"k": "drop", "name": n} for n in picked]
        else:
            pool = _faction_pool(key)
            picked = rng.sample(pool, min(ITEMS_PER_PAGE, len(pool)))
            pages[key] = [{"k": kind, "id": item_id} for kind, item_id in picked]
    return {"day": day, "pages": pages}


def get_rotation() -> dict:
    """Today's rotation, generating (and saving) it if it's a new day."""
    day = current_day()
    raw = get_setting(_SETTING_KEY, "")
    if raw:
        try:
            data = json.loads(raw)
            if data.get("day") == day and isinstance(data.get("pages"), dict):
                # A rotation rolled before SHOP_DROP_NAMES changed can hold a drop
                # that is no longer sold - throw it away and roll a fresh one.
                stale = any(ref.get("k") == "drop" and ref.get("name") not in SHOP_DROP_NAMES
                            for ref in data["pages"].get(DROPS_PAGE, []))
                if not stale:
                    return data
        except (ValueError, AttributeError):
            pass
    data = _generate(day)
    set_setting(_SETTING_KEY, json.dumps(data))
    return data


def force_new_rotation() -> None:
    """Throws today's rotation away so the next /shop builds a fresh one
    (it will roll the same items again unless the pools changed, since the
    picks are seeded by the date)."""
    set_setting(_SETTING_KEY, "")


def _resolve(ref: dict, drop_pool: dict | None) -> ShopItem | None:
    kind = ref.get("k")
    if kind == "character":
        c = ch.get_character(ref.get("id", 0))
        if c is None or not c.enabled or c.craftable_only:
            return None
        return ShopItem("character", c.name, price_for_tier(c.tier), c.id, c.tier,
                        f"HP {c.hp:,} / ATK {c.attack:,}", c.emoji)
    if kind == "weapon":
        w = wp.get_weapon(ref.get("id", 0))
        if w is None or not w.enabled:
            return None
        stat = "HP" if w.boost_type == "hp" else "Damage"
        return ShopItem("weapon", w.name, price_for_tier(w.tier), w.id, w.tier,
                        f"+{w.boost_percent}% {stat}", w.emoji)
    if kind == "drop":
        info = (drop_pool or {}).get(ref.get("name", ""))
        if info is None:
            return None
        rare = info["rate"] <= RARE_DROP_MAX_RATE
        return ShopItem("drop", ref["name"], price_for_drop(ref["name"], info["rate"]), 0, "",
                        "Rare boss drop" if rare else "Boss drop", info["emoji_key"], rare)
    return None


def get_page_items(page_key: str) -> list[ShopItem]:
    """The (up to) 6 items on one page today. Anything that has since been
    disabled/removed is simply left out."""
    refs = get_rotation()["pages"].get(page_key, [])
    drop_pool = _drop_pool() if page_key == DROPS_PAGE else None
    return [item for item in (_resolve(r, drop_pool) for r in refs) if item is not None]


# ---------------------------------------------------------------------------
# buying
# ---------------------------------------------------------------------------

def buy(buyer_discord_id: int, page_key: str, slot: int, expected_name: str | None = None) -> tuple[ShopItem, int]:
    """Buys item number `slot` (0-5) of `page_key`'s page as it is right now.
    `expected_name` is the item the player was looking at: if the shop has
    rotated since (so that slot now holds something else) nothing is bought.
    Returns (item, owned instance id or 0 for a drop). Raises PurchaseError
    with a player-readable message on any problem; coins are only kept if the
    item was actually granted."""
    items = get_page_items(page_key)
    if not 0 <= slot < len(items) or (expected_name is not None and items[slot].name != expected_name):
        raise PurchaseError("The shop just refreshed, so that item is gone. Open `/shop` again to see today's items.")
    item = items[slot]

    if not pl.spend_coins(buyer_discord_id, item.price):
        balance = pl.get_balance(buyer_discord_id)
        raise PurchaseError(f"**{item.name}** costs {item.price:,} KAN but you only have {balance:,}. Try `/daily`.")

    try:
        if item.kind == "character":
            instance_id = coll.grant_character(item.item_id, buyer_discord_id)
        elif item.kind == "weapon":
            instance_id = coll.grant_weapon(item.item_id, buyer_discord_id)
        else:
            inv.add(buyer_discord_id, item.name, 1)
            instance_id = 0
    except Exception:
        pl.add_coins(buyer_discord_id, item.price)      # never keep the coins if nothing was granted
        raise PurchaseError("Something went wrong while granting that item - you were not charged.")
    return item, instance_id