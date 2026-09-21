"""
Achievements.

Each achievement has a stable `key` (stored in player_achievements) - the
key is what makes "nobody gets an achievement twice" work: a player who
already has a row for a key is skipped by check_and_grant() and is never
paid again, no matter how the achievement is renamed/re-worded/re-priced
here. NEVER reuse a key for a different achievement, and don't rename a
key that players already hold. (Old keys that are no longer in the list
below - first_steps, opening_time, hoarder, collector, ... - are simply
left alone in the table; they're ignored everywhere and never re-paid.)

How progress is measured
------------------------
- "Catch N souls" reads catch_log (db/connection.py) - a permanent record
  of every catch/pull/craft, so trading things away never lowers it.
- Mythic / Reiatsu counts are lifetime catches, or what you currently own
  if that's higher (so souls received in trades still count).
- "Collect all X" / Perfectionist read what you CURRENTLY own, like the
  /collection completion screen does.
- Trade achievements read trade_proposals / trade_proposal_items (every
  completed trade is kept there, so these are fully retroactive).
- Catch-speed achievements read counters written by record_catch_speed()
  (called from cogs/spawn.py the moment a spawn is caught).
- Battle achievements: boss fights count as battles (players.battle_wins +
  the "bossbattle_wins" stat). Admin/owner/flawless ones read the stats
  written by cogs/boss.py (flawless) and record_pvp_result() below (PvP -
  no PvP command exists in the codebase yet, see that function).

Call check_and_grant(discord_id) after any action that could complete one
of these. It only looks at achievements the player doesn't have yet and
loads each piece of data at most once per call (see Progress).
"""

import logging
import time
from dataclasses import dataclass
from typing import Callable

from db.connection import get_connection
from db import collection as coll
from db import player_stats as pstats
from factions import completion_group, VISORED_NAMES

log = logging.getLogger("bleachdex.achievements")


@dataclass
class Achievement:
    key: str
    name: str
    desc: str                                   # may contain "{n}" = the target number
    threshold: "int | Callable[[], int]"        # a number, or a function for roster-based targets
    progress_fn: Callable[["Progress"], int]
    kan_reward: int = 1000
    icon_path: str = ""  # set later via /admin achievement seticon, once art exists

    def target(self) -> int:
        """The number to reach. Roster-based achievements ("collect all X")
        compute it from the CURRENT roster, so the numbers always match
        what actually exists in the bot."""
        n = self.threshold() if callable(self.threshold) else self.threshold
        return max(1, n)

    @property
    def description(self) -> str:
        return self.desc.replace("{n}", str(self.target()))


# ---------- Roster pools (which characters/weapons count for which set) ----------

# The ten Gotei 13 captains "Gotei 13" asks for (exact roster names).
CAPTAIN_NAMES = [
    "Genryusai Shigekuni Yamamoto",
    "Sajin Komamura",
    "Soi Fon",
    "Byakuya Kuchiki",
    "Shunsui Kyoraku",
    "Toshiro Hitsugaya",
    "Kenpachi Zaraki",
    "Retsu Unohana",
    "Jushiro Ukitake",
    "Mayuri Kurotsuchi",
]

# Weapons that are NOT Zanpakuto (Shikai/Bankai): the Arrancar Resurreccion
# swords and the Quincy Vollstandig weapons. Everything else in the weapons
# table is a Zanpakuto, and that's what "Zanpakuto Collector" counts.
NON_ZANPAKUTO_WEAPONS = {
    # Arrancar Resurreccion
    "Murcielago", "Los Lobos", "Pantera", "Gamuza", "Tiburon",
    "Santa Teresa", "Fornicaras", "Brujeria", "Glotoneria", "Ira",
    # Quincy
    "Kruzifix", "Freund Schild", "Diagramm", "Tatar Foras",
}

# Members of the Hollow completion tab that are NOT Arrancar.
NON_ARRANCAR_NAMES = {"Grand Fisher"}

_POOL_TTL = 300  # seconds - roster changes rarely, no need to re-query on every catch
_pool_cache: dict = {"ts": 0.0, "data": None}


