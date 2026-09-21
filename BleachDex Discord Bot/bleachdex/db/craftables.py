"""
Craftable characters. A craftable IS a normal row in the `characters`
table (with craftable_only=1 - see db/characters.py's
list_characters(), which excludes those from every normal pack/spawn
pool automatically) so once someone owns one it works everywhere a
normal character does: /collection, /equip, /battle, /trade. The only
special thing about it is how you GET one - spending ingredients here,
never a pack or a wild spawn.

A recipe is a list of ingredients (craft_ingredients table), each one of:

    drop       boss drops in owned_boss_drops (Hogyoku, Jigokucho, ...)
    weapon     owned weapon cards, matched by weapon name (Zabimaru, ...)
    character  owned character cards, matched by character name - this
               covers both the base character ("Sosuke Aizen") and
               "previous form" ingredients, because every craftable is
               itself a characters row

Crafting checks EVERY ingredient first and only then consumes them, all
in one transaction, so a failed craft never eats half a recipe.

Old single-drop recipes (craft_recipes table, created by
/admin craftable add before multi-ingredient recipes existed) are still
read as a fallback for characters that have no craft_ingredients rows.
"""

import unicodedata
from dataclasses import dataclass, field

from db.connection import get_connection
from db import characters as ch
from db import player_stats as pstats
from db.collection import grant_character, get_owned_character_instance


class CraftError(Exception):
    pass


KINDS = ("drop", "weapon", "character")


@dataclass
class Ingredient:
    kind: str    # 'drop' | 'weapon' | 'character'
    name: str
    qty: int = 1


@dataclass
class Recipe:
    character_id: int
    ingredients: list[Ingredient] = field(default_factory=list)
    category: str = ""


# ---------------------------------------------------------------------------
# creating craftables / recipes
# ---------------------------------------------------------------------------

def set_recipe(character_id: int, ingredients: list[Ingredient]) -> None:
    """Replaces the character's whole recipe with `ingredients`."""
    for ing in ingredients:
        if ing.kind not in KINDS:
            raise CraftError(f"Unknown ingredient kind {ing.kind!r} for {ing.name}.")
    conn = get_connection()
    try:
        conn.execute("DELETE FROM craft_ingredients WHERE character_id = ?", (character_id,))
        conn.executemany(
            "INSERT INTO craft_ingredients (character_id, kind, item_name, qty, sort_order) "
            "VALUES (?, ?, ?, ?, ?)",
            [(character_id, i.kind, i.name, i.qty, n) for n, i in enumerate(ingredients)],
        )
        conn.commit()
    finally:
        conn.close()


def add_craftable(
    name: str,
    image_path: str,
    hp: int,
    attack: int,
    required_drop_name: str,
    required_drop_qty: int,
) -> ch.Character:
    """Creates a craftable character with a single-drop recipe (used by
    /admin craftable add). Raises CraftError if a character with this
    name already exists (craftable or not) - edit the existing one
    directly if you need to change something, this only creates new
    ones. Multi-ingredient recipes come from seed_craftables.py."""
    if ch.find_character_by_name(name, enabled_only=False) is not None:
        raise CraftError(f"A character named **{name}** already exists.")

    character_id = ch.add_character(
        name=name, image_path=image_path, hp=hp, attack=attack,
        tier="mythic",  # craftables skip pack/spawn tier logic entirely; this is just a display label
    )
    conn = get_connection()
    try:
        conn.execute("UPDATE characters SET craftable_only = 1 WHERE id = ?", (character_id,))
        conn.commit()
    finally:
        conn.close()
    set_recipe(character_id, [Ingredient("drop", required_drop_name, required_drop_qty)])
    return ch.get_character(character_id)


