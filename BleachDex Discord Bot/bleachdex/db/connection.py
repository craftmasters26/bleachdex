"""
Shared SQLite connection + full schema for BleachDex-Lite.

Everything lives in one file (db/bleachdex.sqlite3). Tiers control both
pull rarity odds and weekly-pack guarantees:

    common < uncommon < rare < epic < legendary < mythic   (mythic is hardest to pull)
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "bleachdex.sqlite3"

TIERS = ["common", "uncommon", "rare", "epic", "legendary", "mythic"]
# Relative pull weight per tier - higher = more likely. Mythic is
# deliberately far below the others.
TIER_WEIGHTS = {
    "common": 1000,
    "uncommon": 500,
    "rare": 200,
    "epic": 60,
    "legendary": 20,
    "mythic": 5,
}
# KAN coins granted for catching a Soul of each tier (spawns only).
TIER_COIN_REWARDS = {
    "common": 300,
    "uncommon": 600,
    "rare": 800,
    "epic": 1000,
    "legendary": 1250,
    "mythic": 1500,
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS characters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    position TEXT NOT NULL DEFAULT '',
    image_path TEXT NOT NULL,
    hp INTEGER NOT NULL,
    attack INTEGER NOT NULL,
    tier TEXT NOT NULL DEFAULT 'common',
    rarity INTEGER NOT NULL DEFAULT 100,
    ability_name TEXT DEFAULT '',
    ability_description TEXT DEFAULT '',
    emoji TEXT DEFAULT '',
    card_template_path TEXT DEFAULT '',
    card_image_path TEXT DEFAULT '',
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS weapons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    position TEXT NOT NULL DEFAULT '',
    image_path TEXT NOT NULL,
    attack_bonus INTEGER NOT NULL DEFAULT 0,
    tier TEXT NOT NULL DEFAULT 'common',
    rarity INTEGER NOT NULL DEFAULT 100,
    ability_name TEXT DEFAULT '',
    ability_description TEXT DEFAULT '',
    emoji TEXT DEFAULT '',
    card_template_path TEXT DEFAULT '',
    card_image_path TEXT DEFAULT '',
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS players (
    discord_id INTEGER PRIMARY KEY,
    kan_coins INTEGER NOT NULL DEFAULT 0,
    last_daily_coin_claim INTEGER DEFAULT 0,
    last_weekly_pack_claim INTEGER DEFAULT 0,
    daily_pack_date TEXT DEFAULT '',
    daily_pack_pulls_used INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS owned_characters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    character_id INTEGER NOT NULL REFERENCES characters(id),
    owner_discord_id INTEGER NOT NULL,
    health INTEGER NOT NULL,
    attack INTEGER NOT NULL,
    equipped_weapon_instance_id INTEGER DEFAULT NULL,
    caught_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS owned_weapons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    weapon_id INTEGER NOT NULL REFERENCES weapons(id),
    owner_discord_id INTEGER NOT NULL,
    attack_bonus INTEGER NOT NULL,
    caught_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_owned_char_owner ON owned_characters(owner_discord_id);
CREATE INDEX IF NOT EXISTS idx_owned_weapon_owner ON owned_weapons(owner_discord_id);

CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_a_id INTEGER NOT NULL,
    user_b_id INTEGER NOT NULL,
    user_a_offer TEXT NOT NULL,   -- JSON: {"kind": "character"/"weapon", "instance_id": N}
    user_b_offer TEXT NOT NULL,
    user_a_accepted INTEGER NOT NULL DEFAULT 0,
    user_b_accepted INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending',  -- pending / completed / cancelled
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS teams (
    owner_discord_id INTEGER NOT NULL,
    slot INTEGER NOT NULL CHECK (slot IN (1, 2, 3)),
    character_instance_id INTEGER NOT NULL REFERENCES owned_characters(id),
    PRIMARY KEY (owner_discord_id, slot)
);

CREATE TABLE IF NOT EXISTS guild_settings (
    guild_id INTEGER PRIMARY KEY,
    spawn_channel_id INTEGER,
    channel_has_activity INTEGER NOT NULL DEFAULT 0,
    last_spawn_at INTEGER DEFAULT 0,
    next_check_at INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS active_spawns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    message_id INTEGER,
    kind TEXT NOT NULL,              -- 'character' or 'weapon'
    collectible_id INTEGER NOT NULL,
    caught_by INTEGER,
    spawned_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS shop_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    generated_at INTEGER NOT NULL,
    slot1_kind TEXT, slot1_id INTEGER, slot1_price INTEGER,
    slot2_kind TEXT, slot2_id INTEGER, slot2_price INTEGER,
    slot3_kind TEXT, slot3_id INTEGER, slot3_price INTEGER,
    slot4_kind TEXT, slot4_id INTEGER, slot4_price INTEGER
);

CREATE TABLE IF NOT EXISTS bot_settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS player_achievements (
    discord_id INTEGER NOT NULL,
    achievement_key TEXT NOT NULL,
    earned_at INTEGER NOT NULL,
    PRIMARY KEY (discord_id, achievement_key)
);
"""

