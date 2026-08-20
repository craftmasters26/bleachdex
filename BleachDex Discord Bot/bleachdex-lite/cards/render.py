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
"""

import io
import textwrap
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont, ImageOps

ASSETS_DIR = Path(__file__).parent.parent / "assets"
DEFAULT_BACKGROUND = ASSETS_DIR / "backgrounds" / "placeholder.png"
FONT_DIR = ASSETS_DIR / "fonts"

# Measured directly from your card.png (1054x1492) by scanning for the
# black inset box's border lines. Stored as fractions of (width, height)
# so they still make sense if the template's resolution ever changes.
# left, top, right, bottom
ARTWORK_BOX_FRAC = (0.0617, 0.1917, 0.9375, 0.5717)

TITLE_Y_FRAC = 0.045          # "Don Kanonji" name, above the box
ABILITY_Y_FRAC = 0.615        # ability name/description, just below the box
STATS_Y_FRAC = 0.925          # HP / Attack numbers, near the bottom icons
MARGIN_X_FRAC = 0.038


def _load_font(name: str, size: int) -> ImageFont.FreeTypeFont:
    """Try a custom TTF first, fall back to PIL's bundled default font."""
    custom = FONT_DIR / name
    if custom.exists():
        return ImageFont.truetype(str(custom), size)
    try:
        return ImageFont.truetype("DejaVuSans-Bold.ttf", size)
    except OSError:
        return ImageFont.load_default(size=size)


def _ensure_background(template_override: str = "") -> Image.Image:
    """Returns the template image AT ITS OWN NATIVE SIZE - never resized
    here, so nothing gets distorted."""
    if template_override and Path(template_override).exists():
        return Image.open(template_override).convert("RGBA")

    try:
        from db.connection import get_setting
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


def render_card(
    name: str,
    artwork_path: str,
    hp: int,
    attack: int,
    rarity: int,
    ability_name: str = "",
    ability_description: str = "",
    template_path: str = "",
) -> bytes:
    """Returns PNG bytes ready to attach to a Discord message.
    template_path, if given (a character/weapon's own card_template_path),
    overrides the global default template for just this card."""
    image = _ensure_background(template_path)
    width, height = image.size
    draw = ImageDraw.Draw(image)

    # Artwork box in real pixels for THIS template's actual resolution
    box = (
        (int(ARTWORK_BOX_FRAC[0] * width), int(ARTWORK_BOX_FRAC[1] * height)),
        (int(ARTWORK_BOX_FRAC[2] * width), int(ARTWORK_BOX_FRAC[3] * height)),
    )
    box_w = box[1][0] - box[0][0]
    box_h = box[1][1] - box[0][1]

    # Fonts scale with the template's resolution instead of being fixed
    # pixel sizes that only looked right at one specific canvas size.
    title_font = _load_font("title.ttf", max(18, int(height * 0.052)))
    stats_font = _load_font("stats.ttf", max(16, int(height * 0.036)))
    ability_name_font = _load_font("ability_name.ttf", max(16, int(height * 0.032)))
    ability_desc_font = _load_font("ability_desc.ttf", max(14, int(height * 0.025)))

    margin_x = int(MARGIN_X_FRAC * width)

    # Name, above the artwork box - white with a black outline so it
    # reads clearly against the orange template
    draw.text((margin_x, int(TITLE_Y_FRAC * height)), name, font=title_font,
               fill=(255, 255, 255, 255), stroke_width=3, stroke_fill=(0, 0, 0, 255))

    # Artwork - ImageOps.fit crops to COMPLETELY FILL the box (no empty
    # letterboxing), which is what "bigger the frame" wants. If you'd
    # rather see the whole image with empty space instead of cropping,
    # tell me and I'll switch this to a "fit inside, no crop" mode.
    try:
        artwork = Image.open(artwork_path).convert("RGBA")
        fitted = ImageOps.fit(artwork, (box_w, box_h))
        image.paste(fitted, box[0])
        artwork.close()
    except (FileNotFoundError, OSError):
        draw.rectangle(box, outline=(0, 0, 0, 255), width=3)
        draw.text(
            ((box[0][0] + box[1][0]) // 2, (box[0][1] + box[1][1]) // 2),
            "no artwork", font=stats_font, fill=(60, 40, 20, 255), anchor="mm",
        )

    # Ability block, just below the box - white with a black outline,
    # same style as the name, so it's readable against the orange template
    y = int(ABILITY_Y_FRAC * height)
    if ability_name:
        draw.text((margin_x, y), f"Ability: {ability_name}", font=ability_name_font,
                   fill=(255, 255, 255, 255), stroke_width=2, stroke_fill=(0, 0, 0, 255))
        y += int(height * 0.036)
    wrap_width = max(20, int(width / (ability_desc_font.size * 0.55)))
    for line in textwrap.wrap(ability_description, width=wrap_width):
        draw.text((margin_x, y), line, font=ability_desc_font,
                   fill=(255, 255, 255, 255), stroke_width=1, stroke_fill=(0, 0, 0, 255))
        y += int(height * 0.028)

    # HP / Attack, bottom corners near the heart/sword icons
    stats_y = int(STATS_Y_FRAC * height) - stats_font.size
    draw.text((margin_x, stats_y), str(hp), font=stats_font,
               fill=(237, 115, 101, 255), stroke_width=2, stroke_fill=(0, 0, 0, 255))
    draw.text((width - margin_x, stats_y), str(attack), font=stats_font,
               fill=(252, 194, 76, 255), stroke_width=2, stroke_fill=(0, 0, 0, 255),
               anchor="ra")

    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="PNG")
    return buffer.getvalue()