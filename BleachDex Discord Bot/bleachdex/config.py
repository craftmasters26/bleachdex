"""
All configuration comes from environment variables, so nothing secret
ever gets committed to your repo. Copy .env.example to .env and fill
it in locally, or set these in your host's dashboard (Render, Railway,
Wispbyte, etc. all have an "Environment Variables" section).
"""

import os

try:
    from dotenv import load_dotenv
    load_dotenv()  # loads .env for local development; no-op if the file doesn't exist
except ImportError:
    pass

DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN", "")
ADMIN_PANEL_SECRET = os.environ.get("ADMIN_PANEL_SECRET", "change-me")
ADMIN_PANEL_PASSWORD = os.environ.get("ADMIN_PANEL_PASSWORD", "change-me")
ADMIN_PANEL_PORT = int(os.environ.get("ADMIN_PANEL_PORT", "5000"))

# Optional: your Discord server's ID. When set, slash commands sync
# ONLY to that server and apply instantly (global syncs can take up to
# an hour to show up / stop erroring with CommandSignatureMismatch).
# Right-click your server icon in Discord (Developer Mode must be on
# under User Settings -> Advanced) -> "Copy Server ID".
DEV_GUILD_ID = os.environ.get("BLEACHDEX_DEV_GUILD_ID", "")

# The ID of your MAIN server (the one the invite link in cogs/spawn.py
# points to). Needed for the "Main Catcher" achievement - it's earned by
# catching a soul in this server. Right-click the server icon -> "Copy
# Server ID". Defaults to your main server; the env var overrides it.
MAIN_GUILD_ID = int(os.environ.get("BLEACHDEX_MAIN_GUILD_ID", "1523569183353208863") or 0)

# --- Player dashboard (Discord OAuth login) ---
# From https://discord.com/developers/applications -> your app -> OAuth2 tab.
OAUTH_CLIENT_ID = os.environ.get("BLEACHDEX_CLIENT_ID", "")
OAUTH_CLIENT_SECRET = os.environ.get("BLEACHDEX_CLIENT_SECRET", "")

# --- Public URL / tunnel (only needed if you want the dashboard and
# API reachable from outside your host, e.g. so the marketing site's
# live sections can reach it) ---
BASE_URL = os.environ.get("BLEACHDEX_BASE_URL", f"http://localhost:{ADMIN_PANEL_PORT}")
NGROK_AUTHTOKEN = os.environ.get("BLEACHDEX_NGROK_AUTHTOKEN", "")
NGROK_DOMAIN = os.environ.get("BLEACHDEX_NGROK_DOMAIN", "")

if not DISCORD_TOKEN:
    raise RuntimeError(
        "DISCORD_TOKEN is not set. Create a .env file (see .env.example) "
        "or set it in your host's environment variables."
    )