def _pools() -> dict:
    """ID sets for each collection achievement, cached for a few minutes."""
    now = time.time()
    if _pool_cache["data"] is not None and now - _pool_cache["ts"] < _POOL_TTL:
        return _pool_cache["data"]

    conn = get_connection()
    try:
        chars = conn.execute(
            "SELECT id, name, craftable_only FROM characters WHERE enabled = 1"
        ).fetchall()
        weapons = conn.execute("SELECT id, name FROM weapons WHERE enabled = 1").fetchall()
    finally:
        conn.close()

    by_name = {c["name"]: c["id"] for c in chars}
    zanpakuto = [w for w in weapons if w["name"] not in NON_ZANPAKUTO_WEAPONS]
    weapon_names = {w["name"].lower() for w in zanpakuto}
    normal = [c for c in chars if not c["craftable_only"]]

    data = {
        "captains": {by_name[n] for n in CAPTAIN_NAMES if n in by_name},
        "vizards": {by_name[n] for n in VISORED_NAMES if n in by_name},
        "arrancar": {
            c["id"] for c in normal
            if completion_group(c["name"]) == "hollow" and c["name"] not in NON_ARRANCAR_NAMES
        },
        "quincy": {c["id"] for c in normal if completion_group(c["name"]) == "quincy"},
        # A "Zanpakuto Spirit" is a character that shares its name with a
        # Zanpakuto weapon (Haineko, Tobiume, Wabisuke, ...).
        "spirits": {c["id"] for c in normal if c["name"].lower() in weapon_names},
        "all_characters": {c["id"] for c in chars},   # includes craftables, like /collection completion
        "all_weapons": {w["id"] for w in weapons},
        "zanpakuto": {w["id"] for w in zanpakuto},
    }
    _pool_cache["ts"] = now
    _pool_cache["data"] = data
    return data


# ---------- Per-player progress snapshot ----------

