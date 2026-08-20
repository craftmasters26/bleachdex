"""
Shared Discord-related helpers used by multiple cogs.

Custom emojis are stored in the database as just the numeric emoji ID
(e.g. "123456789012345678") - the ID an admin copies from wherever
they uploaded it.

There are TWO different places a custom emoji can live, and they work
completely differently:

1. SERVER emojis - uploaded to a specific Discord server. The bot can
   only see these if it's actually a member of that server. discord.py
   caches these automatically; client.get_emoji(id) checks this cache.

2. APPLICATION emojis - uploaded via the Developer Portal's "Emojis"
   tab, tied to the bot application itself, not any server. These are
   NOT in client.get_emoji()'s cache at all - they have to be fetched
   separately via client.fetch_application_emojis() and cached here.
   This is almost certainly what you're using if you uploaded through
   the Developer Portal rather than right-clicking an emoji in a server.

resolve_emoji() checks both. The application-emoji cache is populated
by refresh_application_emoji_cache(), which bot.py calls once on
startup and cogs/emoji_admin.py calls again every time an admin adds
one (so a just-uploaded emoji works immediately, no restart needed).
"""

import discord

_app_emoji_cache: dict[str, discord.Emoji] = {}


async def refresh_application_emoji_cache(client: discord.Client) -> None:
    """Re-fetches the bot's application-owned emojis (Developer Portal
    -> Emojis tab) and caches them by ID so resolve_emoji() can find
    them synchronously. Call this on startup, and again any time you
    want newly-uploaded application emojis to work without a restart."""
    global _app_emoji_cache
    try:
        app_emojis = await client.fetch_application_emojis()
        _app_emoji_cache = {str(e.id): e for e in app_emojis}
    except discord.HTTPException:
        pass  # keep whatever we had cached before; don't crash the caller


def resolve_emoji(client: discord.Client, emoji_id: str) -> str:
    """
    Turns a stored emoji ID into a real, renderable Discord emoji mention.
    Checks server emojis (client.get_emoji) first, then application
    emojis (the local cache populated by refresh_application_emoji_cache).
    Returns "" if emoji_id is blank, not a valid integer, or the bot
    genuinely can't find that emoji anywhere.
    """
    if not emoji_id:
        return ""
    try:
        eid = int(emoji_id)
    except (ValueError, TypeError):
        return ""

    emoji_obj = client.get_emoji(eid)
    if emoji_obj:
        return str(emoji_obj)

    app_emoji = _app_emoji_cache.get(emoji_id)
    if app_emoji:
        return str(app_emoji)

    return ""