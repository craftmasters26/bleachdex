"""
Renders a character/weapon into a full stat card, using YOUR uploaded
template (card.png) as the background instead of a hardcoded size.

THE BUG THIS FIXES: the old version force-resized every template to a
fixed 900x1200 canvas, then pasted artwork into ARTWORK_BOX coordinates
that were only correct for that one hardcoded size. Your template is
1054x1492 - a different aspect ratio - so the force-resize distorted it
and the artwork landed in the wrong spot.

THE FIX: the canvas now always matches the template's OWN native size
(no resizing/distortion at all), and the artwork box is stored as
FRACTIONS of the template's width/height, not fixed pixels - measured
directly off your card.png's black inset box. That box works for your
current 1054x1492 template exactly, and will still scale sanely if you
ever swap in a different-sized template later.

TEXT STYLE: name / HP / attack / ability text are drawn "poster style" -
a solid offset drop-shadow copy behind a bright fill, both with a thin
black stroke - to match the punchy title-card look (see
_draw_poster_text). Font-wise this uses the boldest/most condensed fonts
found on the system (Poppins Bold / Bold Italic) since no font files
ship in assets/fonts/. If you drop your OWN .ttf files into
assets/fonts/ named title.ttf, stats.ttf, ability_label.ttf and
ability_body.ttf, those are used automatically instead - do that if you
want an exact match to a specific display/distressed font.
"""

import io
from pathlib import Path
from typing import Optional, Sequence, Tuple
from functools import lru_cache

import random

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from lru_bytes_cache import BoundedByteCache
from reiatsu import boosted_attack, boosted_hp, reiatsu_name

ASSETS_DIR = Path(__file__).parent.parent / "assets"
DEFAULT_BACKGROUND = ASSETS_DIR / "backgrounds" / "placeholder.png"
FONT_DIR = ASSETS_DIR / "fonts"

# Full rendered-card cache. render_card() is a pure function of its
# arguments plus whatever the active template currently is - so for
# the very common case of the same character/weapon being rendered
# again (repeat spawns, repeat pack pulls, viewing the same card
# twice), this skips the ENTIRE pipeline below: network fetch, PIL
# decode, LANCZOS resize, font fitting, and every poster-text draw
# call. Keyed to include the resolved template's own identity (path +
# mtime) so it self-invalidates the moment an admin swaps templates -
# never serves stale art after a template change.
_RENDER_CACHE = BoundedByteCache(max_bytes=40 * 1024 * 1024)  # 40MB


def _background_identity(template_override: str, faction: str) -> str:
    """Cheap (no image decode) mirror of _ensure_background()'s own
    resolution order, used only to build a cache key. Including each
    candidate path's mtime means even overwriting a file in place
    (same path, new content) correctly busts the cache."""
    if template_override and Path(template_override).exists():
        try:
            return f"override:{template_override}:{Path(template_override).stat().st_mtime_ns}"
        except OSError:
            return f"override:{template_override}"

    try:
        from db.connection import get_setting
        if faction:
            faction_path = get_setting(f"card_template_path:{faction}", "")
            if faction_path and Path(faction_path).exists():
                try:
                    return f"faction:{faction_path}:{Path(faction_path).stat().st_mtime_ns}"
                except OSError:
                    return f"faction:{faction_path}"

        custom_path = get_setting("card_template_path", "")
        if custom_path and Path(custom_path).exists():
            try:
                return f"custom:{custom_path}:{Path(custom_path).stat().st_mtime_ns}"
            except OSError:
                return f"custom:{custom_path}"
    except Exception:
        pass

    return "default"

# The artwork frame, measured from the card design: 189.3 x 116.6 on a
# 210 x 297 card. Stored as fractions of the canvas (not fixed pixels) so
# it lands on the template's drawn frame at ANY template resolution -
# all three templates in assets/backgrounds/ share this layout.
# Center is the frame's own center, measured off the template.
ARTWORK_BOX_SIZE_FRAC = (189.3 / 210, 116.6 / 297)
ARTWORK_CENTER_FRAC = (0.5014, 0.371)

