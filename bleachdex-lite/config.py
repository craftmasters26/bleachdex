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