class Progress:
    """Everything an achievement might need to know about one player.
    Each value is queried lazily and at most once per instance, so
    checking ~35 achievements costs a handful of small queries, not 35+."""

    def __init__(self, discord_id: int):
        self.discord_id = discord_id
        self._cache: dict = {}

    def _once(self, name: str, fn):
        if name not in self._cache:
            self._cache[name] = fn()
        return self._cache[name]

    def _scalar(self, sql: str, *params) -> int:
        conn = get_connection()
        try:
            row = conn.execute(sql, params).fetchone()
            return (row[0] or 0) if row else 0
        finally:
            conn.close()

    # -- counters written by pstats.increment() --
    @property
    def stats(self) -> dict:
        def load():
            conn = get_connection()
            try:
                rows = conn.execute(
                    "SELECT stat_key, value FROM player_stats WHERE discord_id = ?",
                    (self.discord_id,),
                ).fetchall()
                return {r["stat_key"]: r["value"] for r in rows}
            finally:
                conn.close()
        return self._once("stats", load)

    def stat(self, key: str) -> int:
        return self.stats.get(key, 0)

    # -- catches --
    @property
    def total_caught(self) -> int:
        return self._once("total_caught", lambda: self._scalar(
            "SELECT COUNT(*) FROM catch_log WHERE discord_id = ?", self.discord_id))

    @property
    def mythic_count(self) -> int:
        def load():
            caught = self._scalar(
                """SELECT COUNT(*) FROM catch_log cl JOIN characters c ON c.id = cl.item_id
                   WHERE cl.discord_id = ? AND cl.kind = 'character' AND c.tier = 'mythic'""",
                self.discord_id)
            owned = self._scalar(
                """SELECT COUNT(*) FROM owned_characters oc JOIN characters c ON c.id = oc.character_id
                   WHERE oc.owner_discord_id = ? AND c.tier = 'mythic'""",
                self.discord_id)
            return max(caught, owned)
        return self._once("mythic_count", load)

    @property
    def reiatsu_count(self) -> int:
        def load():
            caught = self._scalar(
                "SELECT COUNT(*) FROM catch_log WHERE discord_id = ? AND kind = 'character' AND is_reiatsu = 1",
                self.discord_id)
            owned = self._scalar(
                "SELECT COUNT(*) FROM owned_characters WHERE owner_discord_id = ? AND is_reiatsu = 1",
                self.discord_id)
            return max(caught, owned)
        return self._once("reiatsu_count", load)

    @property
    def main_server_catches(self) -> int:
        """1 if this player has ever caught a spawn in the main server
        (BLEACHDEX_MAIN_GUILD_ID), else 0. Reads active_spawns, so it's
        retroactive for catches made before this achievement existed."""
        def load():
            import config
            if not config.MAIN_GUILD_ID:
                return 0
            return self._scalar(
                "SELECT 1 FROM active_spawns WHERE caught_by = ? AND guild_id = ? LIMIT 1",
                self.discord_id, config.MAIN_GUILD_ID)
        return self._once("main_server_catches", load)

    # -- collection --
    @property
    def owned_character_ids(self) -> set:
        return self._once("owned_chars", lambda: coll.get_owned_character_ids(self.discord_id))

    @property
    def owned_weapon_ids(self) -> set:
        return self._once("owned_weapons", lambda: coll.get_owned_weapon_ids(self.discord_id))

    def owned_in_pool(self, pool_name: str) -> int:
        return len(self.owned_character_ids & _pools()[pool_name])

    @property
    def completion_percent(self) -> int:
        """Whole-number % of the roster (characters incl. craftables + weapons)
        currently owned - same maths as /collection completion, rounded DOWN
        so it only reaches 100 when nothing is missing."""
        pools = _pools()
        total = len(pools["all_characters"]) + len(pools["all_weapons"])
        if not total:
            return 0
        owned = (len(self.owned_character_ids & pools["all_characters"])
                 + len(self.owned_weapon_ids & pools["all_weapons"]))
        return owned * 100 // total

    # -- trades (all completed trades are kept in trade_proposals) --
    @property
    def trades(self) -> dict:
        def load():
            conn = get_connection()
            try:
                rows = conn.execute(
                    """SELECT t.user_a_coins + t.user_b_coins AS coins,
                              (SELECT COUNT(*) FROM trade_proposal_items i WHERE i.trade_id = t.id) AS items
                       FROM trade_proposals t
                       WHERE t.status = 'completed' AND (t.user_a_id = ? OR t.user_b_id = ?)""",
                    (self.discord_id, self.discord_id),
                ).fetchall()
            finally:
                conn.close()
            return {
                "count": len(rows),
                "max_items": max((r["items"] for r in rows), default=0),
                "with_kan": sum(1 for r in rows if r["coins"] > 0),
            }
        return self._once("trades", load)

    # -- battles --
    @property
    def battle_wins(self) -> int:
        """PvP wins (players.battle_wins) + boss-battle wins."""
        def load():
            pvp = self._scalar("SELECT battle_wins FROM players WHERE discord_id = ?", self.discord_id)
            return pvp + self.stat("bossbattle_wins")
        return self._once("battle_wins", load)

    @property
    def boss_wins(self) -> int:
        # "bossbattle_wins" is what cogs/boss.py writes; "boss_wins" was the
        # old co-op boss counter. (This used to read only "boss_wins", so
        # Boss Slayer could never be earned.)
        return self.stat("bossbattle_wins") + self.stat("boss_wins")


def _pool_size(name: str):
    return lambda: len(_pools()[name])


# ---------- The achievement list ----------
# Order here is the order /achievements shows them in.
# Keys marked (kept) already exist in player_achievements - unchanged on purpose
# so nobody who already earned them is paid again.

