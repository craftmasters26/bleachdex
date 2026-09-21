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
    boost_type TEXT NOT NULL DEFAULT 'damage',   -- 'damage' or 'hp' - which stat this weapon's % applies to
    boost_percent INTEGER NOT NULL DEFAULT 0,    -- e.g. 40 means +40%, applied multiplicatively in battle
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
    caught_at INTEGER NOT NULL,
    is_reiatsu INTEGER NOT NULL DEFAULT 0   -- 1 = awakened Reiatsu copy, see reiatsu.py
);

CREATE TABLE IF NOT EXISTS owned_weapons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    weapon_id INTEGER NOT NULL REFERENCES weapons(id),
    owner_discord_id INTEGER NOT NULL,
    attack_bonus INTEGER NOT NULL,
    boost_type TEXT NOT NULL DEFAULT 'damage',
    boost_percent INTEGER NOT NULL DEFAULT 0,
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

-- The table above (`trades`) is dead - nothing in the code queries it.
-- db/trade.py (the actual trade system) uses these two instead. They
-- were missing from this schema entirely, which is why every /trade
-- command failed with "no such table: trade_proposals".
CREATE TABLE IF NOT EXISTS trade_proposals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id INTEGER,
    message_id INTEGER,
    user_a_id INTEGER NOT NULL,
    user_b_id INTEGER NOT NULL,
    user_a_coins INTEGER NOT NULL DEFAULT 0,
    user_b_coins INTEGER NOT NULL DEFAULT 0,
    user_a_locked INTEGER NOT NULL DEFAULT 0,
    user_b_locked INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending',  -- pending / completed / cancelled / expired
    created_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS trade_proposal_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id INTEGER NOT NULL REFERENCES trade_proposals(id),
    side TEXT NOT NULL,   -- 'a' or 'b'
    kind TEXT NOT NULL,   -- 'character' or 'weapon'
    instance_id INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_trade_items_trade_id ON trade_proposal_items(trade_id);

-- Dead as of the multi-preset /team update below - nothing in the code
-- queries this table anymore (see db/teams.py's one-time migration into
-- team_presets, preset 1). Left in place so an old DB file doesn't lose
-- the rows before that migration runs on next startup.
CREATE TABLE IF NOT EXISTS teams (
    owner_discord_id INTEGER NOT NULL,
    slot INTEGER NOT NULL CHECK (slot IN (1, 2, 3)),
    character_instance_id INTEGER NOT NULL REFERENCES owned_characters(id),
    PRIMARY KEY (owner_discord_id, slot)
);

-- Each player can keep up to 2 saved teams ("presets"), each with its
-- own 3 slots - e.g. a boss-battle team and a separate PvP team. See
-- db/teams.py.
CREATE TABLE IF NOT EXISTS team_presets (
    owner_discord_id INTEGER NOT NULL,
    preset INTEGER NOT NULL CHECK (preset IN (1, 2)),
    slot INTEGER NOT NULL CHECK (slot IN (1, 2, 3)),
    character_instance_id INTEGER NOT NULL REFERENCES owned_characters(id),
    PRIMARY KEY (owner_discord_id, preset, slot)
);

