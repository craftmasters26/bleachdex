"""
/team add - build a 3-character team and save it into one of your 2
team slots.

Flow:
  1. /team add -> a message with 2 "Slot" buttons and 3 "Character"
     buttons. Tapping a Character button opens a small text box - type
     the character's name (full or partial) and it's looked up across
     your WHOLE collection, not just a pre-built list. This is
     deliberate: Discord select menus cap out at 25 options, which
     used to mean only your 25 most recently caught characters (and
     less than that if you'd caught duplicates) were even reachable.
     Touch the 3 Character buttons in any order, then hit Next.
  2. Next -> a dropdown per character to optionally equip a weapon on
     it (same effect as /equip - "No weapon" leaves it as-is). Weapon
     collections are usually much smaller, so this step still uses a
     dropdown (capped at 25, grouped "Name xN" for duplicates same as
     before) rather than the search box.
  3. Save team -> writes the 3 slots into team_presets and equips
     whichever weapons were picked, then confirms what was saved.

Note: a bare "/team" (no subcommand at all) isn't something Discord
lets a command group do - "team" has to be a group's *name* for
/team use, /team show, and /team list to exist alongside it, and a
group name by itself is never directly runnable. /team add is the
closest to that: it takes no typed arguments anymore and immediately
opens the dropdown flow above.

/team use - switch which of your 2 presets is "active" (the one
/battle and /admin bossbattle's Challenge button actually read).
/team show - view one preset (or your active one).
/team list - quick overview of both presets at once.
"""

from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from db import collection as coll, teams, characters as ch, weapons as wp

PRESET_RANGE = app_commands.Range[int, 1, 2]


async def _verify_owner(view_owner_id: int, interaction: discord.Interaction) -> bool:
    """Guards every callback below against acting on the wrong
    person's in-progress team-builder. In a normal Discord client an
    ephemeral message's components are only clickable by the person
    who triggered them, but this makes that explicit instead of
    silently assuming it, and gives a clear message instead of a
    confusing failure if it's ever wrong."""
    if interaction.user.id != view_owner_id:
        await interaction.response.send_message(
            "This isn't your team-builder — run `/team add` yourself.", ephemeral=True
        )
        return False
    return True


class _SlotButton(discord.ui.Button):
    def __init__(self, view: "_TeamSlotView", slot: int):
        super().__init__(
            label=f"Slot {slot}",
            style=discord.ButtonStyle.primary if view.preset == slot else discord.ButtonStyle.secondary,
            row=0,
        )
        self.slot = slot

    async def callback(self, interaction: discord.Interaction):
        view: "_TeamSlotView" = self.view
        if not await _verify_owner(view.owner_id, interaction):
            return
        view.preset = self.slot
        for child in view.children:
            if isinstance(child, _SlotButton):
                child.style = discord.ButtonStyle.primary if child.slot == view.preset else discord.ButtonStyle.secondary
        await interaction.response.edit_message(view=view)


class _CharacterButton(discord.ui.Button):
    """A slot's "Character N" control. Tapping it opens a small text
    box (a modal) to type the character's name, instead of a dropdown
    - this is what actually removes the 25-option cap, since the
    lookup searches the player's whole collection in the database
    rather than a pre-built list of 25 SelectOptions."""

    def __init__(self, view: "_TeamSlotView", index: int):
        super().__init__(
            label=f"Character {index + 1}: tap to pick",
            style=discord.ButtonStyle.secondary,
            row=index + 1,
        )
        self.index = index

    async def callback(self, interaction: discord.Interaction):
        view: "_TeamSlotView" = self.view
        if not await _verify_owner(view.owner_id, interaction):
            return
        await interaction.response.send_modal(_CharacterNameModal(view, self))


