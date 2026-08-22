"""
run_all.py — kept for backward compatibility.

The bot + admin panel + player dashboard are now merged into one
Flask app (server.py), since a second simultaneous ngrok tunnel isn't
reliably available on the free tier. This file just points at that.

Use `python3 server.py` directly going forward — this still works
the same way if you're used to typing run_all.py out of habit.
"""

from server import main
import asyncio

if __name__ == "__main__":
    asyncio.run(main())
