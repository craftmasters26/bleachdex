"""
Web admin panel: add/manage characters AND weapons separately (per
your split), with image upload, position, tier, and optional emoji.

This is the point-and-click alternative to /character add and
/weapon add in Discord - both write to the same database.

This is a Blueprint, not a standalone app, so it can be mounted at
/admin alongside the player-facing dashboard in server.py - both
behind one process, one port, one tunnel.
"""

import sys
from pathlib import Path
from functools import wraps
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from flask import (
    Blueprint, render_template, request, redirect, url_for, session, flash,
)
from werkzeug.utils import secure_filename

import config
from db.connection import TIERS
from db import characters as ch, weapons as wp

UPLOAD_DIR = Path(__file__).parent / "static" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}

admin_bp = Blueprint(
    "admin", __name__,
    template_folder="templates",
    static_folder="static",
    url_prefix="/admin",
)


def _allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin.login"))
        return view(*args, **kwargs)
    return wrapped


def _save_image(file_storage, prefix: str) -> str:
    filename = secure_filename(file_storage.filename)
    dest = UPLOAD_DIR / f"{prefix}_{filename}"
    counter = 1
    while dest.exists():
        dest = UPLOAD_DIR / f"{prefix}_{filename}_{counter}"
        counter += 1
    file_storage.save(dest)
    return str(dest)


@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("password") == config.ADMIN_PANEL_PASSWORD:
            session["admin_logged_in"] = True
            return redirect(url_for("admin.index"))
        flash("Wrong password.")
    return render_template("login.html")


@admin_bp.route("/logout")
def logout():
    session.pop("admin_logged_in", None)
    return redirect(url_for("admin.login"))


@admin_bp.route("/")
@login_required
def index():
    characters = ch.list_characters(enabled_only=False)
    weapons = wp.list_weapons(enabled_only=False)
    return render_template("index.html", characters=characters, weapons=weapons, tiers=TIERS)


def _validate_common_fields(form, files, extra_stat: Optional[str]):
    """
    Shared validation for the add-character and add-weapon forms.
    `extra_stat` is 'hp' for characters (they need both hp and attack);
    weapons only use 'attack' as their attack_bonus.
    Returns (errors, cleaned_dict). cleaned_dict is only meaningful if errors is empty.
    """
    name = form.get("name", "").strip()
    attack = form.get("attack", "").strip()
    hp = form.get("hp", "").strip() if extra_stat == "hp" else "1"  # weapons don't need hp
    tier = form.get("tier", "common").strip()
    emoji = form.get("emoji", "").strip()
    image = files.get("image")

    errors = []
    if not name:
        errors.append("Name is required.")
    if not attack.isdigit() or int(attack) <= 0:
        errors.append("Attack must be a positive whole number.")
    if extra_stat == "hp" and (not hp.isdigit() or int(hp) <= 0):
        errors.append("HP must be a positive whole number.")
    if tier not in TIERS:
        errors.append(f"Tier must be one of: {', '.join(TIERS)}.")
    if emoji and not emoji.isdigit():
        errors.append(
            "Emoji ID must be the numeric ID of a custom emoji (right-click "
            "it in Discord with Developer Mode on → Copy Emoji ID), not the "
            "emoji itself."
        )
    if not image or image.filename == "":
        errors.append("An image is required.")
    elif not _allowed_file(image.filename):
        errors.append("Image must be png, jpg, jpeg, or webp.")

    cleaned = {
        "name": name,
        "attack": int(attack) if attack.isdigit() else 0,
        "hp": int(hp) if hp.isdigit() else 0,
        "tier": tier, "emoji": emoji,
    }
    return errors, cleaned


# ---------- Characters ----------

@admin_bp.route("/characters/add", methods=["GET", "POST"])
@login_required
def add_character():
    if request.method == "POST":
        errors, cleaned = _validate_common_fields(request.form, request.files, extra_stat="hp")
        if errors:
            for e in errors:
                flash(e)
            return render_template("add_character.html", form=request.form, tiers=TIERS)

        image_path = _save_image(request.files["image"], cleaned["name"].lower().replace(" ", "_"))
        ch.add_character(
            name=cleaned["name"],
            image_path=image_path,
            hp=cleaned["hp"],
            attack=cleaned["attack"],
            tier=cleaned["tier"],
            emoji=cleaned["emoji"],
            ability_name=request.form.get("ability_name", "").strip(),
            ability_description=request.form.get("ability_description", "").strip(),
        )
        flash(f"Added character {cleaned['name']}!")
        return redirect(url_for("admin.index"))

    return render_template("add_character.html", form={}, tiers=TIERS)


@admin_bp.route("/characters/delete/<int:character_id>", methods=["POST"])
@login_required
def delete_character(character_id: int):
    ch.delete_character(character_id)
    flash("Character disabled.")
    return redirect(url_for("admin.index"))


# ---------- Weapons ----------

@admin_bp.route("/weapons/add", methods=["GET", "POST"])
@login_required
def add_weapon():
    if request.method == "POST":
        errors, cleaned = _validate_common_fields(request.form, request.files, extra_stat=None)
        if errors:
            for e in errors:
                flash(e)
            return render_template("add_weapon.html", form=request.form, tiers=TIERS)

        image_path = _save_image(request.files["image"], "weapon_" + cleaned["name"].lower().replace(" ", "_"))
        wp.add_weapon(
            name=cleaned["name"],
            image_path=image_path,
            attack_bonus=cleaned["attack"],
            tier=cleaned["tier"],
            emoji=cleaned["emoji"],
        )
        flash(f"Added weapon {cleaned['name']}!")
        return redirect(url_for("admin.index"))

    return render_template("add_weapon.html", form={}, tiers=TIERS)


@admin_bp.route("/weapons/delete/<int:weapon_id>", methods=["POST"])
@login_required
def delete_weapon(weapon_id: int):
    wp.delete_weapon(weapon_id)
    flash("Weapon disabled.")
    return redirect(url_for("admin.index"))

