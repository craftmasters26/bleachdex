"""
A small registry for emoji that aren't tied to a specific character or
weapon - the KAN currency icon, boss drop icons, and anything else
that needs a settable custom emoji later. Built on top of the
existing bot_settings key-value table (db/connection.py) rather than
a new table, since this is exactly what that table is for.

Keys are freeform strings you choose, e.g. "kan" or "boss_drop:soul_shard".
Use dotted/colon namespacing for anything with many entries (boss
drops especially) so they don't collide with each other.

Keys are normalized to lowercase before hitting the database, since
bot_settings does a plain case-sensitive `key = ?` match - without this,
setting the key as "Kan" would silently never be found by code that
looks it up as "kan" (or vice versa), which is exactly the bug this
fixes: KAN's emoji was stored under "emoji:Kan" but discord_utils.
kan_label() always looks up "emoji:kan", so the mention lookup missed
and silently fell back to the plain "KAN" text.
"""

from db.connection import get_setting, set_setting

_PREFIX = "emoji:"


def get_emoji_id(key: str) -> str:
    """Returns the stored numeric emoji ID for `key`, or "" if unset."""
    return get_setting(_PREFIX + key.strip().lower(), "")


def set_emoji_id(key: str, emoji_id: str) -> None:
    set_setting(_PREFIX + key.strip().lower(), emoji_id)