ACHIEVEMENTS: list[Achievement] = [
    Achievement("main_catcher", "Main Catcher", "Catch your first soul in the main server.", 1,
                lambda p: p.main_server_catches, kan_reward=3000),
    Achievement("speed_is_a_burden", "Speed is a Burden", "Catch a soul in less than 5 seconds.", 1,
                lambda p: p.stat("catch_lt5s"), kan_reward=5000),
    Achievement("fast_catcher", "Fast Catcher", "Catch a soul in under 20 seconds.", 1,
                lambda p: p.stat("catch_lt20s"), kan_reward=1500),
    Achievement("sniper", "Sniper", "Catch a soul in 10 seconds or under.", 1,
                lambda p: p.stat("catch_le10s"), kan_reward=3500),

    Achievement("catch_100", "Novice", "Catch 100 souls.", 100, lambda p: p.total_caught, kan_reward=1500),
    Achievement("catch_500", "Semi-pro", "Catch 500 souls.", 500, lambda p: p.total_caught, kan_reward=2500),
    Achievement("catch_1000", "Hoarder", "Catch 1,000 souls.", 1000, lambda p: p.total_caught, kan_reward=5000),

    Achievement("reiatsu_supply", "Reiatsu Supply", "Obtain 5 Reiatsu Infused souls.", 5,
                lambda p: p.reiatsu_count, kan_reward=3500),
    Achievement("mythic_collector", "Mythic Collector", "Obtain 5 Mythical souls.", 5,
                lambda p: p.mythic_count, kan_reward=3500),
    Achievement("reiatsu_collector", "Reiatsu Collector", "Obtain 10 Reiatsu Infused souls.", 10,
                lambda p: p.reiatsu_count, kan_reward=5000),
    Achievement("mighty_myths", "Mighty Myths", "Obtain 10 Mythical souls.", 10,
                lambda p: p.mythic_count, kan_reward=5000),
    Achievement("mythical_aura", "Mythical Aura", "Obtain your first mythical soul.", 1,
                lambda p: p.mythic_count, kan_reward=3500),
    Achievement("reiatsu_knot", "Reiatsu Knot", "Obtain your first Reiatsu Infused soul.", 1,
                lambda p: p.reiatsu_count, kan_reward=3500),

    Achievement("gotei_13", "Gotei 13", "Obtain 1x each Captain.", _pool_size("captains"),
                lambda p: p.owned_in_pool("captains"), kan_reward=3500),
    Achievement("zanpakuto_collector", "Zanpakuto Collector", "Obtain 1x each Zanpakuto.", _pool_size("zanpakuto"),
                lambda p: len(p.owned_weapon_ids & _pools()["zanpakuto"]), kan_reward=3500),
    Achievement("espada_fleet", "Espada Fleet", "Obtain 1x each Arrancar, including the Espada.", _pool_size("arrancar"),
                lambda p: p.owned_in_pool("arrancar"), kan_reward=5000),
    Achievement("perfectionist", "Perfectionist", "Get 100% completion.", 100,
                lambda p: p.completion_percent, kan_reward=5000),

    Achievement("junior_trade", "Junior Trade", "Complete one trade with 10 souls.", 10,
                lambda p: p.trades["max_items"], kan_reward=3000),
    Achievement("semi_pro_trader", "Semi-pro Trader", "Complete one trade with 50 souls.", 50,
                lambda p: p.trades["max_items"], kan_reward=5000),
    # (kept) key "the_marketplace" - was "The marketplace", same 1500 reward
    Achievement("the_marketplace", "Trading Novice", "Complete your first trade.", 1,
                lambda p: p.trades["count"], kan_reward=1500),
    Achievement("kan_trader", "Kan Trader", "Complete a trade which includes Kan.", 1,
                lambda p: p.trades["with_kan"], kan_reward=1500),
    Achievement("trading_beginner", "Trading Beginner", "Complete 50 trades.", 50,
                lambda p: p.trades["count"], kan_reward=1500),

    Achievement("fighter", "Fighter", "Win your first battle.", 1, lambda p: p.battle_wins, kan_reward=1500),
    # (kept) key "boss_slayer"
    Achievement("boss_slayer", "Boss Slayer", "Win a boss battle.", 1, lambda p: p.boss_wins, kan_reward=5000),
    # (kept) key "beating_the_boss" - was "Beating the boss", same 7500 reward
    Achievement("beating_the_boss", "Beating the Sternritter", "Win a battle against an admin.", 1,
                lambda p: p.stat("beat_admin_wins"), kan_reward=7500),
    # (kept) key "dethroning_the_king" - was "Dethroning the king", same 10000 reward
    Achievement("dethroning_the_king", "Dethroning the Almighty", "Win a battle against the owner.", 1,
                lambda p: p.stat("beat_owner_wins"), kan_reward=10000),
    Achievement("flawless_victory", "Flawless Victory", "Win a battle without losing a single character.", 1,
                lambda p: p.stat("flawless_wins"), kan_reward=4000),

    # (kept) key "crafter"
    Achievement("crafter", "Crafter", "Craft your 1st collectable.", 1,
                lambda p: p.stat("items_crafted"), kan_reward=3000),
    Achievement("master_craftsman", "Master Craftsman", "Craft 10 collectables.", 10,
                lambda p: p.stat("items_crafted"), kan_reward=6000),
    Achievement("bankai_spammer", "Bankai Spammer", "Win 10 battles.", 10,
                lambda p: p.battle_wins, kan_reward=3000),

    # (kept) keys "trusted_deal" / "high_roller"
    Achievement("trusted_deal", "Trusted Deal", "Trade with an admin.", 1,
                lambda p: p.stat("traded_with_admin"), kan_reward=5000),
    Achievement("high_roller", "High Roller", "Trade with the owner.", 1,
                lambda p: p.stat("traded_with_owner"), kan_reward=7500),

    Achievement("vizard_mask", "Vizard Mask", "Collect all Visored/Vizards.", _pool_size("vizards"),
                lambda p: p.owned_in_pool("vizards"), kan_reward=7500),
    Achievement("zanpakuto_spirit", "Zanpakuto Spirit", "Collect all {n} Zanpakuto Spirits.", _pool_size("spirits"),
                lambda p: p.owned_in_pool("spirits"), kan_reward=5000),
    Achievement("quincy_k", "Quincy K", "Collect all {n} Quincy.", _pool_size("quincy"),
                lambda p: p.owned_in_pool("quincy"), kan_reward=8000),
]