# Plain ImageOps.fit only crops whichever single axis overflows once the
# OTHER axis is matched to the box - if the box's aspect ratio is close
# to the source screenshot's own aspect ratio (common for 16:9 anime
# caps), that leaves almost no vertical crop to work with, so a
# character sitting in the upper half of their source shot comes out
# with a slab of dead sky/background below them. ARTWORK_ZOOM scales
# the source up an extra bit beyond "just barely covers the box" so
# there's real crop room on BOTH axes, and ARTWORK_FOCUS_FRAC picks
# where in that crop room to sit - (0.5, 0.5) is a plain center crop,
# a smaller y biases toward the TOP of the source (keeps heads/faces,
# crops away floor/background at the bottom instead).
ARTWORK_ZOOM = 1.18
ARTWORK_FOCUS_FRAC = (0.5, 0.35)

TITLE_Y_FRAC = 0.030          # "Don Kanonji" name, above the box - pulled up a
                                # touch since the title is now bigger/bolder
TITLE_AREA_RIGHT_FRAC = 0.925  # name is centered within [TITLE_X_FRAC, this].
                                # Was 0.68 to dodge the faction emblem in the
                                # top-right corner, but the new template has
                                # no emblem, so the title can use the full
                                # width now (mirrors MARGIN_X_FRAC on the
                                # right side).
ABILITY_Y_FRAC = 0.605        # ability label ("ABILITY:"), just below the box
MARGIN_X_FRAC = 0.038
TITLE_X_FRAC = 0.075          # a bit further in than MARGIN_X_FRAC, so the
                               # name doesn't sit flush against the card's
                               # left wall like the ability text/stats do

# HP sits just to the RIGHT of the heart icon; attack sits just to the
# LEFT of the sword icon - measured directly off the heart/sword artwork
# baked into active_template.png (heart + its "+" flourishes span roughly
# x 0.06-0.22 of width; the sword icon spans roughly x 0.78-0.97).
# Both are baseline-anchored ("s") close to STATS_Y_FRAC so they sit low,
# right at the bottom corners next to the icons, instead of floating
# above them.
STATS_HP_X_FRAC = 0.235
STATS_ATTACK_X_FRAC = 0.765
STATS_Y_FRAC = 0.958

