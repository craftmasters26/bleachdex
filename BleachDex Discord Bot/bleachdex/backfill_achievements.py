"""
One-off: run every player through the achievement check once, so anyone who
ALREADY qualifies for the new achievements gets them (and their KAN) now,
quietly, instead of being announced one by one in a channel the next time
they catch something.

Players who already hold an achievement are skipped by check_and_grant(),
so nothing is ever paid twice - it's safe to run this more than once.

    python3 backfill_achievements.py            # do it
    python3 backfill_achievements.py --dry-run  # just show what WOULD be granted
"""

import sys

from db.connection import init_db, get_connection
from db import achievements as ach


def main(dry_run: bool) -> None:
    init_db()  # applies the new catch_log column / index if the bot hasn't restarted yet
    conn = get_connection()
    try:
        ids = [r["discord_id"] for r in conn.execute("SELECT discord_id FROM players")]
    finally:
        conn.close()

    total_players = total_granted = total_kan = 0
    for discord_id in ids:
        if dry_run:
            already = ach.earned_keys(discord_id)
            progress = ach.Progress(discord_id)
            granted = [a for a in ach.ACHIEVEMENTS
                       if a.key not in already and a.progress_fn(progress) >= a.target()]
        else:
            granted = ach.check_and_grant(discord_id)
        if granted:
            total_players += 1
            total_granted += len(granted)
            total_kan += sum(a.kan_reward for a in granted)
            print(f"{discord_id}: " + ", ".join(a.name for a in granted))

    verb = "would grant" if dry_run else "granted"
    print(f"\n{verb} {total_granted} achievements to {total_players} players "
          f"({total_kan:,} KAN total)")


if __name__ == "__main__":
    main("--dry-run" in sys.argv)