class _CharacterNameModal(discord.ui.Modal):
    def __init__(self, view: "_TeamSlotView", button: "_CharacterButton"):
        super().__init__(title=f"Character {button.index + 1}")
        self.view_ref = view
        self.button = button
        self.name_input = discord.ui.TextInput(
            label="Character name",
            placeholder="e.g. Ichigo Kurosaki — full or partial name works",
            max_length=100,
        )
        self.add_item(self.name_input)

    async def on_submit(self, interaction: discord.Interaction):
        view = self.view_ref
        query = self.name_input.value.strip()
        # Every owned COPY matching the text (not one per name) - so we can
        # hand out a copy that isn't already sitting in another slot.
        copies = coll.find_owned_character_instances_matching(view.owner_id, query)

        if not copies:
            await interaction.response.send_message(
                f'You don\'t own a character matching "{query}".', ephemeral=True
            )
            return

        distinct_character_ids = list(dict.fromkeys(c.character_id for c in copies))
        if len(distinct_character_ids) > 1:
            names = ", ".join(ch.get_character(cid).name for cid in distinct_character_ids[:10])
            await interaction.response.send_message(
                f'"{query}" matches more than one character: {names}. '
                f"Type more of the name to narrow it down.",
                ephemeral=True,
            )
            return

        # Copies already used by the OTHER two slots are off-limits. (This
        # button's own current pick doesn't count - re-picking it is fine.)
        used_elsewhere = {
            cid for i, cid in enumerate(view.char_ids)
            if cid is not None and i != self.button.index
        }
        free = [c for c in copies if c.id not in used_elsewhere]
        if not free:
            name = ch.get_character(copies[0].character_id).name
            await interaction.response.send_message(
                f"You only own {len(copies)}x **{name}** and "
                f"{'it is' if len(copies) == 1 else 'all of them are'} already in this team.",
                ephemeral=True,
            )
            return

        inst = free[0]
        view.char_ids[self.button.index] = inst.id
        self.button.label = f"Character {self.button.index + 1}: {ch.get_character(inst.character_id).name}"[:80]
        self.button.style = discord.ButtonStyle.success
        await interaction.response.edit_message(view=view)


class _NextButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Next: weapons", style=discord.ButtonStyle.success, row=0)

    async def callback(self, interaction: discord.Interaction):
        view: "_TeamSlotView" = self.view
        if not await _verify_owner(view.owner_id, interaction):
            return

        if any(c is None for c in view.char_ids):
            await interaction.response.send_message("Pick all 3 characters first.", ephemeral=True)
            return

        if len(set(view.char_ids)) != len(view.char_ids):
            await interaction.response.send_message(
                "The same character copy is in more than one slot — pick 3 different ones.",
                ephemeral=True,
            )
            return

        chosen = [coll.get_owned_character_instance(cid) for cid in view.char_ids]
        # Existing-but-no-longer-yours counts too: a traded character keeps
        # its id, it just changes owner.
        if any(c is None or c.owner_discord_id != view.owner_id for c in chosen):
            # A picked character stopped existing between opening /team add
            # and hitting Next (e.g. traded away mid-flow). Previously this
            # crashed the interaction silently instead of telling you why
            # nothing happened - now it says so and lets you retry cleanly.
            await interaction.response.send_message(
                "One of the characters you picked isn't in your collection "
                "anymore — run `/team add` again to refresh the list.",
                ephemeral=True,
            )
            return

        weapon_view = _TeamWeaponView(view.owner_id, view.preset, chosen)
        await interaction.response.edit_message(
            content=weapon_view.render_content(), view=weapon_view
        )


class _TeamSlotView(discord.ui.View):
    """Step 1: which of your 2 slots, and which 3 characters. Character
    picking is search-by-name (see _CharacterButton/_CharacterNameModal)
    rather than a pre-built list, so this view no longer needs to be
    handed the player's full collection up front."""

    def __init__(self, owner_id: int, default_preset: int):
        super().__init__(timeout=300)
        self.owner_id = owner_id
        self.preset = default_preset
        self.char_ids: list[Optional[int]] = [None, None, None]

        self.add_item(_SlotButton(self, 1))
        self.add_item(_SlotButton(self, 2))
        for i in range(3):
            self.add_item(_CharacterButton(self, i))
        self.add_item(_NextButton())


