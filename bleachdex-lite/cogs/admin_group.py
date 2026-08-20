"""
Shared top-level /admin command group.

Every bot-admin-only command (character/weapon add+remove, edit/change,
force-spawn, emoji) attaches its own subgroup to THIS object via
parent=admin_group, so they all end up nested under one /admin command
tree instead of being scattered as separate top-level commands:

    /admin character add|remove
    /admin weapon add|remove
    /admin edit template|character|weapon
    /admin change character|weapon
    /admin spawn character|weapon
    /admin emoji add

Only bot.py registers this object to the command tree (once, in
setup_hook, after every extension has loaded and attached its
subgroups) - individual cogs just import admin_group and parent their
own Group()s off of it. Do NOT call bot.tree.add_command(admin_group)
anywhere else, or Discord will reject the duplicate registration.

/set spawn is NOT part of this - it's a server-admin command (anyone
with Administrator permission on their own server), not a bot-admin
command, so it stays as its own top-level group in cogs/spawn.py.
"""

from discord import app_commands

admin_group = app_commands.Group(
    name="admin",
    description="[Bot admin] Admin-only commands",
)