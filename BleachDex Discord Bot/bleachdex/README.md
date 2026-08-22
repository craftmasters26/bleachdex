# BleachDex-Lite

A single-process rewrite of the BallsDex feature set — pack pulls,
collection tracking, trading, battling, an admin panel — built to run
on hosts that only give you one process, like Wispbyte, Render's free
tier, or a cheap VPS. No Docker, no Postgres, no nginx.

## Feature list

**Roster (admin-managed, split as requested):**
- **Characters** — name, position, image, HP, attack, tier, optional
  ability name/description, optional custom emoji
- **Weapons** (Zanpakuto) — name, position, image, attack bonus, tier,
  optional custom emoji. Equip one onto a character to add its bonus
  in battle.
- Add either via a Discord slash command (`/character add`,
  `/weapon add` — admin-only) or the web admin panel. Both write to
  the same database.

**Rarity tiers** (common → uncommon → rare → epic → legendary →
mythic): mythic is pulled far less often than common. Tune the odds
in `db/connection.py` → `TIER_WEIGHTS`.

**Custom emoji:** when adding a character or weapon, `emoji_id` (or
the web form's "Custom emoji ID" field) expects the *numeric ID* of a
custom Discord emoji, not the emoji character itself — turn on
Developer Mode in Discord, right-click the emoji, and choose **Copy
Emoji ID**. The bot resolves that ID to a live emoji mention wherever
it's shown (`/pack`, `/collection`), so it always displays correctly
even for animated emojis.

**Teams & battling:**
- `/team add` — register your team of 3 owned characters
  (`character1/2/3`), optionally equipping a weapon onto each at the
  same time (`weapon1/2/3`)
- `/team show` — see your current team
- `/battle @opponent` — both of you need a full team set up first.
  Battles are 3v3: fighters go out in slot order, and a fighter who
  wins their 1v1 keeps their remaining HP into the next matchup. First
  team fully knocked out loses.

**Packs / economy:**
- `/pack daily` — 3 pulls per day, any tier, resets at UTC midnight
- `/pack weekly` — 1 pull per week, guaranteed Epic or Mythic
- `/daily` — claim KAN coins (once per 24h)
- `/balance` — check your (or someone else's) KAN coin balance

**Collection:**
- `/collection completion` — % owned, owned vs missing, shows each
  character's custom emoji if set
- `/collection inventory` — lists your owned characters and weapons by
  name (you'll need these names for `/trade`, `/equip`, `/battle`)

**Trading:**
- `/trade start` — propose a trade: you offer one item, they offer
  one item. **Both sides must press Accept** before anything moves.
  Either side can Decline/Cancel any time before it completes.

**Equipping:**
- `/equip` — attach an owned weapon to an owned character
- `/unequip` — remove it

**Battling:**
- `/battle @opponent` — both players pick a fighter from a dropdown,
  then a turn-based fight plays out (attack vs remaining HP, turns
  alternate) until someone hits 0. Equipped weapon bonuses apply.
  Doesn't consume or damage your cards — just for bragging rights
  right now. Say the word if you want stakes (wagered coins, loser
  gives up a card, etc.) added on top.

## Not included yet

- Per-server config (e.g. restricting commands to one channel)
- Spending KAN coins on anything (currently earn-only — tell me what
  you want it to buy: extra pack rolls? cosmetics? a shop?)
- Spawn-based catching (BallsDex's "first to click wins" mechanic) —
  this version is claim-based (`/pack daily`) instead

## Setup

1. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

2. Create a Discord bot application at
   https://discord.com/developers/applications, add a Bot user, and
   copy its token. Under installation/OAuth2, make sure the `bot` and
   `applications.commands` scopes are enabled when you invite it.

3. Copy `.env.example` to `.env` and fill in `DISCORD_TOKEN`, an admin
   panel password, and (optional) `ADMIN_USER_IDS` — a comma-separated
   list of Discord user IDs allowed to use `/character add` and
   `/weapon add` even without server Administrator permission.

## Running it

**Locally, both bot and admin panel together:**
```
python3 run_all.py
```

**As two separate processes** (recommended if your host allows more
than one process):
```
python3 bot.py
python3 admin/app.py
```

## Adding your first characters and weapons

Either:
- In Discord: `/character add` or `/weapon add` (admin-only) — upload
  the image directly as a Discord attachment, fill in the rest inline
- Or the web admin panel → "Add character" / "Add weapon"

Then `/pack daily` to test a pull.

## What's tested vs. what needs a live Discord connection

Everything in `db/`, `logic/battle.py`, `cards/render.py`, and
`admin/app.py` was actually run and asserted against in a sandbox
before being handed to you — tier-weighted pulls, the daily coin/pack
cooldowns, equip/unequip, a full two-sided trade (including that it
genuinely refuses to complete on a single accept), and the battle
simulator's win logic.

What I *can't* test without a real bot token and a real Discord
server: slash command registration, button/select-menu interactions,
and attachment uploads through Discord itself. Those are exercised
the first time you actually run the bot — if anything misbehaves
there, send me the error and I'll fix it.

## Deploying

Any host that runs a single long-lived Python process works — see the
earlier conversation for the Wispbyte / Oracle Cloud / Render
trade-offs. Start command: `python3 run_all.py`.

The SQLite file (`db/bleachdex.sqlite3`) is just a file — back it up
by copying it somewhere periodically. On hosts with ephemeral disks,
check whether your host offers a persistent volume, or your roster
and everyone's collections will reset on every redeploy.

## Project layout

```
bot.py                 - Discord bot entry point, loads all cogs
run_all.py              - runs bot + admin panel together (single process)
config.py               - reads settings from environment variables

db/connection.py        - schema + shared SQLite connection, tier weights
db/characters.py        - character CRUD + weighted random pull
db/weapons.py           - weapon CRUD + weighted random pull
db/players.py           - KAN coins, daily/weekly claim cooldowns
db/collection.py        - ownership, equip/unequip, trade transfers
db/trades.py            - two-sided trade state machine

logic/battle.py         - pure turn-based combat simulator (no Discord/DB)
cards/render.py         - renders the pack-pull card image (PIL)

cogs/packs.py            - /pack daily, /pack weekly
cogs/collection.py       - /collection completion, /collection inventory
cogs/economy.py          - /daily, /balance
cogs/admin_add.py        - /character add, /weapon add (admin-only)
cogs/trade.py            - /trade start (with Accept/Decline buttons)
cogs/battle.py           - /battle (fighter-select + turn-based sim)
cogs/equip.py            - /equip, /unequip
cogs/permissions.py      - admin-check helper

admin/app.py             - Flask admin panel
admin/templates/         - admin panel HTML
assets/backgrounds/      - card background image(s)
assets/fonts/            - drop custom TTF files here for nicer card text (optional)
```