ACHIEVEMENT_KEYS: set[str] = {a.key for a in ACHIEVEMENTS}


# ---------- Reading / granting ----------

def earned_keys(discord_id: int) -> set[str]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT achievement_key FROM player_achievements WHERE discord_id = ?",
            (discord_id,),
        ).fetchall()
        return {r["achievement_key"] for r in rows}
    finally:
        conn.close()


def earned_count(discord_id: int) -> int:
    """How many of the CURRENT achievements this player has (ignores old
    keys that are no longer in the list)."""
    return len(earned_keys(discord_id) & ACHIEVEMENT_KEYS)


def check_and_grant(discord_id: int) -> list[Achievement]:
    """Grants any newly-met achievements (paying their KAN reward) and
    returns the ones earned THIS call, so the caller can announce them.

    Achievements the player already has are skipped entirely, and the
    INSERT is checked (rowcount) so two checks racing each other can
    never pay the same achievement twice."""
    from db import players as pl

    already = earned_keys(discord_id)
    pending = [a for a in ACHIEVEMENTS if a.key not in already]
    if not pending:
        return []

    progress = Progress(discord_id)
    newly_earned: list[Achievement] = []
    conn = get_connection()
    try:
        for a in pending:
            try:
                if a.progress_fn(progress) < a.target():
                    continue
            except Exception:
                # One broken achievement must never break a catch/pack/trade.
                log.exception("Achievement %s progress check failed", a.key)
                continue
            cur = conn.execute(
                "INSERT OR IGNORE INTO player_achievements "
                "(discord_id, achievement_key, earned_at) VALUES (?, ?, ?)",
                (discord_id, a.key, int(time.time())),
            )
            if cur.rowcount == 1:
                newly_earned.append(a)
        conn.commit()
    finally:
        conn.close()

    for a in newly_earned:
        pl.add_coins(discord_id, a.kan_reward)

    return newly_earned


# ---------- Hooks that record the counters the achievements above read ----------

def record_catch_speed(discord_id: int, seconds: float) -> None:
    """Call once per successful spawn catch with the seconds between the
    spawn appearing and the correct guess. Feeds Speed is a Burden (<5s),
    Sniper (<=10s) and Fast Catcher (<20s)."""
    if seconds < 5:
        pstats.increment(discord_id, "catch_lt5s")
    if seconds <= 10:
        pstats.increment(discord_id, "catch_le10s")
    if seconds < 20:
        pstats.increment(discord_id, "catch_lt20s")


def record_pvp_result(
    winner_id: int,
    loser_id: int,
    *,
    loser_is_admin: bool = False,
    loser_is_owner: bool = False,
    winner_lost_no_characters: bool = False,
) -> None:
    """Hook for a player-vs-player battle command. There isn't one in the
    codebase right now (cogs/battle.py only holds shared stat helpers), so
    nothing calls this yet - but Beating the Sternritter, Dethroning the
    Almighty, Fighter, Bankai Spammer and Flawless Victory all need it the
    moment one exists. Call it when a PvP battle resolves, then call
    check_and_grant(winner_id)."""
    from db import players as pl

    pl.record_battle_win(winner_id)
    pl.record_battle_loss(loser_id)
    if loser_is_admin:
        pstats.increment(winner_id, "beat_admin_wins")
    if loser_is_owner:
        pstats.increment(winner_id, "beat_owner_wins")
    if winner_lost_no_characters:
        pstats.increment(winner_id, "flawless_wins")