def upsert_craftable(
    name: str,
    image_path: str,
    card_image_path: str,
    hp: int,
    attack: int,
    tier: str,
    ability_name: str,
    ability_description: str,
    category: str,
    ingredients: list[Ingredient],
) -> tuple[ch.Character, bool]:
    """Creates the craftable if no character has this name yet, otherwise
    refreshes its stats/ability/category/recipe in place (image paths
    are left alone on an existing row so custom card art set through
    /admin edit character survives a re-seed). Returns (character,
    created). Safe to call repeatedly."""
    existing = ch.find_character_by_name(name, enabled_only=False)
    if existing is not None and not existing.craftable_only:
        raise CraftError(
            f"**{name}** already exists as a normal (pack/spawn) character - "
            "refusing to turn it into a craftable."
        )
    created = existing is None
    if created:
        character_id = ch.add_character(
            name=name, image_path=image_path, hp=hp, attack=attack, tier=tier,
            ability_name=ability_name, ability_description=ability_description,
        )
    else:
        character_id = existing.id

    conn = get_connection()
    try:
        if created:
            conn.execute(
                "UPDATE characters SET craftable_only = 1, craft_category = ?, card_image_path = ? "
                "WHERE id = ?",
                (category, card_image_path, character_id),
            )
        else:
            conn.execute(
                """UPDATE characters SET hp = ?, attack = ?, tier = ?, ability_name = ?,
                          ability_description = ?, craftable_only = 1, craft_category = ?
                   WHERE id = ?""",
                (hp, attack, tier, ability_name, ability_description, category, character_id),
            )
        conn.commit()
    finally:
        conn.close()

    set_recipe(character_id, ingredients)
    return ch.get_character(character_id), created


# ---------------------------------------------------------------------------
# reading recipes
# ---------------------------------------------------------------------------

def _legacy_recipe(conn, character_id: int) -> list[Ingredient]:
    row = conn.execute(
        "SELECT required_drop_name, required_drop_qty FROM craft_recipes WHERE character_id = ?",
        (character_id,),
    ).fetchone()
    return [Ingredient("drop", row["required_drop_name"], row["required_drop_qty"])] if row else []


def list_craftables() -> list[tuple[ch.Character, Recipe]]:
    """Every enabled craftable with its recipe, in creation order (so a
    chain like Aizen's five fusions stays in order within its category)."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT c.*, c.craft_category AS _category
               FROM characters c
               WHERE c.craftable_only = 1 AND c.enabled = 1
               ORDER BY c.id"""
        ).fetchall()
        by_char: dict[int, list[Ingredient]] = {}
        for r in conn.execute(
            "SELECT character_id, kind, item_name, qty FROM craft_ingredients "
            "ORDER BY character_id, sort_order, id"
        ).fetchall():
            by_char.setdefault(r["character_id"], []).append(
                Ingredient(r["kind"], r["item_name"], r["qty"])
            )
        out = []
        for row in rows:
            character = ch.Character.from_row(row)
            ingredients = by_char.get(row["id"]) or _legacy_recipe(conn, row["id"])
            out.append((character, Recipe(row["id"], ingredients, row["_category"] or "")))
        return out
    finally:
        conn.close()


def get_recipe(character_id: int) -> Recipe | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT craft_category FROM characters WHERE id = ?", (character_id,)
        ).fetchone()
        if row is None:
            return None
        ingredients = [
            Ingredient(r["kind"], r["item_name"], r["qty"])
            for r in conn.execute(
                "SELECT kind, item_name, qty FROM craft_ingredients "
                "WHERE character_id = ? ORDER BY sort_order, id",
                (character_id,),
            ).fetchall()
        ] or _legacy_recipe(conn, character_id)
        if not ingredients:
            return None
        return Recipe(character_id, ingredients, row["craft_category"] or "")
    finally:
        conn.close()



def _norm(text) -> str:
    """Case/accent/whitespace-insensitive form of a name, so an ingredient
    'Sosuke Aizen' still matches a card stored as 'Sōsuke  Aizen'."""
    if text is None:
        return ""
    decomposed = unicodedata.normalize("NFKD", str(text))
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(stripped.casefold().split())


def _open():
    conn = get_connection()
    conn.create_function("norm", 1, _norm, deterministic=True)
    return conn

# ---------------------------------------------------------------------------
# what the player holds
# ---------------------------------------------------------------------------

def _have(conn, discord_id: int, ing: Ingredient) -> int:
    if ing.kind == "drop":
        row = conn.execute(
            "SELECT quantity FROM owned_boss_drops WHERE discord_id = ? AND drop_name = ?",
            (discord_id, ing.name),
        ).fetchone()
        return row["quantity"] if row else 0
    if ing.kind == "weapon":
        return conn.execute(
            """SELECT COUNT(*) FROM owned_weapons ow JOIN weapons w ON w.id = ow.weapon_id
               WHERE ow.owner_discord_id = ? AND norm(w.name) = norm(?)""",
            (discord_id, ing.name),
        ).fetchone()[0]
    return conn.execute(
        """SELECT COUNT(*) FROM owned_characters oc JOIN characters c ON c.id = oc.character_id
           WHERE oc.owner_discord_id = ? AND norm(c.name) = norm(?)""",
        (discord_id, ing.name),
    ).fetchone()[0]