-- Which of the 2 presets is "active" for a player - this is the one
-- /battle and /admin bossbattle's Challenge button actually read via
-- teams.get_team(discord_id) with no explicit preset argument.
CREATE TABLE IF NOT EXISTS team_active_preset (
    owner_discord_id INTEGER PRIMARY KEY,
    preset INTEGER NOT NULL DEFAULT 1
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

-- Generic per-player counters for achievements that don't have an
-- existing table to read from (e.g. "beat the server owner in a
-- battle", "traded with an admin"). See db/player_stats.py.
CREATE TABLE IF NOT EXISTS player_stats (
    discord_id INTEGER NOT NULL,
    stat_key TEXT NOT NULL,
    value INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (discord_id, stat_key)
);

-- Boss battles. See db/bosses.py.
CREATE TABLE IF NOT EXISTS bosses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    image_path TEXT NOT NULL DEFAULT '',
    max_hp INTEGER NOT NULL DEFAULT 1000,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS boss_drops (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    boss_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    stock INTEGER,              -- NULL = unlimited, otherwise decrements as claimed
    emoji_key TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS active_boss_battles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id INTEGER NOT NULL UNIQUE,   -- one active fight per channel at a time
    boss_id INTEGER NOT NULL,
    current_hp INTEGER NOT NULL,
    message_id INTEGER,
    started_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS boss_battle_participants (
    battle_id INTEGER NOT NULL,
    discord_id INTEGER NOT NULL,
    damage_dealt INTEGER NOT NULL DEFAULT 0,
    last_attack_at INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (battle_id, discord_id)
);

-- What players actually HOLD from boss drops - resolve_defeat() in
-- db/bosses.py only decides/announces who gets what; this table is
-- the actual inventory that /craft spends from. See db/inventory.py.
CREATE TABLE IF NOT EXISTS owned_boss_drops (
    discord_id INTEGER NOT NULL,
    drop_name TEXT NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (discord_id, drop_name)
);

-- Solo "/admin bossbattle" fights - separate feature from the co-op
-- bosses table above (now unused - see db/bosses.py). Each row is one
-- preset boss with its own HP/damage stats and up to two
-- independently-rolled drops (a player can get neither, either, or
-- both on a win - unlike the shared-pool single-draw drops in
-- boss_drops). See seed_bossbattle.py. Drops are credited into the
-- existing owned_boss_drops table above, so /craft spends them the
-- same way regardless of which boss system handed them out.
CREATE TABLE IF NOT EXISTS bossbattle_bosses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL UNIQUE,
    image_path TEXT NOT NULL DEFAULT '',
    max_hp INTEGER NOT NULL,
    dmg_per_round INTEGER NOT NULL,
    drop1_name TEXT NOT NULL DEFAULT '',
    drop1_rate REAL NOT NULL DEFAULT 0,
    drop1_emoji_key TEXT NOT NULL DEFAULT '',
    drop2_name TEXT NOT NULL DEFAULT '',
    drop2_rate REAL NOT NULL DEFAULT 0,
    drop2_emoji_key TEXT NOT NULL DEFAULT '',
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at INTEGER NOT NULL
);

-- Unlimited per-boss drops (replaces the old fixed drop1/2/3 columns
-- above, which are kept in place for backward compat but no longer
-- read/written - see db/bosses.py). Each boss can have any number of
-- independently-rolled drops now (some crafting bosses have 10+).
CREATE TABLE IF NOT EXISTS bossbattle_drops (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    boss_id INTEGER NOT NULL REFERENCES bossbattle_bosses(id) ON DELETE CASCADE,
    item_name TEXT NOT NULL,
    rate REAL NOT NULL DEFAULT 0,
    emoji_key TEXT NOT NULL DEFAULT '',
    sort_order INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_bossbattle_drops_boss ON bossbattle_drops(boss_id);

-- Craftable characters - see db/craftables.py. A craftable is a
-- normal row in the `characters` table (craftable_only = 1 there,
-- see the ALTER TABLE below) so it works everywhere a normal
-- character does (collection, equip, battle, trade) once someone
-- owns one - it just can never come from a pack or a wild spawn,
-- and has exactly one crafting recipe here.
CREATE TABLE IF NOT EXISTS craft_recipes (
    character_id INTEGER PRIMARY KEY,
    required_drop_name TEXT NOT NULL,
    required_drop_qty INTEGER NOT NULL
);

-- Multi-ingredient recipes (db/craftables.py). One row per ingredient
-- of a craftable. kind says where the player's copy comes from:
--   'drop'      -> owned_boss_drops, matched by item_name
--   'weapon'    -> owned_weapons, matched by the weapon's name
--   'character' -> owned_characters, matched by the character's name
--                  (this is also how "previous form" ingredients work,
--                  since every craftable is itself a characters row)
-- craft_recipes above is only read as a fallback for old single-drop
-- recipes that have no rows here.
CREATE TABLE IF NOT EXISTS craft_ingredients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    character_id INTEGER NOT NULL REFERENCES characters(id),
    kind TEXT NOT NULL,
    item_name TEXT NOT NULL,
    qty INTEGER NOT NULL DEFAULT 1,
    sort_order INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_craft_ing_char ON craft_ingredients(character_id);
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
    # Message-count-based spawn gating (db/spawns.py's record_message()/
    # reset_after_spawn()) needs this column but it was never added to
    # the schema, causing "OperationalError: table guild_settings has
    # no column named message_count_since_spawn" the moment anyone
    # sends a message in a configured spawn channel.
    "ALTER TABLE guild_settings ADD COLUMN message_count_since_spawn INTEGER NOT NULL DEFAULT 0",
    # Lifetime count of items given away in completed trades - db/trade.py's
    # _execute_trade() calls record_traded_away(), which needs this
    # column. Missing entirely from this schema, which is the second
    # reason every /trade would fail (after fixing the missing tables).
    "ALTER TABLE players ADD COLUMN traded_away_count INTEGER NOT NULL DEFAULT 0",
    # Marks a character as craft-only (db/craftables.py) - it's a
    # normal row in `characters` otherwise (so collection/equip/
    # battle/trade all already work with it once someone owns one),
    # this just needs to be excluded from the normal pack/spawn pool.
    # See list_characters()'s new exclude_craftable_only param in
    # db/characters.py.
    "ALTER TABLE characters ADD COLUMN craftable_only INTEGER NOT NULL DEFAULT 0",
    # Weapons switched from a flat attack_bonus number to a percentage
    # boost to EITHER hp or damage (per your Character_list.txt spec:
    # "Boost Type: HP or Damage", "Boost %"). attack_bonus is kept in
    # place rather than dropped (SQLite can't cheaply drop columns) but
    # is no longer read anywhere - see db/weapons.py and cogs/battle.py.
    "ALTER TABLE weapons ADD COLUMN boost_type TEXT NOT NULL DEFAULT 'damage'",
    "ALTER TABLE weapons ADD COLUMN boost_percent INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE owned_weapons ADD COLUMN boost_type TEXT NOT NULL DEFAULT 'damage'",
    "ALTER TABLE owned_weapons ADD COLUMN boost_percent INTEGER NOT NULL DEFAULT 0",
    # Hourly auto boss-spawn (GMT+8) - see cogs/boss.py's hourly_boss_spawn
    # task loop and db/bosses.py's list_hourly_spawn_targets(). Reuses
    # the same spawn_channel_id as regular Soul spawns, so there's no
    # separate boss channel to configure - last_boss_spawn_hour_key just
    # records the last GMT+8 hour ('YYYY-MM-DD HH') a boss was spawned
    # for this guild, so a bot restart mid-hour can't double-spawn.
    "ALTER TABLE guild_settings ADD COLUMN last_boss_spawn_hour_key TEXT DEFAULT ''",
    # Third drop slot for bossbattle bosses - Soul Reaper Captains
    # (Bankai item + flower + Jigokucho) and the crafting-material
    # bosses each have three separate drop rolls.
    "ALTER TABLE bossbattle_bosses ADD COLUMN drop3_name TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE bossbattle_bosses ADD COLUMN drop3_rate REAL NOT NULL DEFAULT 0",
    "ALTER TABLE bossbattle_bosses ADD COLUMN drop3_emoji_key TEXT NOT NULL DEFAULT ''",
    # Which /craft category a craftable character is listed under
    # (Aizen, Espada Resurreccion, Soul Reaper Captains, ...).
    "ALTER TABLE characters ADD COLUMN craft_category TEXT NOT NULL DEFAULT ''",
    # Reiatsu - a 10% chance on every character added to a collection
    # that this particular COPY is an awakened Reiatsu copy (+20% damage,
    # +10% HP in battle, different card). Per-copy, not per-character:
    # see reiatsu.py.
    "ALTER TABLE owned_characters ADD COLUMN is_reiatsu INTEGER NOT NULL DEFAULT 0",
    # catch_log remembers whether each catch was a Reiatsu copy, so the
    # "Obtain N Reiatsu Infused souls" achievements survive trading the copy
    # away. Older rows default to 0 (the achievement also counts Reiatsu
    # copies currently owned, so nobody loses progress).
    "ALTER TABLE catch_log ADD COLUMN is_reiatsu INTEGER NOT NULL DEFAULT 0",
    # Main Catcher looks up "has this player ever caught in the main server".
    "CREATE INDEX IF NOT EXISTS idx_active_spawns_caught_by ON active_spawns(caught_by)",
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