class _WeaponButton(discord.ui.Button):
    """A slot's weapon control - same tap-to-search pattern as
    _CharacterButton, for the same reason: no cap on how many weapons
    you can reach, and no confusing duplicate-name suffixes."""

    def __init__(self, view: "_TeamWeaponView", index: int, char_label: str):
        super().__init__(
            label=f"Weapon for {char_label}: none",
            style=discord.ButtonStyle.secondary,
            row=index,
        )
        self.index = index
        self.char_label = char_label

    async def callback(self, interaction: discord.Interaction):
        view: "_TeamWeaponView" = self.view
        if not await _verify_owner(view.owner_id, interaction):
            return
        await interaction.response.send_modal(_WeaponNameModal(view, self))


class _WeaponNameModal(discord.ui.Modal):
    def __init__(self, view: "_TeamWeaponView", button: "_WeaponButton"):
        super().__init__(title=f"Weapon for {button.char_label}"[:45])
        self.view_ref = view
        self.button = button
        self.name_input = discord.ui.TextInput(
            label="Weapon name (blank to unequip)",
            placeholder="e.g. Zangetsu — full or partial name works",
            max_length=100,
            required=False,
        )
        self.add_item(self.name_input)

    async def on_submit(self, interaction: discord.Interaction):
        view = self.view_ref
        query = self.name_input.value.strip()

        if not query:
            view.weapon_ids[self.button.index] = None
            self.button.label = f"Weapon for {self.button.char_label}: none"
            self.button.style = discord.ButtonStyle.secondary
            await interaction.response.edit_message(view=view)
            return

        copies = coll.find_owned_weapon_instances_matching(view.owner_id, query)

        if not copies:
            await interaction.response.send_message(
                f'You don\'t own a weapon matching "{query}".', ephemeral=True
            )
            return

        distinct_weapon_ids = list(dict.fromkeys(c.weapon_id for c in copies))
        if len(distinct_weapon_ids) > 1:
            names = ", ".join(wp.get_weapon(wid).name for wid in distinct_weapon_ids[:10])
            await interaction.response.send_message(
                f'"{query}" matches more than one weapon: {names}. '
                f"Type more of the name to narrow it down.",
                ephemeral=True,
            )
            return

        # One copy of a weapon can only be on one character: skip copies
        # already picked for another slot here, and prefer copies that
        # aren't currently equipped on someone outside this team.
        used_elsewhere = {
            wid for i, wid in enumerate(view.weapon_ids)
            if wid is not None and i != self.button.index
        }
        free = [c for c in copies if c.id not in used_elsewhere]
        if not free:
            name = wp.get_weapon(copies[0].weapon_id).name
            await interaction.response.send_message(
                f"You only own {len(copies)}x **{name}** and "
                f"{'it is' if len(copies) == 1 else 'all of them are'} already picked for another character.",
                ephemeral=True,
            )
            return

        team_char_ids = {c.id for c in view.chars}
        equipped_on = coll.get_equipped_weapon_map(view.owner_id)

        def _held_by_outsider(c) -> bool:
            holder = equipped_on.get(c.id)
            return holder is not None and holder not in team_char_ids

        free.sort(key=_held_by_outsider)  # stable: newest-first order otherwise kept
        inst = free[0]
        view.weapon_ids[self.button.index] = inst.id
        self.button.label = f"Weapon for {self.button.char_label}: {wp.get_weapon(inst.weapon_id).name}"[:80]
        self.button.style = discord.ButtonStyle.success
        await interaction.response.edit_message(view=view)


class _BackButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Back", style=discord.ButtonStyle.secondary, row=3)

    async def callback(self, interaction: discord.Interaction):
        view: "_TeamWeaponView" = self.view
        if not await _verify_owner(view.owner_id, interaction):
            return
        # Note: previously this rebuilt the character step from only the
        # 3 already-chosen characters (whatever was passed in when this
        # view was built), so hitting Back would strand you with just
        # those 3 to re-pick from instead of your full collection. The
        # search-by-name picker below no longer needs a pre-built list
        # at all, so Back now always has access to everything you own.
        slot_view = _TeamSlotView(view.owner_id, view.preset)
        await interaction.response.edit_message(
            content="Pick a slot and your 3 characters.", view=slot_view
        )