# No custom fonts ship with the repo, so these are the boldest faces
# actually installed on this system - swapped in automatically if you
# add real .ttf files under assets/fonts/ (see _load_font).
_BOLD_ITALIC_FALLBACKS = [
    "/usr/share/fonts/truetype/google-fonts/Poppins-BoldItalic.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-BoldOblique.ttf",
]
_BOLD_FALLBACKS = [
    "/usr/share/fonts/truetype/google-fonts/Poppins-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]

Color = Tuple[int, int, int, int]


def _cover_crop(
    img: Image.Image, box_w: int, box_h: int,
    zoom: float = 1.0, focus: Tuple[float, float] = (0.5, 0.5),
) -> Image.Image:
    """Like ImageOps.fit, but with an adjustable zoom and a focus point
    instead of always cropping dead-center. `zoom` > 1 scales the source
    up further beyond the minimum needed to cover the box, so there's
    slack to crop on BOTH axes instead of just whichever one overflows.
    `focus` is (x, y) in [0, 1] saying where in that slack to sit -
    (0.5, 0.5) is a plain center crop; (0.5, 0.35) keeps more of the top
    of the source and crops away more of the bottom."""
    scale = max(box_w / img.width, box_h / img.height) * zoom
    new_w = max(box_w, round(img.width * scale))
    new_h = max(box_h, round(img.height * scale))
    resized = img.resize((new_w, new_h), Image.LANCZOS)
    max_left = new_w - box_w
    max_top = new_h - box_h
    left = int(max_left * focus[0])
    top = int(max_top * focus[1])
    return resized.crop((left, top, left + box_w, top + box_h))


@lru_cache(maxsize=256)
def _load_font(name: str, size: int, italic: bool = False) -> ImageFont.FreeTypeFont:
    """Try a custom TTF first (assets/fonts/<name>), then the boldest
    system font available, then PIL's built-in default as a last resort.

    Cached: ImageFont.truetype() re-reads and re-parses the font file
    from disk on every call, and _fit_font_to_width() below calls this
    repeatedly while shrinking the size - without caching, one card
    render could do 15+ redundant disk reads/parses for fonts it just
    loaded a moment ago at a different size."""
    custom = FONT_DIR / name
    if custom.exists():
        return ImageFont.truetype(str(custom), size)
    for candidate in (_BOLD_ITALIC_FALLBACKS if italic else _BOLD_FALLBACKS):
        if Path(candidate).exists():
            try:
                return ImageFont.truetype(candidate, size)
            except OSError:
                continue
    try:
        return ImageFont.truetype("DejaVuSans-Bold.ttf", size)
    except OSError:
        return ImageFont.load_default(size=size)


def _fit_font_to_width(
    draw: ImageDraw.ImageDraw,
    text: str,
    font_name: str,
    start_size: int,
    min_size: int,
    max_width: int,
    italic: bool = False,
) -> ImageFont.FreeTypeFont:
    """Shrinks the font size (never below min_size) until `text` fits
    within max_width pixels. Used for the name so a long name doesn't
    run into the faction emblem in the top-right corner."""
    size = start_size
    font = _load_font(font_name, size, italic=italic)
    while size > min_size and draw.textlength(text, font=font) > max_width:
        size -= 2
        font = _load_font(font_name, size, italic=italic)
    return font


def _wrap_by_pixel_width(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
) -> list:
    """Greedy word-wrap using actual measured text width, instead of a
    rough character-count guess - bold/italic display fonts are wide
    enough that character counting badly overflows the card edge."""
    words = text.split()
    if not words:
        return []
    lines = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if draw.textlength(candidate, font=font) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _draw_poster_text(
    draw: ImageDraw.ImageDraw,
    xy: Tuple[int, int],
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: Color,
    shadow_fill: Color,
    shadow_offset: int,
    anchor: Optional[str] = None,
    stroke_width: int = 2,
    stroke_fill: Color = (0, 0, 0, 255),
) -> None:
    """Comic-title / poster look: a solid offset shadow copy of the text
    sits behind the real text, both outlined in black for crispness.
    That reads as a much punchier "title card" style than a thin single
    outline, closer to the reference card art."""
    x, y = xy
    draw.text(
        (x + shadow_offset, y + shadow_offset), text, font=font,
        fill=shadow_fill, stroke_width=stroke_width, stroke_fill=stroke_fill,
        anchor=anchor,
    )
    draw.text(
        (x, y), text, font=font,
        fill=fill, stroke_width=stroke_width, stroke_fill=stroke_fill,
        anchor=anchor,
    )


def _ensure_background(template_override: str = "", faction: str = "") -> Image.Image:
    """Returns the template image AT ITS OWN NATIVE SIZE - never resized
    here, so nothing gets distorted.

    Priority order:
      1. template_override - a character/weapon's OWN card_template_path,
         if it has one set via /admin edit character|weapon
      2. a per-faction template (set via /admin edit faction-template),
         if `faction` is given and one's been set for it
      3. the global default template (/admin edit template)
      4. a flat placeholder, so the bot never crashes with nothing set
    """
    if template_override and Path(template_override).exists():
        return Image.open(template_override).convert("RGBA")

    try:
        from db.connection import get_setting
        if faction:
            faction_path = get_setting(f"card_template_path:{faction}", "")
            if faction_path and Path(faction_path).exists():
                return Image.open(faction_path).convert("RGBA")

        custom_path = get_setting("card_template_path", "")
        if custom_path and Path(custom_path).exists():
            return Image.open(custom_path).convert("RGBA")
    except Exception:
        pass  # fall through to the default background below

    if DEFAULT_BACKGROUND.exists():
        return Image.open(DEFAULT_BACKGROUND).convert("RGBA")
    # Flat placeholder gradient so the bot never crashes if no
    # background asset has been added yet. Matches your template's
    # aspect ratio so the artwork box fractions still look reasonable.
    return Image.new("RGBA", (1054, 1492), (30, 30, 40, 255))


# ---------------------------------------------------------------------------
# Reiatsu variant look (see reiatsu.py)
# ---------------------------------------------------------------------------
# A Reiatsu copy renders as the same card with: an icy-cyan title, a
# rising spirit-energy glow + sparks over the artwork, a glowing frame
# around the whole card, a "REIATSU" badge on the artwork, and its
# boosted HP/attack numbers.

REIATSU_CYAN = (70, 205, 255)
REIATSU_ICE = (222, 246, 255, 255)
REIATSU_SHADOW = (8, 34, 72, 255)


def _reiatsu_artwork_aura(image: Image.Image, box, seed: str) -> None:
    """Spirit-energy glow rising from the bottom of the artwork box,
    plus a scatter of upward sparks. Seeded from the name so the same
    character always gets the same sparks (the card is cached anyway)."""
    (x0, y0), (x1, y1) = box
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0:
        return

    # Vertical gradient: transparent at the top -> strong at the bottom.
    ramp = Image.linear_gradient("L").resize((w, h))
    bottom_alpha = ramp.point(lambda v: int(((v / 255) ** 1.7) * 165))
    glow = Image.new("RGBA", (w, h), REIATSU_CYAN + (0,))
    glow.putalpha(bottom_alpha)
    image.alpha_composite(glow, (x0, y0))

    # Faint edge haze left/right so the aura wraps the figure.
    side = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sd = ImageDraw.Draw(side)
    edge = max(4, int(w * 0.05))
    sd.rectangle([0, 0, edge, h], fill=REIATSU_CYAN + (120,))
    sd.rectangle([w - edge, 0, w, h], fill=REIATSU_CYAN + (120,))
    side = side.filter(ImageFilter.GaussianBlur(radius=edge * 1.4))
    image.alpha_composite(side, (x0, y0))

    rng = random.Random(f"reiatsu:{seed}")
    sparks = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(sparks)
    # Rising embers: bright head with a short fading tail BELOW it, so
    # they read as energy lifting off the figure, not as falling rain.
    for _ in range(30):
        sx = rng.randint(0, w)
        sy = rng.randint(int(h * 0.12), int(h * 0.92))
        r = rng.randint(max(2, h // 170), max(3, h // 75))
        tail = rng.randint(h // 22, h // 9)
        drift = rng.randint(-r * 2, r * 2)
        d.line([(sx, sy), (sx + drift, sy + tail)],
               fill=(180, 236, 255, rng.randint(60, 130)), width=max(1, r // 2))
        d.ellipse([sx - r, sy - r, sx + r, sy + r],
                  fill=(245, 253, 255, rng.randint(170, 255)))
    halo = sparks.filter(ImageFilter.GaussianBlur(radius=max(3, h // 55)))
    image.alpha_composite(halo, (x0, y0))
    image.alpha_composite(halo, (x0, y0))
    image.alpha_composite(sparks, (x0, y0))


def _reiatsu_frame_and_badge(image: Image.Image, box, badge_font) -> None:
    """Glowing frame around the whole card + a REIATSU badge pinned to
    the artwork's top-right corner. Drawn last so it sits over everything."""
    w, h = image.size
    t = max(6, int(w * 0.018))
    radius = int(w * 0.05)
    inset = t // 2

    halo = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(halo).rounded_rectangle(
        [inset, inset, w - inset - 1, h - inset - 1], radius=radius,
        outline=REIATSU_CYAN + (255,), width=t,
    )
    halo = halo.filter(ImageFilter.GaussianBlur(radius=t * 1.1))
    image.alpha_composite(halo)
    image.alpha_composite(halo)  # twice = a stronger glow without a wider blur

    d = ImageDraw.Draw(image)
    d.rounded_rectangle(
        [inset, inset, w - inset - 1, h - inset - 1], radius=radius,
        outline=REIATSU_ICE, width=max(2, t // 3),
    )

    # Badge
    (bx0, by0), (bx1, by1) = box
    label = "REIATSU"
    tw = d.textlength(label, font=badge_font)
    pad_x = int(badge_font.size * 0.55)
    pad_y = int(badge_font.size * 0.32)
    right = bx1 - int(w * 0.02)
    top = by0 + int(w * 0.02)
    pill = [right - tw - 2 * pad_x, top, right, top + badge_font.size + 2 * pad_y]
    d.rounded_rectangle(pill, radius=(pill[3] - pill[1]) // 2,
                        fill=(10, 42, 88, 235), outline=REIATSU_ICE, width=max(2, t // 4))
    d.text((pill[0] + pad_x, pill[1] + pad_y), label, font=badge_font,
           fill=REIATSU_ICE, stroke_width=1, stroke_fill=(0, 0, 0, 255))


# HP / Attack number colours per faction: (fill, shadow, outline, outline width).
# Black text gets a WHITE outline - a black number with the usual black
# outline would simply vanish into it - and a thin one (1px), because a
# thick light outline would swallow the black fill of this narrow font.
_WHITE = ((255, 255, 255, 255), (30, 30, 30, 255), (0, 0, 0, 255), 3)
_BLACK = ((0, 0, 0, 255), (120, 120, 120, 255), (255, 255, 255, 255), 1)
_GREY = ((150, 150, 150, 255), (30, 30, 30, 255), (0, 0, 0, 255), 3)
_BLUE = ((70, 150, 255, 255), (8, 24, 70, 255), (0, 0, 0, 255), 3)
_RED = ((235, 50, 50, 255), (60, 8, 8, 255), (0, 0, 0, 255), 3)
_DEFAULT_HP = ((224, 64, 56, 255), (48, 16, 10, 255), (0, 0, 0, 255), 3)        # crimson, like the heart icon
_DEFAULT_ATTACK = ((255, 197, 84, 255), (48, 16, 10, 255), (0, 0, 0, 255), 3)   # gold, like the sword icon

STAT_COLORS = {
    #  faction      (HP,     ATTACK)
    "quincy":      (_BLUE,  _RED),
    "soul_reaper": (_WHITE, _BLACK),
    "hollow":      (_GREY,  _WHITE),
}


def _stat_colors(name: str, faction: str):
    """(hp_style, attack_style) for a card. Uses the faction the caller
    passed in, or - when that's empty (characters added after the
    original faction list, e.g. most non-pack roster) - looks the name
    up in factions.py. Anything else keeps the default red / gold."""
    if not faction:
        from factions import CHARACTER_FACTIONS, COMPLETION_EXTRA_FACTIONS
        faction = CHARACTER_FACTIONS.get(name) or COMPLETION_EXTRA_FACTIONS.get(name, "")
    return STAT_COLORS.get(faction, (_DEFAULT_HP, _DEFAULT_ATTACK))


def weapon_stat_display(weapon) -> Tuple[int, int, str, str]:
    """Builds the (hp, attack, hp_display, attack_display) args to pass
    into render_card() for a Weapon. Weapons no longer have flat hp/
    attack numbers - they boost ONE of the equipped character's stats
    by boost_percent% (see db/weapons.py) - so the OTHER stat slot on
    the card shows a plain "0" and the boosted one shows "+40%" style
    text instead of a raw number."""
    if weapon.boost_type == "hp":
        return 0, 0, f"+{weapon.boost_percent}%", "0"
    return 0, 0, "0", f"+{weapon.boost_percent}%"


def render_card(
    name: str,
    artwork_path: str,
    hp: int,
    attack: int,
    rarity: int,
    ability_name: str = "",
    ability_description: str = "",
    template_path: str = "",
    faction: str = "",
    hp_display: Optional[str] = None,
    attack_display: Optional[str] = None,
    reiatsu: bool = False,
) -> bytes:
    """Returns PNG bytes ready to attach to a Discord message.
    template_path, if given (a character/weapon's own card_template_path),
    overrides the global default template for just this card. faction,
    if given, selects a faction-themed template when no per-card
    template_path is set - see _ensure_background()'s priority order.

    hp_display/attack_display let a caller override what TEXT is drawn
    in the HP/Attack slots without changing the numbers used anywhere
    else - weapon cards use this to show "+40%" instead of a raw stat,
    since a weapon's hp/attack params are now a percentage boost to
    one stat, not a flat number for both (see cogs/shop.py, card_view.py).
    Defaults to str(hp)/str(attack), i.e. unchanged for character cards.

    reiatsu=True renders the Reiatsu variant of a CHARACTER card (see
    reiatsu.py): "(Reiatsu)" name, cyan title, spirit-energy aura,
    glowing frame + badge, and the boosted HP (+10%) / attack (+20%)
    numbers - pass the character's BASE hp/attack, the boost is applied
    here. Never pass it for weapons."""
    bg_id = _background_identity(template_path, faction)
    cache_key = (
        name, artwork_path, hp, attack, rarity, ability_name,
        ability_description, template_path, faction, hp_display,
        attack_display, bg_id, reiatsu,
    )
    cached = _RENDER_CACHE.get(cache_key)
    if cached is not None:
        return cached

    card_name = name
    if reiatsu:
        card_name = reiatsu_name(name)
        if hp_display is None:
            hp_display = str(boosted_hp(hp))
        if attack_display is None:
            attack_display = str(boosted_attack(attack))

    image = _ensure_background(template_path, faction)
    width, height = image.size
    draw = ImageDraw.Draw(image)

    # Artwork box: sized as a fraction of the canvas so it always matches
    # the template's own drawn frame, centered on it.
    box_w = int(ARTWORK_BOX_SIZE_FRAC[0] * width)
    box_h = int(ARTWORK_BOX_SIZE_FRAC[1] * height)
    center_x = int(ARTWORK_CENTER_FRAC[0] * width)
    center_y = int(ARTWORK_CENTER_FRAC[1] * height)
    box = (
        (center_x - box_w // 2, center_y - box_h // 2),
        (center_x - box_w // 2 + box_w, center_y - box_h // 2 + box_h),
    )

    # Fonts scale with the template's resolution instead of being fixed
    # pixel sizes that only looked right at one specific canvas size.
    # Name + stat numbers use the italic/slanted face (matches the punchy
    # "TENSA ZANGETSU" title-logo look); ability text uses the upright
    # bold face.
    stats_font = _load_font("stats.ttf", max(18, int(height * 0.056)), italic=True)
    # Label bigger than the body text (was the other way round) - "ABILITY:"
    # is the punchy header, the description underneath is the fine print.
    ability_label_font = _load_font("ability_label.ttf", max(16, int(height * 0.038)))
    ability_body_font = _load_font("ability_body.ttf", max(14, int(height * 0.024)))

    margin_x = int(MARGIN_X_FRAC * width)
    title_x = int(TITLE_X_FRAC * width)

    # Name font shrinks to fit if it's long - the top-right faction
    # emblem eats into the available width, so a long name (e.g. "Ichigo
    # Kurosaki") must not be allowed to run under/over it.
    title_area_left = title_x
    title_area_right = int(TITLE_AREA_RIGHT_FRAC * width)
    title_max_width = title_area_right - title_area_left
    # Bumped from 0.052 -> 0.066 start size to read as a big bold banner
    # logo (like the reference "Pudding" card's title), not a small label.
    title_font = _fit_font_to_width(
        draw, card_name.upper(), "title.ttf",
        start_size=max(20, int(height * 0.066)), min_size=max(14, int(height * 0.028)),
        max_width=title_max_width, italic=True,
    )

    # Poster/shadow colors - a dark warm brown works as the "shadow" copy
    # against the orange template for every text color we use below.
    shadow_dark = (48, 16, 10, 255)
    cream = (255, 248, 232, 255)
    title_fill, title_shadow = (REIATSU_ICE, REIATSU_SHADOW) if reiatsu else (cream, shadow_dark)

    # Name, above the artwork box - bold italic, all caps, cream over a
    # dark offset shadow copy, so it reads as a title-card logo rather
    # than plain label text. Centered within the name's own safe area
    # (left margin -> just before the faction emblem), not the full
    # card width, so it reads as centered without ever sitting under
    # the emblem.
    title_center_x = (title_area_left + title_area_right) // 2
    _draw_poster_text(
        draw, (title_center_x, int(TITLE_Y_FRAC * height)), card_name.upper(), title_font,
        fill=title_fill, shadow_fill=title_shadow,
        shadow_offset=max(2, int(height * 0.006)), stroke_width=3, anchor="ma",
    )

    # Artwork - ImageOps.fit crops to COMPLETELY FILL the box (no empty
    # letterboxing), which is what "bigger the frame" wants. If you'd
    # rather see the whole image with empty space instead of cropping,
    # tell me and I'll switch this to a "fit inside, no crop" mode.
    #
    # THE BUG THIS FIXES: many of the source PNGs are transparent-
    # background art where the RGB channel under fully-transparent
    # pixels is still (0, 0, 0) - black - even though alpha is 0. Pillow's
    # paste() does NOT use the source's own alpha as a mask unless you
    # explicitly pass one, so without `fitted` as the mask arg those
    # "transparent" pixels got pasted as solid opaque black, painting a
    # black rectangle behind every character instead of showing the
    # template through. Passing `fitted` as its own mask makes paste()
    # respect per-pixel alpha, so transparent regions correctly show the
    # card template underneath instead of black.
    try:
        from image_source import fetch_image_bytes
        from card import CARD_IMAGES

        # Always prefer the dedicated card art (card.py / CARD_IMAGES) by
        # name over whatever artwork_path was passed in - artwork_path is
        # usually the SPAWN art (soul.py), which is meant for the catch
        # embed, not the middle frame of the actual rendered card. Only
        # fall back to artwork_path if this name has no card.py entry.
        card_source = CARD_IMAGES.get(name) or artwork_path
        image_buf = fetch_image_bytes(card_source)
        if image_buf is None:
            raise FileNotFoundError(card_source)
        artwork = Image.open(image_buf).convert("RGBA")
        fitted = _cover_crop(
            artwork, box_w, box_h, zoom=ARTWORK_ZOOM, focus=ARTWORK_FOCUS_FRAC,
        )
        image.paste(fitted, box[0], fitted)
        artwork.close()
    except (FileNotFoundError, OSError):
        draw.rectangle(box, outline=(0, 0, 0, 255), width=3)
        draw.text(
            ((box[0][0] + box[1][0]) // 2, (box[0][1] + box[1][1]) // 2),
            "no artwork", font=stats_font, fill=(60, 40, 20, 255), anchor="mm",
        )

    if reiatsu:
        _reiatsu_artwork_aura(image, box, name)

    # Ability block, just below the box: "ABILITY: <NAME>" as ONE bold
    # header line (matches the reference card's "ABILITY: THREE EYES"
    # style - name folded into the label instead of a separate label +
    # "name - description" line), then the description flowing
    # underneath as its own wrapped paragraph.
    y = int(ABILITY_Y_FRAC * height)
    label_shadow_off = max(2, int(height * 0.004))
    # The word "ABILITY:" is gone - the header is just the ability's own
    # name (and nothing at all if it has none).
    if ability_name:
        header_text = ability_name.upper()
        header_max_width = width - margin_x - int(width * 0.03)
        header_font = _fit_font_to_width(
            draw, header_text, "ability_label.ttf",
            start_size=ability_label_font.size, min_size=max(14, int(height * 0.022)),
            max_width=header_max_width,
        )
        _draw_poster_text(
            draw, (margin_x, y), header_text, header_font,
            fill=cream, shadow_fill=shadow_dark,
            shadow_offset=label_shadow_off, stroke_width=2,
        )
        y += int(header_font.size * 1.25)

    body_text = ability_description
    body_shadow_off = max(2, int(height * 0.005))
    body_max_width = width - margin_x - int(width * 0.03)
    for line in _wrap_by_pixel_width(draw, body_text, ability_body_font, body_max_width):
        _draw_poster_text(
            draw, (margin_x, y), line, ability_body_font,
            fill=cream, shadow_fill=shadow_dark,
            shadow_offset=body_shadow_off, stroke_width=2,
        )
        y += int(ability_body_font.size * 1.28)

    # HP / Attack, anchored on their text BASELINE (not top-left) so they
    # sit consistently low, right at the bottom corners next to the
    # heart/sword icons, instead of floating above them. Colored to match
    # their icon (crimson HP next to the heart, gold Attack next to the
    # sword) instead of both being plain white - matches the reference
    # card's colored stat numbers instead of reading as one flat block.
    stats_y = int(STATS_Y_FRAC * height)
    stats_shadow_off = max(2, int(height * 0.006))
    hp_style, attack_style = _stat_colors(name, faction)
    _draw_poster_text(
        draw, (int(STATS_HP_X_FRAC * width), stats_y), hp_display if hp_display is not None else str(hp), stats_font,
        fill=hp_style[0], shadow_fill=hp_style[1], stroke_fill=hp_style[2],
        shadow_offset=stats_shadow_off, stroke_width=hp_style[3], anchor="ls",
    )
    _draw_poster_text(
        draw, (int(STATS_ATTACK_X_FRAC * width), stats_y), attack_display if attack_display is not None else str(attack), stats_font,
        fill=attack_style[0], shadow_fill=attack_style[1], stroke_fill=attack_style[2],
        shadow_offset=stats_shadow_off, anchor="rs", stroke_width=attack_style[3],
    )

    if reiatsu:
        badge_font = _load_font("ability_label.ttf", max(14, int(height * 0.024)), italic=True)
        _reiatsu_frame_and_badge(image, box, badge_font)

    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="PNG")
    result = buffer.getvalue()
    _RENDER_CACHE.put(cache_key, result)
    return result