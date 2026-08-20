"""
web/dashboard.py — player-facing web dashboard.

Discord OAuth login so a player can see their own KAN coin balance and
collection from a browser. Separate from admin/app.py (that's for
adding characters/weapons); this is for players looking at their own
stuff. Also exposes two public, read-only JSON endpoints the marketing
site's live sections call: /api/leaderboard and /api/stats.

Mounted at the site root by server.py, alongside the admin blueprint
at /admin — one Flask app, one port, one tunnel.
"""

from __future__ import annotations

import time
import secrets
import requests
from flask import Blueprint, request, redirect, session, jsonify, url_for

import config
from db.connection import get_connection
from db.players import get_player

dashboard_bp = Blueprint("dashboard", __name__)

DISCORD_API = "https://discord.com/api"

# Set by server.py once it knows the bot instance and the public base URL.
_bot_ref = None
_base_url = ""


def init_dashboard(bot, base_url: str):
    global _bot_ref, _base_url
    _bot_ref = bot
    _base_url = base_url.rstrip("/")


def _redirect_uri() -> str:
    return f"{_base_url}/callback"


SITE_STYLE = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Shippori+Mincho:wght@400;600;700;800&family=Manrope:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root{
  --void:#0a0906; --void-raised:#131009; --void-line:#241f14;
  --bone:#e9dfc7; --bone-dim:#a99c7c; --bone-faint:#6b6350;
  --vermillion:#c23b1c; --vermillion-bright:#e8531f;
  --gold:#c8a334; --gold-bright:#f0cf6a;
}
*{box-sizing:border-box;}
body{background:var(--void);color:var(--bone);font-family:'Manrope',sans-serif;margin:0;padding:60px 24px;min-height:100vh;}
.wrap{max-width:640px;margin:0 auto;}
h1{font-family:'Shippori Mincho',serif;font-size:36px;margin:0 0 8px;}
h2{font-family:'Shippori Mincho',serif;font-size:16px;color:var(--vermillion-bright);margin:0 0 6px;text-transform:uppercase;letter-spacing:.06em;}
p{line-height:1.6;color:var(--bone-dim);}
a.btn{display:inline-block;background:var(--vermillion);color:var(--bone);padding:14px 28px;border-radius:4px;text-decoration:none;font-weight:700;border:1px solid var(--vermillion-bright);}
a.btn:hover{background:var(--vermillion-bright);}
a.btn-ghost{display:inline-block;color:var(--bone-dim);padding:10px 0;text-decoration:none;font-family:'JetBrains Mono',monospace;font-size:13px;}
.card{background:var(--void-raised);border:1px solid var(--void-line);border-radius:6px;padding:22px 24px;margin:16px 0;}
.card .stat{font-family:'JetBrains Mono',monospace;font-size:30px;color:var(--gold-bright);font-weight:700;}
.card .sub{font-size:13px;color:var(--bone-faint);margin-top:4px;}
.stat-row{display:flex;gap:32px;flex-wrap:wrap;}
.stat-row > div{flex:1;min-width:130px;}
.userbar{display:flex;align-items:center;gap:14px;margin-bottom:36px;}
.userbar img{width:52px;height:52px;border-radius:50%;border:2px solid var(--void-line);}
.userbar .name{font-weight:700;font-size:18px;}
.list-item{display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--void-line);font-size:14px;}
.list-item:last-child{border-bottom:none;}
</style>
"""


@dashboard_bp.route("/")
def home():
    return f"""
    <html><head><title>BleachDex</title>{SITE_STYLE}</head>
    <body><div class="wrap" style="text-align:center;padding-top:60px;">
      <h1>BleachDex</h1>
      <p>Log in with Discord to view your KAN coins and collection.</p>
      <br><a class="btn" href="/login">Log in with Discord</a>
      <br><br><a class="btn-ghost" href="/api/leaderboard">View live leaderboard JSON →</a>
    </div></body></html>
    """


@dashboard_bp.route("/login")
def login():
    if not config.OAUTH_CLIENT_ID:
        return "Discord login is not configured (missing CLIENT_ID).", 503
    url = (
        f"{DISCORD_API}/oauth2/authorize?client_id={config.OAUTH_CLIENT_ID}"
        f"&redirect_uri={_redirect_uri()}&response_type=code&scope=identify"
    )
    return redirect(url)


@dashboard_bp.route("/callback")
def callback():
    code = request.args.get("code")
    if not code:
        return "Missing code.", 400

    data = {
        "client_id": config.OAUTH_CLIENT_ID,
        "client_secret": config.OAUTH_CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": _redirect_uri(),
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    token_res = requests.post(f"{DISCORD_API}/oauth2/token", data=data, headers=headers)
    if token_res.status_code != 200:
        return f"OAuth token exchange failed: {token_res.text}", 400
    access_token = token_res.json().get("access_token")

    user_res = requests.get(
        f"{DISCORD_API}/users/@me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    if user_res.status_code != 200:
        return "Failed to fetch user.", 400
    user = user_res.json()

    user_id = user.get("id")
    if not user_id:
        return "Failed to get user", 400

    session["user_id"] = user_id
    session["username"] = user.get("global_name") or user.get("username") or user_id
    session["avatar"] = user.get("avatar")
    session["discriminator"] = user.get("discriminator")
    session.permanent = True
    return redirect(url_for("dashboard.dashboard"))


@dashboard_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("dashboard.home"))


@dashboard_bp.route("/dashboard")
def dashboard():
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("dashboard.login"))

    player = get_player(int(user_id))

    username = session.get("username") or user_id
    avatar_hash = session.get("avatar")
    if avatar_hash:
        avatar_url = f"https://cdn.discordapp.com/avatars/{user_id}/{avatar_hash}.png?size=128"
    else:
        try:
            idx = int(session.get("discriminator") or 0) % 5
        except (TypeError, ValueError):
            idx = 0
        avatar_url = f"https://cdn.discordapp.com/embed/avatars/{idx}.png"

    conn = get_connection()
    try:
        char_count = conn.execute(
            "SELECT COUNT(*) AS n FROM owned_characters WHERE owner_discord_id = ?",
            (int(user_id),),
        ).fetchone()["n"]
        weapon_count = conn.execute(
            "SELECT COUNT(*) AS n FROM owned_weapons WHERE owner_discord_id = ?",
            (int(user_id),),
        ).fetchone()["n"]
        unique_chars = conn.execute(
            "SELECT COUNT(DISTINCT character_id) AS n FROM owned_characters WHERE owner_discord_id = ?",
            (int(user_id),),
        ).fetchone()["n"]
    finally:
        conn.close()

    return f"""
    <html><head><title>Dashboard | BleachDex</title>{SITE_STYLE}</head>
    <body><div class="wrap">
        <div class="userbar">
          <img src="{avatar_url}" alt="">
          <div><div class="name">{username}</div></div>
        </div>
        <div class="card">
          <h2>KAN Coins</h2>
          <div class="stat">{player['kan_coins']:,}</div>
          <div class="sub">Earned from /daily · spent in future shop features</div>
        </div>
        <div class="card">
          <h2>Collection</h2>
          <div class="stat-row">
            <div><div class="stat">{char_count:,}</div><div class="sub">Characters owned</div></div>
            <div><div class="stat">{unique_chars:,}</div><div class="sub">Unique characters</div></div>
            <div><div class="stat">{weapon_count:,}</div><div class="sub">Zanpakutō owned</div></div>
          </div>
        </div>
        <br><a class="btn-ghost" href="/logout">Log out</a>
    </div></body></html>
    """


# ---------------------------------------------------------------
# Public JSON API — used by the marketing site's live sections.
# ---------------------------------------------------------------

@dashboard_bp.route("/api/leaderboard")
def api_leaderboard():
    """Public, read-only. Top collectors by total owned characters."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT owner_discord_id, COUNT(*) AS total
            FROM owned_characters
            GROUP BY owner_discord_id
            ORDER BY total DESC
            LIMIT 10
            """
        ).fetchall()
    finally:
        conn.close()

    def resolve_name(uid: int) -> str:
        if _bot_ref:
            user = _bot_ref.get_user(int(uid))
            if user:
                return user.global_name or user.name
        return f"Player {str(uid)[-4:]}"

    return jsonify({
        "generated_at": time.time(),
        "top_collectors": [
            {"rank": i + 1, "name": resolve_name(r["owner_discord_id"]), "cards": r["total"]}
            for i, r in enumerate(rows)
        ],
        # No global battle-win tracking exists yet in this rebuild
        # (battles don't record a persistent winner count) — empty for now.
        "top_battlers": [],
    })


@dashboard_bp.route("/api/stats")
def api_stats():
    """Public, aggregate, non-identifying totals for the marketing site."""
    conn = get_connection()
    try:
        registered_players = conn.execute(
            "SELECT COUNT(*) AS n FROM players"
        ).fetchone()["n"]
        total_cards = conn.execute(
            "SELECT COUNT(*) AS n FROM owned_characters"
        ).fetchone()["n"]
    finally:
        conn.close()

    return jsonify({
        "generated_at": time.time(),
        "registered_players": registered_players,
        "total_cards_caught": total_cards,
        "total_battles_won": 0,  # not tracked yet in this rebuild
    })