class _SaveButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Save team", style=discord.ButtonStyle.success, row=3)

    async def callback(self, interaction: discord.Interaction):
        view: "_TeamWeaponView" = self.view
        if not await _verify_owner(view.owner_id, interaction):
            return

        picked_weapons = [w for w in view.weapon_ids if w is not None]
        if len(set(picked_weapons)) != len(picked_weapons):
            await interaction.response.send_message(
                "The same weapon is picked for more than one character — "
                "a weapon can only be equipped on one character at a time.",
                ephemeral=True,
            )
            return

        try:
            # Validates 3 DIFFERENT copies, all still owned, and writes the
            # 3 slots in one transaction.
            teams.set_team(view.owner_id, view.preset, [inst.id for inst in view.chars])
            for inst, weapon_instance_id in zip(view.chars, view.weapon_ids):
                if weapon_instance_id is not None:
                    coll.equip_weapon(inst.id, weapon_instance_id, view.owner_id)
                else:
                    # A blank weapon button now genuinely unequips instead
                    # of silently doing nothing - the buttons pre-fill from
                    # whatever's currently equipped, so "blank" is always a
                    # deliberate clear, not just "untouched". Harmless no-op
                    # if the character had nothing equipped anyway.
                    coll.unequip_weapon(inst.id, view.owner_id)
        except Exception as e:
            # Previously any failure here (bad weapon id, DB error, etc.)
            # just made the interaction fail with no message at all, which
            # looked exactly like "the team didn't save" with zero
            # explanation. Now the actual reason gets shown.
            await interaction.response.send_message(
                f"Couldn't save the team: {e}", ephemeral=True
            )
            return

        # Read the team back from the DB rather than trusting the writes
        # above succeeded - if this comes back empty, something is wrong
        # and the player is told immediately instead of seeing a "Saved"
        # message for a team that isn't actually there.
        saved = teams.get_team(view.owner_id, preset=view.preset)
        if saved is None:
            await interaction.response.send_message(
                "Something went wrong and the team wasn't actually saved. "
                "Please try `/team add` again.",
                ephemeral=True,
            )
            return

        for child in view.children:
            child.disabled = True

        names = ", ".join(ch.get_character(c.character_id).name for c in view.chars)
        active_note = ""
        if teams.get_active_preset(view.owner_id) != view.preset:
            active_note = f"\n-# Your active slot is still {teams.get_active_preset(view.owner_id)} — use `/team use` to switch to {view.preset}."
        await interaction.response.edit_message(
            content=f"Saved **slot {view.preset}**: {names}.{active_note}", view=view
        )


class _TeamWeaponView(discord.ui.View):
    """Step 2: optionally equip a weapon on each of the 3 characters
    just picked, then save everything in one go."""

    def __init__(self, owner_id: int, preset: int, chars: list):
        super().__init__(timeout=300)
        self.owner_id = owner_id
        self.preset = preset
        self.chars = chars  # 3 OwnedCharacter, in slot order (always 3 different copies)
        self.weapon_ids: list[Optional[int]] = [None, None, None]

        claimed_weapons: set[int] = set()
        for i, inst in enumerate(chars):
            name = ch.get_character(inst.character_id).name
            label = f"{name} (Slot {i + 1})"
            btn = _WeaponButton(self, i, label)
            # Reflect whatever's already equipped, if anything, instead of
            # always starting blank - otherwise typing nothing and hitting
            # Save would look like a no-op even though the modal invites
            # you to blank it out to unequip.
            if inst.equipped_weapon_instance_id is not None and inst.equipped_weapon_instance_id not in claimed_weapons:
                equipped = coll.get_owned_weapon_instance(inst.equipped_weapon_instance_id)
                if equipped is not None:
                    claimed_weapons.add(equipped.id)
                    self.weapon_ids[i] = equipped.id
                    btn.label = f"Weapon for {label}: {wp.get_weapon(equipped.weapon_id).name}"[:80]
                    btn.style = discord.ButtonStyle.success
            self.add_item(btn)

        self.add_item(_BackButton())
        self.add_item(_SaveButton())

    def render_content(self) -> str:
        names = ", ".join(ch.get_character(c.character_id).name for c in self.chars)
        return f"**Slot {self.preset}:** {names}\nPick a weapon for each (optional), then Save team."


