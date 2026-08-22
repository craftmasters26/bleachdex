"""
server.py — runs the Discord bot, the admin panel, and the player
dashboard all in one process, on one port, behind one ngrok tunnel.

Why one Flask app instead of two: ngrok's free tier reliably supports
one live tunnel per account. Rather than build against an assumption
about whether a second simultaneous tunnel would work, the admin panel
(admin/app.py) and the player dashboard (web/dashboard.py) are both
mounted as Blueprints on a single app — admin under /admin, the
player-facing pages at the root. One port, one tunnel, no ambiguity.

Use this instead of run_all.py — it does the same job (bot + web
together in one process) but merges the two Flask apps into one.
bot.py and admin/app.py remain independently runnable/testable; this
file just wires them together via the on_ready_extra hook in bot.py.
"""

import asyncio
import logging
import threading

from flask import Flask

import config
from bot import BleachDexBot
from admin.app import admin_bp
from web.dashboard import dashboard_bp, init_dashboard

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("bleachdex.server")

app = Flask(__name__)
app.secret_key = config.ADMIN_PANEL_SECRET
app.register_blueprint(admin_bp)
app.register_blueprint(dashboard_bp)


def _run_flask():
    app.run(host="0.0.0.0", port=config.ADMIN_PANEL_PORT, use_reloader=False)


def _start_web(bot: BleachDexBot):
    """Runs once, from bot.py's on_ready_extra hook — so the web layer
    only comes up after the bot is actually connected, not before."""
    init_dashboard(bot, config.BASE_URL)

    threading.Thread(target=_run_flask, daemon=True).start()
    log.info(f"Flask running locally on port {config.ADMIN_PANEL_PORT}")

    if config.NGROK_AUTHTOKEN and config.NGROK_DOMAIN:
        try:
            from pyngrok import ngrok, conf
            conf.get_default().auth_token = config.NGROK_AUTHTOKEN
            public_url = ngrok.connect(
                config.ADMIN_PANEL_PORT, domain=config.NGROK_DOMAIN
            ).public_url
            log.info(f"Public URL: {public_url}")
        except Exception as e:
            log.error(f"ngrok tunnel failed to start: {e}")
    else:
        log.warning(
            "BLEACHDEX_NGROK_AUTHTOKEN / BLEACHDEX_NGROK_DOMAIN not set — "
            "the dashboard and API will only be reachable locally, not "
            "over the internet. The bot itself still works fine."
        )


async def main():
    bot = BleachDexBot(on_ready_extra=lambda: _start_web(bot))
    async with bot:
        await bot.start(config.DISCORD_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