# Columns added after the initial release. SQLite's CREATE TABLE IF NOT
# EXISTS won't retrofit these onto a database that already exists, so we
# add them by hand and just ignore "duplicate column" errors on DBs that
# already have them (or were freshly created with SCHEMA above, which
# already includes them).
_MIGRATIONS = [
    "ALTER TABLE characters ADD COLUMN card_template_path TEXT DEFAULT ''",
    "ALTER TABLE weapons ADD COLUMN card_template_path TEXT DEFAULT ''",
    "ALTER TABLE weapons ADD COLUMN ability_name TEXT DEFAULT ''",
    "ALTER TABLE weapons ADD COLUMN ability_description TEXT DEFAULT ''",
    # card_image_path is the artwork shown INSIDE the rendered stat card
    # (/pack daily reveal, /card view). It's separate from image_path,
    # which is the plain image shown when the thing SPAWNS in the wild -
    # /edit card only ever touches card_image_path, never image_path.
    "ALTER TABLE characters ADD COLUMN card_image_path TEXT DEFAULT ''",
    "ALTER TABLE weapons ADD COLUMN card_image_path TEXT DEFAULT ''",
    "ALTER TABLE players ADD COLUMN battle_wins INTEGER NOT NULL DEFAULT 0",
    # Win-streak tracking for the "Undefeated"/"Consecutive Kills"
    # achievements - current_win_streak resets to 0 on a loss;
    # best_win_streak only ever goes up, so an achievement earned from
    # a past streak is never revoked just because a later battle is lost.
    "ALTER TABLE players ADD COLUMN current_win_streak INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE players ADD COLUMN best_win_streak INTEGER NOT NULL DEFAULT 0",
]

# Permanent record of every catch (pack pull, spawn catch, or shop
# purchase - anything that calls grant_character/grant_weapon in
# db/collection.py). Unlike owned_characters/owned_weapons, rows here
# are NEVER deleted or moved on a trade - this is what "catch count"
# achievements (Soul Collector, Hollow Hunter, etc.) read from, so
# trading something away doesn't undo credit for having caught it.
_CATCH_LOG_SCHEMA = """
CREATE TABLE IF NOT EXISTS catch_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    discord_id INTEGER NOT NULL,
    kind TEXT NOT NULL,          -- 'character' or 'weapon'
    item_id INTEGER NOT NULL,    -- characters.id or weapons.id, depending on kind
    caught_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_catch_log_discord_id ON catch_log(discord_id);
"""


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    conn = get_connection()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
        conn.executescript(_CATCH_LOG_SCHEMA)
        conn.commit()
        for stmt in _MIGRATIONS:
            try:
                conn.execute(stmt)
                conn.commit()
            except sqlite3.OperationalError:
                pass  # column already exists
    finally:
        conn.close()


def get_setting(key: str, default: str = "") -> str:
    conn = get_connection()
    try:
        row = conn.execute("SELECT value FROM bot_settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default
    finally:
        conn.close()


def set_setting(key: str, value: str) -> None:
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO bot_settings (key, value) VALUES (?, ?)
               ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
            (key, value),
        )
        conn.commit()
    finally:
        conn.close()