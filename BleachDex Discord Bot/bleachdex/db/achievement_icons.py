"""
Lets an achievement's icon be set after the fact (once art exists)
without editing db/achievements.py's hardcoded list. Built on the
same bot_settings key-value table as db/custom_emoji.py.
"""

from db.connection import get_setting, set_setting

_PREFIX = "achievement_icon:"


def get_icon(achievement_key: str) -> str:
    return get_setting(_PREFIX + achievement_key, "")


def set_icon(achievement_key: str, image_path: str) -> None:
    set_setting(_PREFIX + achievement_key, image_path)