"""
One-time repair script.

What went wrong: your characters were bulk-inserted with image_path set
directly to a raw.githubusercontent.com URL (this is supported - see
image_source.py's docstring), but the URLs that got stored point at an
OLD image folder on GitHub ("images/character image/..."). At some
point that folder was renamed/reorganized to
"new soul images/New Character Images/...", and soul.py was updated to
match - but the already-seeded database rows were never updated, so
they still point at a path that 404s. That's why /spawn raises
FileNotFoundError for characters that haven't happened to spawn (and
get cached) since before the rename.

This script walks every row in the characters table, looks up the
CURRENT correct URL for that name in soul.py's CHARACTER_IMAGES, and
updates the DB row if it's different. Safe to re-run - it only writes
when there's an actual mismatch, and it never touches
card_image_path/card_template_path (your manual /card art).

Run once from the project root (same folder as bot.py), with the bot
stopped or at least not spawning at the same moment:
    python fix_character_images.py
"""

from db import characters as ch
from db.connection import init_db
from soul import CHARACTER_IMAGES


def main():
    init_db()
    rows = ch.list_characters(enabled_only=False)

    updated = 0
    already_ok = 0
    no_mapping = 0

    for c in rows:
        correct_url = CHARACTER_IMAGES.get(c.name)
        if not correct_url:
            print(f"  ! no image mapped in soul.py for {c.name!r} - left untouched")
            no_mapping += 1
            continue
        if c.image_path == correct_url:
            already_ok += 1
            continue
        print(f"  * {c.name}: updating image_path")
        print(f"      old: {c.image_path}")
        print(f"      new: {correct_url}")
        ch.update_character_image(c.id, correct_url)
        updated += 1

    print("\n" + "=" * 50)
    print(f"Updated:        {updated}")
    print(f"Already correct:{already_ok}")
    print(f"No soul.py entry:{no_mapping}")
    print("=" * 50)
    if updated:
        print(
            "\nDone. The next time a fixed character spawns, "
            "fetch_image_bytes() will pull the corrected URL fresh - "
            "there's no cache folder to worry about anymore."
        )


if __name__ == "__main__":
    main()