class TeamGroup(app_commands.Group):
    def __init__(self):
        super().__init__(name="team", description="Save and manage your 2 saved teams")

    @app_commands.command(
        name="add",
        description="Build a team by name and save it into one of your 2 slots",
    )
    async def add(self, interaction: discord.Interaction):
        character_count = len(coll.list_owned_characters(interaction.user.id))
        if character_count < 3:
            await interaction.response.send_message(
                "You need at least 3 characters in your collection to build a team.",
                ephemeral=True,
            )
            return

        default_preset = teams.get_active_preset(interaction.user.id)
        if default_preset not in (1, 2):
            default_preset = 1

        view = _TeamSlotView(interaction.user.id, default_preset)
        await interaction.response.send_message(
            content=(
                "Pick a slot, then tap each Character button and type a name "
                "(full or partial - works across your whole collection, not just "
                "recent catches)."
            ),
            view=view,
            ephemeral=True,
        )

    @app_commands.command(name="use", description="Switch which of your 2 saved slots is active for battles")
    @app_commands.describe(preset="Which slot (1-2) to make active")
    async def use(self, interaction: discord.Interaction, preset: PRESET_RANGE):
        teams.set_active_preset(interaction.user.id, preset)
        team = teams.get_team(interaction.user.id, preset=preset)
        if team is None:
            await interaction.response.send_message(
                f"Slot **{preset}** is now active, but it isn't fully set yet — "
                f"use `/team add` to fill it.",
                ephemeral=True,
            )
            return

        names = ", ".join(ch.get_character(inst.character_id).name for inst in team)
        await interaction.response.send_message(f"Slot **{preset}** is now active: {names}.")

    @app_commands.command(name="show", description="Show one of your saved teams (defaults to your active slot)")
    @app_commands.describe(preset="Which slot (1-2) to show - leave empty for your active slot")
    async def show(self, interaction: discord.Interaction, preset: Optional[PRESET_RANGE] = None):
        shown_preset = preset if preset is not None else teams.get_active_preset(interaction.user.id)
        team = teams.get_team(interaction.user.id, preset=shown_preset)
        if team is None:
            await interaction.response.send_message(
                f"You haven't set a full 3-character team in slot **{shown_preset}** yet — "
                f"use `/team add` first.",
                ephemeral=True,
            )
            return

        lines = []
        for slot, inst in enumerate(team, start=1):
            char = ch.get_character(inst.character_id)
            weapon_note = ""
            if inst.equipped_weapon_instance_id:
                w_inst = coll.get_owned_weapon_instance(inst.equipped_weapon_instance_id)
                weapon = wp.get_weapon(w_inst.weapon_id) if w_inst else None
                if weapon:
                    weapon_note = f" (+ {weapon.name})"
            lines.append(
                f"**Slot {slot}:** {char.name} — {inst.health} HP / "
                f"{inst.attack} ATK{weapon_note}"
            )

        active_flag = " (active)" if shown_preset == teams.get_active_preset(interaction.user.id) else ""
        embed = discord.Embed(
            title=f"{interaction.user.display_name}'s team — slot {shown_preset}{active_flag}",
            description="\n".join(lines),
            color=discord.Color.teal(),
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="list", description="Quick overview of both of your saved team slots")
    async def list_presets(self, interaction: discord.Interaction):
        active = teams.get_active_preset(interaction.user.id)
        presets = teams.list_presets(interaction.user.id)

        lines = []
        for preset in (1, 2):
            flag = " (active)" if preset == active else ""
            team = presets[preset]
            if team is None:
                lines.append(f"**Slot {preset}:** *empty*{flag}")
            else:
                names = ", ".join(ch.get_character(inst.character_id).name for inst in team)
                lines.append(f"**Slot {preset}:** {names}{flag}")

        embed = discord.Embed(
            title=f"{interaction.user.display_name}'s saved teams",
            description="\n".join(lines),
            color=discord.Color.teal(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


class Team(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.bot.tree.add_command(TeamGroup())


async def setup(bot: commands.Bot):
    await bot.add_cog(Team(bot))