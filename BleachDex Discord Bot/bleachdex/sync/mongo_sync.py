"""
bot-sync/mongo_sync.py

Live one-way bridge: SQLite (the bot's real source of truth) -> MongoDB
(what the website reads). Runs as a background task inside the bot
process so it can resolve real Discord usernames/avatars from the
bot's already-populated user cache — a standalone script without a
bot connection would only ever show "Player 1234" placeholders.

INSTALL: drop this file into your bot repo as bleachdex/sync/mongo_sync.py
(create the bleachdex/sync/ folder, it needs an empty __init__.py too),
add `motor>=3.5.0` and `pymongo>=4.8.0` to requirements.txt, and add
MONGODB_URI (+ optionally MONGO_SYNC_INTERVAL_SECONDS) to your .env.

WIRE-UP: in bot.py, inside BleachDexBot.on_ready(), after the existing
on_ready_extra call, add:

    from sync.mongo_sync import start_background_sync
    start_background_sync(self)

That's it — the loop below then runs forever alongside the bot,
resyncing every SYNC_INTERVAL_SECONDS. It never writes back to SQLite
and never touches game logic, so there is zero risk to existing
commands even if this fails — a failed tick just logs a warning and
retries next interval.

WHY POLLING INSTEAD OF WRITE-THROUGH: every mutating action lives
across a dozen cogs (packs, spawn, trade, battle, shop, achievements).
Hooking Mongo writes into every one of them individually is a large,
invasive change with many places to introduce a bug. A 10-second
poll loop reads current truth from SQLite and mirrors it — the
website is never more than ~10s stale, which is invisible for a
leaderboard/dashboard use case, and the bot's actual command code is
never touched. If you later want zero-lag, call `sync_player(...)`
directly at the end of the specific mutating functions instead of
waiting for the timer — the functions below are already split per
entity so that's a small follow-up change, not a rewrite.

2026-09 UPDATE (matches the current bot schema):
- The old single-slot `teams` table is dead now (multi-preset /team
  update). Team data lives in `team_presets` + `team_active_preset`,
  so the team query below was rewritten to pull whichever preset is
  currently "active" per player, same as db/teams.py's get_team().
- Weapons switched from a flat `attack_bonus` number to a percentage
  boost against either HP or damage (`boost_type` / `boost_percent`).
  `attack_bonus` is kept in the DB for backward compatibility but is
  no longer written to, so weapons are now synced with boostType/
  boostPercent as the real numbers; attackBonus is still sent too
  (now informational only) in case the website hasn't been updated
  to read the new fields yet.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time

from motor.motor_asyncio import AsyncIOMotorClient

from db.connection import get_connection
from db.achievements import ACHIEVEMENTS, ACHIEVEMENT_KEYS

log = logging.getLogger("bleachdex.sync")

SYNC_INTERVAL_SECONDS = int(os.environ.get("MONGO_SYNC_INTERVAL_SECONDS", "3600"))
MONGODB_URI = os.environ.get("MONGODB_URI", "")

_client: AsyncIOMotorClient | None = None
_db = None


def _get_db():
    global _client, _db
    if _db is None:
        if not MONGODB_URI:
            raise RuntimeError(
                "MONGODB_URI is not set - add it to .env to enable the "
                "website sync bridge."
            )
        _client = AsyncIOMotorClient(MONGODB_URI)
        # Database name comes from the URI path (e.g. .../bleachdex);
        # get_default_database() reads that instead of hardcoding it here.
        _db = _client.get_default_database()
    return _db


# ---------------------------------------------------------------
# Blocking SQLite reads. Each one is a cheap, indexed query against a
# bot of this scale (hundreds of players, low thousands of owned
# rows) - all of them together typically finish in well under a
# second, which is fine for a 10s-interval background task.
# ---------------------------------------------------------------

def _fetch_characters(conn) -> list[dict]:
    from factions import CHARACTER_FACTIONS

    rows = conn.execute(
        "SELECT id, name, position, image_path, hp, attack, tier, "
        "ability_name, ability_description, card_image_path, enabled, "
        "craftable_only "
        "FROM characters"
    ).fetchall()

    owner_counts = {
        r["character_id"]: r["n"]
        for r in conn.execute(
            "SELECT character_id, COUNT(DISTINCT owner_discord_id) AS n "
            "FROM owned_characters GROUP BY character_id"
        ).fetchall()
    }
    catch_counts = {
        r["item_id"]: r["n"]
        for r in conn.execute(
            "SELECT item_id, COUNT(*) AS n FROM catch_log "
            "WHERE kind = 'character' GROUP BY item_id"
        ).fetchall()
    }

    out = []
    for r in rows:
        out.append({
            "sourceId": r["id"],
            "name": r["name"],
            "faction": CHARACTER_FACTIONS.get(r["name"], ""),
            "tier": r["tier"],
            "hp": r["hp"],
            "attack": r["attack"],
            "abilityName": r["ability_name"] or "",
            "abilityDescription": r["ability_description"] or "",
            "imagePath": r["image_path"],
            "cardImagePath": r["card_image_path"] or "",
            "enabled": bool(r["enabled"]),
            "craftableOnly": bool(r["craftable_only"]),
            "ownerCount": owner_counts.get(r["id"], 0),
            "totalCaught": catch_counts.get(r["id"], 0),
        })
    return out


def _fetch_weapons(conn) -> list[dict]:
    from factions import weapon_faction

    rows = conn.execute(
        "SELECT id, name, position, image_path, attack_bonus, boost_type, "
        "boost_percent, tier, ability_name, ability_description, "
        "card_image_path, enabled "
        "FROM weapons"
    ).fetchall()

    owner_counts = {
        r["weapon_id"]: r["n"]
        for r in conn.execute(
            "SELECT weapon_id, COUNT(DISTINCT owner_discord_id) AS n "
            "FROM owned_weapons GROUP BY weapon_id"
        ).fetchall()
    }
    catch_counts = {
        r["item_id"]: r["n"]
        for r in conn.execute(
            "SELECT item_id, COUNT(*) AS n FROM catch_log "
            "WHERE kind = 'weapon' GROUP BY item_id"
        ).fetchall()
    }

    out = []
    for r in rows:
        out.append({
            "sourceId": r["id"],
            "name": r["name"],
            "faction": weapon_faction(r["name"]),
            "tier": r["tier"],
            # boostType/boostPercent are the real numbers now; attackBonus
            # is kept for backward compat but is always 0 on new weapons.
            "attackBonus": r["attack_bonus"],
            "boostType": r["boost_type"],
            "boostPercent": r["boost_percent"],
            "abilityName": r["ability_name"] or "",
            "abilityDescription": r["ability_description"] or "",
            "imagePath": r["image_path"],
            "cardImagePath": r["card_image_path"] or "",
            "enabled": bool(r["enabled"]),
            "ownerCount": owner_counts.get(r["id"], 0),
            "totalCaught": catch_counts.get(r["id"], 0),
        })
    return out


def _fetch_players(conn) -> tuple[list[dict], int, int]:
    """Returns (players, enabled_character_count, enabled_weapon_count)."""
    enabled_char_count = conn.execute(
        "SELECT COUNT(*) AS n FROM characters WHERE enabled = 1"
    ).fetchone()["n"] or 1
    enabled_weapon_count = conn.execute(
        "SELECT COUNT(*) AS n FROM weapons WHERE enabled = 1"
    ).fetchone()["n"] or 1

    players = conn.execute("SELECT * FROM players").fetchall()

    char_counts = {
        r["owner_discord_id"]: (r["total"], r["unique_n"])
        for r in conn.execute(
            "SELECT owner_discord_id, COUNT(*) AS total, "
            "COUNT(DISTINCT character_id) AS unique_n "
            "FROM owned_characters GROUP BY owner_discord_id"
        ).fetchall()
    }
    weapon_counts = {
        r["owner_discord_id"]: (r["total"], r["unique_n"])
        for r in conn.execute(
            "SELECT owner_discord_id, COUNT(*) AS total, "
            "COUNT(DISTINCT weapon_id) AS unique_n "
            "FROM owned_weapons GROUP BY owner_discord_id"
        ).fetchall()
    }
    lifetime_catches = {
        r["discord_id"]: r["n"]
        for r in conn.execute(
            "SELECT discord_id, COUNT(*) AS n FROM catch_log GROUP BY discord_id"
        ).fetchall()
    }
    achievement_keys = {}
    for r in conn.execute(
        "SELECT discord_id, achievement_key FROM player_achievements"
    ).fetchall():
        achievement_keys.setdefault(r["discord_id"], []).append(r["achievement_key"])

    # Teams: the old single-slot `teams` table is dead - pull each
    # player's currently ACTIVE preset (team_active_preset, defaulting
    # to preset 1) from team_presets instead, matching db/teams.py's
    # get_team() with no explicit preset argument (what /battle and
    # the boss-battle Challenge button actually read).
    team_rows = conn.execute(
        """
        SELECT tp.owner_discord_id, tp.slot, c.id AS character_id, c.name,
               c.image_path, c.tier, ow.name AS weapon_name
        FROM team_presets tp
        LEFT JOIN team_active_preset tap ON tap.owner_discord_id = tp.owner_discord_id
        JOIN owned_characters oc ON oc.id = tp.character_instance_id
        JOIN characters c ON c.id = oc.character_id
        LEFT JOIN owned_weapons ow_inst ON ow_inst.id = oc.equipped_weapon_instance_id
        LEFT JOIN weapons ow ON ow.id = ow_inst.weapon_id
        WHERE tp.preset = COALESCE(tap.preset, 1)
        ORDER BY tp.owner_discord_id, tp.slot
        """
    ).fetchall()
    teams: dict[int, list[dict]] = {}
    for r in team_rows:
        teams.setdefault(r["owner_discord_id"], []).append({
            "slot": r["slot"],
            "characterId": r["character_id"],
            "name": r["name"],
            "imagePath": r["image_path"],
            "tier": r["tier"],
            "equippedWeaponName": r["weapon_name"] or "",
        })

    out = []
    for p in players:
        did = p["discord_id"]
        char_total, char_unique = char_counts.get(did, (0, 0))
        weapon_total, weapon_unique = weapon_counts.get(did, (0, 0))
        # Only current achievements - old removed keys would push "earned" past "total".
        keys = [k for k in achievement_keys.get(did, []) if k in ACHIEVEMENT_KEYS]
        out.append({
            "discordId": str(did),
            "kanCoins": p["kan_coins"],
            "battleWins": p["battle_wins"],
            "currentWinStreak": p["current_win_streak"],
            "bestWinStreak": p["best_win_streak"],
            "tradedAwayCount": p["traded_away_count"],
            "charactersOwned": char_total,
            "uniqueCharactersOwned": char_unique,
            "weaponsOwned": weapon_total,
            "uniqueWeaponsOwned": weapon_unique,
            "totalItemsOwned": char_total + weapon_total,
            "lifetimeCatches": lifetime_catches.get(did, 0),
            "rosterCharacterPct": round(100 * char_unique / enabled_char_count, 1),
            "rosterWeaponPct": round(100 * weapon_unique / enabled_weapon_count, 1),
            "lastDailyCoinClaim": p["last_daily_coin_claim"],
            "lastWeeklyPackClaim": p["last_weekly_pack_claim"],
            "dailyPackDate": p["daily_pack_date"] or "",
            "dailyPackPullsUsed": p["daily_pack_pulls_used"],
            "achievementsEarned": len(keys),
            "achievementsTotal": len(ACHIEVEMENTS),
            "achievementKeys": keys,
            "team": teams.get(did, []),
        })

    return out, enabled_char_count, enabled_weapon_count


def _fetch_leaderboard(conn) -> list[dict]:
    """Matches db/leaderboard.py's overall_leaderboard() exactly, but
    scores on UNIQUE characters + unique weapons (matching the /ranks
    page's own "Rank is unique characters + unique weapons" wording)
    rather than raw total owned."""
    rows = conn.execute(
        """
        WITH char_unique AS (
            SELECT owner_discord_id AS discord_id,
                   COUNT(DISTINCT character_id) AS n
            FROM owned_characters GROUP BY owner_discord_id
        ),
        weapon_unique AS (
            SELECT owner_discord_id AS discord_id,
                   COUNT(DISTINCT weapon_id) AS n
            FROM owned_weapons GROUP BY owner_discord_id
        )
        SELECT
            COALESCE(c.discord_id, w.discord_id) AS discord_id,
            COALESCE(c.n, 0) + COALESCE(w.n, 0) AS score
        FROM char_unique c
        FULL OUTER JOIN weapon_unique w ON w.discord_id = c.discord_id
        ORDER BY score DESC
        LIMIT 100
        """
    ).fetchall()
    return [dict(r) for r in rows]


# SQLite (< 3.39 in some environments) doesn't support FULL OUTER JOIN.
# Fallback computed in Python keeps this working everywhere without
# needing to detect the SQLite version.
def _fetch_leaderboard_py(conn) -> list[dict]:
    char_unique = {
        r["owner_discord_id"]: r["n"]
        for r in conn.execute(
            "SELECT owner_discord_id, COUNT(DISTINCT character_id) AS n "
            "FROM owned_characters GROUP BY owner_discord_id"
        ).fetchall()
    }
    weapon_unique = {
        r["owner_discord_id"]: r["n"]
        for r in conn.execute(
            "SELECT owner_discord_id, COUNT(DISTINCT weapon_id) AS n "
            "FROM owned_weapons GROUP BY owner_discord_id"
        ).fetchall()
    }
    all_ids = set(char_unique) | set(weapon_unique)
    scored = [
        {"discord_id": did, "score": char_unique.get(did, 0) + weapon_unique.get(did, 0)}
        for did in all_ids
    ]
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:100]


def _fetch_site_stats(conn, enabled_char_count: int, enabled_weapon_count: int) -> dict:
    registered_players = conn.execute("SELECT COUNT(*) AS n FROM players").fetchone()["n"]
    total_caught = conn.execute("SELECT COUNT(*) AS n FROM catch_log").fetchone()["n"]
    total_in_circulation = (
        conn.execute("SELECT COUNT(*) AS n FROM owned_characters").fetchone()["n"]
        + conn.execute("SELECT COUNT(*) AS n FROM owned_weapons").fetchone()["n"]
    )
    total_battles_won = conn.execute(
        "SELECT COALESCE(SUM(battle_wins), 0) AS n FROM players"
    ).fetchone()["n"]
    total_trades = conn.execute(
        "SELECT COUNT(*) AS n FROM trade_proposals WHERE status = 'completed'"
    ).fetchone()["n"]

    return {
        "registeredPlayers": registered_players,
        "totalCardsCaught": total_caught,
        "totalItemsInCirculation": total_in_circulation,
        "totalBattlesWon": total_battles_won,
        "totalTradesCompleted": total_trades,
        "rosterCharacterCount": enabled_char_count,
        "rosterWeaponCount": enabled_weapon_count,
    }


# ---------------------------------------------------------------
# Discord name/avatar resolution (needs the live bot cache).
# ---------------------------------------------------------------

def _resolve_profile(bot, discord_id: int) -> tuple[str, str, str]:
    """Returns (username, globalName, avatarUrl). Falls back to a
    masked placeholder if the bot hasn't seen this user (e.g. they
    left every mutual server) rather than failing the whole sync."""
    if bot:
        user = bot.get_user(discord_id)
        if user:
            avatar = user.display_avatar.url if user.display_avatar else ""
            return user.name, (user.global_name or user.name), str(avatar)
    return f"Player {str(discord_id)[-4:]}", f"Player {str(discord_id)[-4:]}", ""


# ---------------------------------------------------------------
# Mongo write phase
# ---------------------------------------------------------------

async def _write_characters(db, characters: list[dict]):
    ops = []
    from pymongo import UpdateOne
    for c in characters:
        ops.append(UpdateOne({"sourceId": c["sourceId"]}, {"$set": c}, upsert=True))
    if ops:
        await db.characters.bulk_write(ops, ordered=False)


async def _write_weapons(db, weapons: list[dict]):
    ops = []
    from pymongo import UpdateOne
    for w in weapons:
        ops.append(UpdateOne({"sourceId": w["sourceId"]}, {"$set": w}, upsert=True))
    if ops:
        await db.weapons.bulk_write(ops, ordered=False)


async def _write_players(db, bot, players: list[dict]):
    from pymongo import UpdateOne
    ops = []
    for p in players:
        username, global_name, avatar_url = _resolve_profile(bot, int(p["discordId"]))
        doc = {
            **p,
            "username": username,
            "globalName": global_name,
            "avatarUrl": avatar_url,
            "lastSyncedAt": time.time(),
        }
        ops.append(UpdateOne({"discordId": p["discordId"]}, {"$set": doc}, upsert=True))
    if ops:
        await db.players.bulk_write(ops, ordered=False)


async def _write_leaderboard(db, bot, scored_rows: list[dict]):
    # Was doing one find_one() per row here (up to 100 individual awaited
    # Mongo round-trips every tick). Fetch all needed kanCoins in a single
    # query instead and look them up from a dict.
    ids = [str(row["discord_id"]) for row in scored_rows]
    kan_by_id = {}
    if ids:
        cursor = db.players.find({"discordId": {"$in": ids}}, {"discordId": 1, "kanCoins": 1})
        async for p in cursor:
            kan_by_id[p["discordId"]] = p.get("kanCoins", 0)

    docs = []
    for i, row in enumerate(scored_rows):
        did = row["discord_id"]
        username, global_name, avatar_url = _resolve_profile(bot, int(did))
        docs.append({
            "board": "overall",
            "rank": i + 1,
            "discordId": str(did),
            "displayName": global_name,
            "avatarUrl": avatar_url,
            "score": row["score"],
            "kanCoins": kan_by_id.get(str(did), 0),
        })

    await db.leaderboardentries.delete_many({"board": "overall"})
    if docs:
        await db.leaderboardentries.insert_many(docs)


async def _write_site_stats(db, stats: dict):
    await db.sitestats.update_one(
        {"singleton": "site_stats"},
        {"$set": {**stats, "generatedAt": time.time()}},
        upsert=True,
    )


# ---------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------

async def sync_once(bot=None) -> None:
    """Runs one full sync pass. Safe to call directly (e.g. from a
    slash command like `/admin sync` if you want an on-demand trigger
    in addition to the timer loop)."""
    db = _get_db()
    conn = get_connection()
    try:
        characters = _fetch_characters(conn)
        weapons = _fetch_weapons(conn)
        players, enabled_char_count, enabled_weapon_count = _fetch_players(conn)
        try:
            leaderboard_rows = _fetch_leaderboard(conn)
        except Exception:
            leaderboard_rows = _fetch_leaderboard_py(conn)
        site_stats = _fetch_site_stats(conn, enabled_char_count, enabled_weapon_count)
    finally:
        conn.close()

    await _write_characters(db, characters)
    await _write_weapons(db, weapons)
    await _write_players(db, bot, players)
    await _write_leaderboard(db, bot, leaderboard_rows)
    await _write_site_stats(db, site_stats)

    log.info(
        "mongo sync: %d characters, %d weapons, %d players, %d leaderboard rows",
        len(characters), len(weapons), len(players), len(leaderboard_rows),
    )


async def _loop(bot, interval: int):
    # Wait one interval before the first run so it doesn't compete with
    # everything else happening right as the bot finishes logging in.
    await asyncio.sleep(min(interval, 5))
    while True:
        try:
            await sync_once(bot)
        except Exception:
            log.exception("mongo sync tick failed - will retry next interval")
        await asyncio.sleep(interval)


def start_background_sync(bot, interval: int = SYNC_INTERVAL_SECONDS):
    """Call once from BleachDexBot.on_ready(). Returns the created
    asyncio.Task (kept alive on bot.loop; you don't need to hold a
    reference to it yourself, but bot.py stashes one anyway so it
    isn't garbage-collected mid-flight)."""
    if not MONGODB_URI:
        log.warning(
            "MONGODB_URI not set - website sync bridge disabled. The bot "
            "and admin panel work fine without it; only the website's "
            "live data will be stale/empty."
        )
        return None
    log.info("Starting MongoDB sync bridge (every %ds)", interval)
    return bot.loop.create_task(_loop(bot, interval))