def get_have(discord_id: int, ingredients: list[Ingredient]) -> list[int]:
    """How many of each ingredient the player currently holds, same
    order as `ingredients` (one connection for the whole recipe)."""
    conn = _open()
    try:
        return [_have(conn, discord_id, i) for i in ingredients]
    finally:
        conn.close()


def missing_summary(discord_id: int, recipe: Recipe) -> list[str]:
    """['1x Hogyoku (have 0)', ...] for whatever's short; empty if craftable now."""
    have = get_have(discord_id, recipe.ingredients)
    return [
        f"{i.qty}x {i.name} (have {h})"
        for i, h in zip(recipe.ingredients, have) if h < i.qty
    ]


# ---------------------------------------------------------------------------
# crafting
# ---------------------------------------------------------------------------

def _consume_weapons(conn, discord_id: int, name: str, qty: int) -> None:
    rows = conn.execute(
        """SELECT ow.id,
                  EXISTS(SELECT 1 FROM owned_characters oc
                         WHERE oc.equipped_weapon_instance_id = ow.id) AS equipped
           FROM owned_weapons ow JOIN weapons w ON w.id = ow.weapon_id
           WHERE ow.owner_discord_id = ? AND norm(w.name) = norm(?)
           ORDER BY equipped ASC, ow.caught_at ASC""",   # spare copies go first
        (discord_id, name),
    ).fetchall()
    for r in rows[:qty]:
        conn.execute(
            "UPDATE owned_characters SET equipped_weapon_instance_id = NULL "
            "WHERE equipped_weapon_instance_id = ?", (r["id"],),
        )
        conn.execute("DELETE FROM owned_weapons WHERE id = ?", (r["id"],))


def _consume_characters(conn, discord_id: int, name: str, qty: int) -> None:
    rows = conn.execute(
        """SELECT oc.id,
                  EXISTS(SELECT 1 FROM team_presets tp WHERE tp.character_instance_id = oc.id) AS on_team,
                  (oc.equipped_weapon_instance_id IS NOT NULL) AS has_weapon
           FROM owned_characters oc JOIN characters c ON c.id = oc.character_id
           WHERE oc.owner_discord_id = ? AND norm(c.name) = norm(?)
           ORDER BY on_team ASC, has_weapon ASC, oc.is_reiatsu ASC, oc.caught_at ASC""",  # spare, plain copies go first
        (discord_id, name),
    ).fetchall()
    for r in rows[:qty]:
        conn.execute("DELETE FROM team_presets WHERE character_instance_id = ?", (r["id"],))
        conn.execute("DELETE FROM owned_characters WHERE id = ?", (r["id"],))


def craft(discord_id: int, character_id: int):
    character = ch.get_character(character_id)
    if character is None or not character.craftable_only:
        raise CraftError("That's not a craftable character.")

    recipe = get_recipe(character_id)
    if recipe is None:
        raise CraftError(f"**{character.name}** has no recipe set - an admin needs to fix this.")

    conn = _open()
    try:
        conn.execute("BEGIN IMMEDIATE")
        short = [
            f"{i.qty}x {i.name} (you have {h})"
            for i in recipe.ingredients
            if (h := _have(conn, discord_id, i)) < i.qty
        ]
        if short:
            conn.rollback()
            raise CraftError("You're missing: " + ", ".join(short) + ".")

        for i in recipe.ingredients:
            if i.kind == "drop":
                conn.execute(
                    "UPDATE owned_boss_drops SET quantity = quantity - ? "
                    "WHERE discord_id = ? AND drop_name = ?",
                    (i.qty, discord_id, i.name),
                )
            elif i.kind == "weapon":
                _consume_weapons(conn, discord_id, i.name, i.qty)
            else:
                _consume_characters(conn, discord_id, i.name, i.qty)
        conn.commit()
    except CraftError:
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    # Returns (character, owned instance) - the instance carries is_reiatsu
    # (grant_character rolls the 10% chance), which cogs/craft.py shows.
    instance_id = grant_character(character_id, discord_id)
    instance = get_owned_character_instance(instance_id)
    pstats.increment(discord_id, "items_crafted")
    return character, instance