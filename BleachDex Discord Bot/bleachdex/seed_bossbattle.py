"""
Seeds db/bossbattle.py's boss table from the numbers in Boss.txt.

Run standalone (`python3 seed_bossbattle.py`) or call seed_bossbattle()
from anywhere - bot.py calls it once in setup_hook, after init_db(), so
a fresh database (or a fresh boss added to this file) is always ready
without a manual step. It's a plain upsert-by-name, so re-running it
after tweaking a number here just updates the existing row instead of
duplicating it.

Art: these bosses are all existing roster characters, so instead of
uploading new art we just point image_path at the same GitHub-hosted
image already used for that character's card (see db/characters.py's
seeded rows / the craftmasters26/bleachdex image repo).

Emoji: the four drop types recur across many bosses, so their emoji
IDs are stored once each under generic keys (bossbattle_drop:*) via
db/custom_emoji.py, rather than repeating the same ID on every boss
row. Values are the numeric IDs from the "BleachDex Emojis" reference
image the bosses were specced from.
"""

from urllib.parse import quote

from db.connection import init_db
from db import bosses as bs, custom_emoji as ce
from soul import CHARACTER_IMAGES

_IMG = "https://raw.githubusercontent.com/craftmasters26/bleachdex/main/new%20soul%20images/New%20Character%20Images/{}.png"

# Generic drop-emoji keys, shared by every boss that drops that item.
EMOJI_IDS = {
    "hollow_mask": "1548196583693226125",
    "hogyoku": "1548196581499600956",
    "quincy_cross": "1548196585618284636",
    "almighty_eye": "1548196579482280079",
    # Captain flowers / Lieutenant badge materials (shared - Captains and
    # Lieutenants drop the same flower items)
    "yarrow": "1550714624582623352",
    "white_poppy": "1550714622787715192",
    "thistle": "1550714618941407252",
    "snowdrop": "1550714614591918131",
    "pasque_flower": "1550714605230366730",
    "marigold": "1550714602671575070",
    "lily_of_the_valley": "1550714600310186005",
    "iris": "1550714595314769971",
    "daffodil": "1550714586020188230",
    "chrysanthemum": "1550714582023278592",
    "camellia": "1550714580265738350",
    "bird_of_paradise": "1550714578164252684",
    "bellflower": "1550714576616693842",
    # Other materials
    "jigokucho": "1550714598150115348",
    "sanrei_glove": "1550714610762518548",
    "vasto_lorde": "1550714620958736524",
    "soul_kings_heart": "1550714616915693588",
    "shinigami_badge": "1550714612448759902",
    "horn_of_salvation": "1550714593087717537",
    "cross_of_scaffold": "1550714584078221372",
    "shineiyaki": "1550736578283044874",
}

DROP_EMOJI_KEY = {
    "Hollow Mask": "bossbattle_drop:hollow_mask",
    "Hogyoku": "bossbattle_drop:hogyoku",
    "Quincy Cross": "bossbattle_drop:quincy_cross",
    "Almighty Eye": "bossbattle_drop:almighty_eye",
    "Yarrow": "bossbattle_drop:yarrow",
    "White Poppy": "bossbattle_drop:white_poppy",
    "Thistle": "bossbattle_drop:thistle",
    "Snowdrop": "bossbattle_drop:snowdrop",
    "Pasque Flower": "bossbattle_drop:pasque_flower",
    "Marigold": "bossbattle_drop:marigold",
    "Lily of the Valley": "bossbattle_drop:lily_of_the_valley",
    "Iris": "bossbattle_drop:iris",
    "Daffodil": "bossbattle_drop:daffodil",
    "Chrysanthemum": "bossbattle_drop:chrysanthemum",
    "Camellia": "bossbattle_drop:camellia",
    "Bird of Paradise": "bossbattle_drop:bird_of_paradise",
    "Bellflower": "bossbattle_drop:bellflower",
    "Jigokuchō": "bossbattle_drop:jigokucho",
    "Sanrei Glove": "bossbattle_drop:sanrei_glove",
    "Vasto Lorde": "bossbattle_drop:vasto_lorde",
    "Soul King's Heart": "bossbattle_drop:soul_kings_heart",
    "Shinigami Badge": "bossbattle_drop:shinigami_badge",
    "Horn of Salvation": "bossbattle_drop:horn_of_salvation",
    "Cross of Scaffold": "bossbattle_drop:cross_of_scaffold",
    "Shin'eiyaku": "bossbattle_drop:shineiyaki",
    # No emoji is registered for this one yet: /admin emoji set-custom
    # key:bossbattle_drop:xcution_badge emoji_id:<id>
    "Xcution Badge": "bossbattle_drop:xcution_badge",
}

# name -> Boss.txt data. image key is the roster character whose art we
# reuse (URL-encoded the same way the roster's own image_path is; for
# the newer entries it's simply the roster character's exact name, which
# is looked up in soul.CHARACTER_IMAGES - see _image_url()).
# Format: (category, name, image_key, max_hp, dmg_per_round,
#          [(drop_name, drop_rate), ...])
# A boss can have any number of drops (db/bosses.py's bossbattle_drops
# table, one row per drop) - each one is rolled independently.
BOSSES = [
    # --------------------------------------------------------- Final Boss
    ("Final Boss", "Sosuke Aizen (Base)", "Sosuke%20Aizen", 70_000, 2_000,
     [("Hollow Mask", 40), ("Hogyoku", 25), ("Shin'eiyaku", 5)]),
    ("Final Boss", "Sosuke Aizen (Hogyoku Fusion)", "Sosuke%20Aizen", 85_000, 2_800,
     [("Hollow Mask", 50), ("Hogyoku", 35), ("Shin'eiyaku", 15),
      ("Soul King's Heart", 5), ("Soul King", 2)]),
    ("Final Boss", "Yhwach (Base)", "Yhwach", 90_000, 2_500,
     [("Quincy Cross", 30), ("Almighty Eye", 3), ("Sanrei Glove", 10), ("Horn of Salvation", 1)]),
    ("Final Boss", "Yhwach (Soul King Absorbed)", "Yhwach", 110_000, 3_000,
     [("Quincy Cross", 40), ("Almighty Eye", 10), ("Sanrei Glove", 15),
      ("Horn of Salvation", 5), ("Soul King's Heart", 10), ("Soul King", 5)]),

    # ----------------------------------------------------------- Espada
    ("Espada", "Dordoni", "Dordoni%20Alessandro%20Del%20Socaccio", 40_000, 800,
     [("Hollow Mask", 10), ("Hogyoku", 5)]),
    ("Espada", "Cirucci", "Cirucci%20Sanderwicci", 40_000, 800,
     [("Hollow Mask", 10), ("Hogyoku", 5)]),
    ("Espada", "Gantenbainne", "Gantenbainne%20Mosqueda", 40_000, 800,
     [("Hollow Mask", 10), ("Hogyoku", 5)]),
    ("Espada", "Aaroniero Arruruerie", "Aaroniero%20Arruruerie", 40_000, 1_000,
     [("Hollow Mask", 12), ("Hogyoku", 6), ("Vasto Lorde", 2)]),
    ("Espada", "Zommari Rureaux", "Zommari%20Rureaux", 40_000, 1_200,
     [("Hollow Mask", 14), ("Hogyoku", 7), ("Vasto Lorde", 2)]),
    ("Espada", "Szayelaporro Granz", "Szayelaporro%20Granz", 40_000, 1_400,
     [("Hollow Mask", 16), ("Hogyoku", 8), ("Vasto Lorde", 3)]),
    ("Espada", "Yammy Llargo (Base)", "Yammy%20Llargo", 40_000, 1_600,
     [("Hollow Mask", 18), ("Hogyoku", 9), ("Vasto Lorde", 3)]),
    ("Espada", "Grimmjow Jaegerjaquez", "grimmjow", 70_000, 1_800,
     [("Hollow Mask", 20), ("Hogyoku", 10), ("Vasto Lorde", 4)]),
    ("Espada", "Nnoitra Gilga", "Nnoitra%20Gilga", 40_000, 2_000,
     [("Hollow Mask", 22), ("Hogyoku", 11), ("Vasto Lorde", 4)]),
    ("Espada", "Ulquiorra Cifer (Base)", "Ulquiorra%20Cifer", 70_000, 2_200,
     [("Hollow Mask", 24), ("Hogyoku", 12), ("Vasto Lorde", 5)]),
    ("Espada", "Tier Harribel", "Tier%20Harribel", 40_000, 2_400,
     [("Hollow Mask", 26), ("Hogyoku", 13), ("Vasto Lorde", 5)]),
    ("Espada", "Coyote Starrk", "Coyote%20Starrk", 70_000, 2_600,
     [("Hollow Mask", 28), ("Hogyoku", 14), ("Vasto Lorde", 6)]),
    ("Espada", "Baraggan Louisenbairn", "Barragan%20Louisenbairn", 40_000, 2_800,
     [("Hollow Mask", 30), ("Hogyoku", 15), ("Vasto Lorde", 6)]),
    ("Espada", "Ulquiorra Cifer (Segunda Etapa)", "Ulquiorra%20Cifer", 70_000, 3_000,
     [("Hollow Mask", 35), ("Hogyoku", 20), ("Vasto Lorde", 8), ("Soul King's Heart", 2)]),
    ("Espada", "Yammy Llargo (Rage / Espada #0)", "Yammy%20Llargo", 40_000, 3_200,
     [("Hollow Mask", 40), ("Hogyoku", 25), ("Vasto Lorde", 10), ("Soul King's Heart", 3)]),

    # --------------------------------------------------------- Sternritter
    ("Sternritter", "Giselle Gewelle", "Giselle%20Gewelle", 20_000, 1_400,
     [("Quincy Cross", 10), ("Almighty Eye", 0.1), ("Sanrei Glove", 5)]),
    ("Sternritter", "As Nodt", "%C3%84s%20N%C3%B6dt", 20_000, 1_600,
     [("Quincy Cross", 12), ("Almighty Eye", 0.2), ("Sanrei Glove", 5)]),
    ("Sternritter", "Mask De Masculine", "Mask%20De%20Masculine", 20_000, 1_800,
     [("Quincy Cross", 14), ("Almighty Eye", 0.3), ("Sanrei Glove", 6)]),
    ("Sternritter", "Bambietta Basterbine", "Bambietta%20Basterbine", 40_000, 2_000,
     [("Quincy Cross", 16), ("Almighty Eye", 0.4), ("Sanrei Glove", 6)]),
    ("Sternritter", "Cang Du", "Cang%20Du", 40_000, 1_800,
     [("Quincy Cross", 18), ("Almighty Eye", 0.5), ("Sanrei Glove", 7)]),
    ("Sternritter", "Askin Nakk Le Vaar", "Askin%20Nakk%20Le%20Vaar", 60_000, 2_400,
     [("Quincy Cross", 20), ("Almighty Eye", 1), ("Sanrei Glove", 8), ("Horn of Salvation", 1)]),
    ("Sternritter", "Pernida Parnkgjas", "Pernida%20Parnkgjas", 60_000, 2_800,
     [("Quincy Cross", 25), ("Almighty Eye", 2), ("Sanrei Glove", 10), ("Horn of Salvation", 2)]),

    # ------------------------------------------- Soul Reaper Captains
    # drop1 = flower (Lieutenant Badge material), drop2 = Jigokucho
    # (Kaname Tosen additionally drops Shin'eiyaku). The Bankai items are
    # weapons now (see seed_craftables.py), not boss drops.
    ("Captain", "Yamamoto", "Genryusai Shigekuni Yamamoto", 75_000, 3_000,
     [("Chrysanthemum", 20), ("Jigokuchō", 25)]),
    ("Captain", "Soi Fon", "Soi Fon", 60_000, 2_500,
     [("Pasque Flower", 18), ("Jigokuchō", 22)]),
    ("Captain", "Gin Ichimaru", "Gin Ichimaru", 60_000, 2_600,
     [("Marigold", 19), ("Jigokuchō", 23)]),
    ("Captain", "Retsu Unohana", "Retsu Unohana", 60_000, 2_700,
     [("Bellflower", 20), ("Jigokuchō", 24)]),
    ("Captain", "Byakuya Kuchiki", "Byakuya Kuchiki", 60_000, 2_650,
     [("Camellia", 20), ("Jigokuchō", 24)]),
    ("Captain", "Sajin Komamura", "Sajin Komamura", 60_000, 2_600,
     [("Iris", 19), ("Jigokuchō", 23)]),
    ("Captain", "Shunsui Kyoraku", "Shunsui Kyoraku", 60_000, 2_800,
     [("Bird of Paradise", 21), ("Jigokuchō", 26)]),
    ("Captain", "Kaname Tosen", "Kaname Tosen", 60_000, 2_550,
     [("White Poppy", 19), ("Jigokuchō", 23), ("Shin'eiyaku", 10)]),
    ("Captain", "Toshiro Hitsugaya", "Toshiro Hitsugaya", 60_000, 2_600,
     [("Daffodil", 20), ("Jigokuchō", 24)]),
    ("Captain", "Kenpachi Zaraki", "Kenpachi Zaraki", 60_000, 3_100,
     [("Yarrow", 22), ("Jigokuchō", 27)]),
    ("Captain", "Mayuri Kurotsuchi", "Mayuri Kurotsuchi", 60_000, 2_500,
     [("Thistle", 18), ("Jigokuchō", 22)]),
    ("Captain", "Jushiro Ukitake", "Jushiro Ukitake", 60_000, 2_700,
     [("Snowdrop", 20), ("Jigokuchō", 24)]),

    # ---------------------------------------- Soul Reaper Lieutenants
    # drop1 = flower (same items the Captains drop), drop2 = Jigokucho
    ("Lieutenant", "Renji Abarai", "Renji Abarai", 48_000, 1_800,
     [("Camellia", 25), ("Jigokuchō", 20)]),
    ("Lieutenant", "Rukia Kuchiki", "Rukia Kuchiki", 46_000, 1_700,
     [("Snowdrop", 24), ("Jigokuchō", 19)]),
    ("Lieutenant", "Izuru Kira", "Izuru Kira", 42_000, 1_600,
     [("Marigold", 23), ("Jigokuchō", 18)]),
    ("Lieutenant", "Momo Hinamori", "Momo Hinamori", 42_000, 1_550,
     [("Lily of the Valley", 22), ("Jigokuchō", 17)]),
    ("Lieutenant", "Shuhei Hisagi", "Shuhei Hisagi", 45_000, 1_750,
     [("White Poppy", 24), ("Jigokuchō", 19)]),
    ("Lieutenant", "Rangiku Matsumoto", "Rangiku Matsumoto", 45_000, 1_800,
     [("Daffodil", 25), ("Jigokuchō", 20)]),
    ("Lieutenant", "Yachiru Kusajishi", "Yachiru Kusajishi", 40_000, 1_500,
     [("Yarrow", 22), ("Jigokuchō", 17)]),
    ("Lieutenant", "Isane Kotetsu", "Isane Kotetsu", 40_000, 1_450,
     [("Bellflower", 21), ("Jigokuchō", 16)]),
    ("Lieutenant", "Tetsuzaemon Iba", "Tetsuzaemon Iba", 40_000, 1_400,
     [("Iris", 20), ("Jigokuchō", 15)]),
    ("Lieutenant", "Nanao Ise", "Nanao Ise", 40_000, 1_350,
     [("Bird of Paradise", 20), ("Jigokuchō", 15)]),
    ("Lieutenant", "Nemu Kurotsuchi", "Nemu Kurotsuchi", 42_000, 1_400,
     [("Thistle", 21), ("Jigokuchō", 16)]),

    # -------------------------------------------------------- Visored
    ("Visored", "Shinji Hirako", "Shinji Hirako", 80_000, 2_400,
     [("Hollow Mask", 30), ("Shin'eiyaku", 12), ("Vasto Lorde", 5)]),
    ("Visored", "Kensei Muguruma", "Kensei Muguruma", 40_000, 2_350,
     [("Hollow Mask", 29), ("Shin'eiyaku", 11), ("Vasto Lorde", 5)]),
    ("Visored", "Rojuro Otoribashi (Rose)", "Rose Otoribashi", 40_000, 2_300,
     [("Hollow Mask", 28), ("Shin'eiyaku", 10), ("Vasto Lorde", 4)]),
    ("Visored", "Love Aikawa", "Love Aikawa", 40_000, 2_350,
     [("Hollow Mask", 29), ("Shin'eiyaku", 11), ("Vasto Lorde", 5)]),
    ("Visored", "Hiyori Sarugaki", "Hiyori Sarugaki", 20_000, 2_200,
     [("Hollow Mask", 26), ("Shin'eiyaku", 9), ("Vasto Lorde", 4)]),
    ("Visored", "Lisa Yadomaru", "Lisa Yadomaru", 20_000, 2_250,
     [("Hollow Mask", 27), ("Shin'eiyaku", 10), ("Vasto Lorde", 4)]),
    ("Visored", "Mashiro Kuna", "Mashiro Kuna", 20_000, 2_150,
     [("Hollow Mask", 26), ("Shin'eiyaku", 9), ("Vasto Lorde", 4)]),
    ("Visored", "Hachigen Ushoda", "Hachigen Ushoda", 40_000, 2_300,
     [("Hollow Mask", 28), ("Shin'eiyaku", 10), ("Vasto Lorde", 4)]),

    # ---------------------------------------------------- Fullbringers
    ("Fullbringer", "Kugo Ginjo", "Kugo Ginjo", 60_000, 2_600,
     [("Xcution Badge", 25), ("Cross of Scaffold", 15)]),
    ("Fullbringer", "Jackie Tristan", "Jackie Tristan", 20_000, 1_800,
     [("Xcution Badge", 18), ("Cross of Scaffold", 5)]),
    ("Fullbringer", "Riruka Dokugamine", "Riruka Dokugamine", 20_000, 1_750,
     [("Xcution Badge", 17), ("Cross of Scaffold", 5)]),
    ("Fullbringer", "Giriko Kutsuzawa", "Giriko Kutsuzawa", 20_000, 1_900,
     [("Xcution Badge", 19), ("Cross of Scaffold", 5)]),
    ("Fullbringer", "Moe Shishigawara", "Moe Shishigawara", 20_000, 1_700,
     [("Xcution Badge", 16), ("Cross of Scaffold", 5)]),
    ("Fullbringer", "Yukio Hans Vorarlberna", "Yukio Hans Vorarlberna", 20_000, 1_850,
     [("Xcution Badge", 18), ("Cross of Scaffold", 5)]),

    # ------------------------------------- Crafting material bosses
    # Low drop rates, high risk - these are where Shin'eiyaku, Sanrei
    # Glove, Soul King etc. come from. The Soul Reaper ones (Urahara,
    # Yoruichi, Isshin) drop the Shinigami Badge. Zangetsu / Tensa Zangetsu
    # are weapons, not drops - Ichigo's recipes ask for the weapons.
    ("Crafting Boss", "Kisuke Urahara", "Kisuke Urahara", 80_000, 3_500,
     [("Shin'eiyaku", 15), ("Jigokuchō", 25), ("Hogyoku", 5), ("Quincy Cross", 5),
      ("Almighty Eye", 1), ("Sanrei Glove", 5), ("Soul King", 2), ("Shinigami Badge", 5),
      ("Cross of Scaffold", 5), ("Soul King's Heart", 2)]),
    ("Crafting Boss", "Yoruichi Shihoin", "Yoruichi Shihoin", 80_000, 3_300,
     [("Jigokuchō", 30), ("Shin'eiyaku", 15), ("Quincy Cross", 5), ("Sanrei Glove", 5),
      ("Soul King", 2), ("Shinigami Badge", 5), ("Cross of Scaffold", 5),
      ("Soul King's Heart", 2)]),
    ("Crafting Boss", "Isshin Kurosaki", "Isshin Kurosaki", 60_000, 3_100,
     [("Jigokuchō", 20), ("Shin'eiyaku", 10), ("Hollow Mask", 15), ("Quincy Cross", 5),
      ("Sanrei Glove", 5), ("Shinigami Badge", 5), ("Cross of Scaffold", 5)]),
    ("Crafting Boss", "Soul King", "Soul King", 100_000, 4_500,
     [("Soul King", 10), ("Soul King's Heart", 10), ("Almighty Eye", 5),
      ("Quincy Cross", 10), ("Sanrei Glove", 10), ("Horn of Salvation", 5)]),
    ("Crafting Boss", "Jugram Haschwalth", "Jugram Haschwalth", 80_000, 4_000,
     [("Almighty Eye", 5), ("Quincy Cross", 20), ("Sanrei Glove", 10),
      ("Horn of Salvation", 5), ("Soul King's Heart", 5), ("Soul King", 5)]),
    ("Crafting Boss", "Uryu Ishida", "Uryu Ishida", 80_000, 2_800,
     [("Sanrei Glove", 20), ("Quincy Cross", 15), ("Almighty Eye", 2),
      ("Horn of Salvation", 2), ("Soul King", 2)]),
    ("Crafting Boss", "Ryuken Ishida", "Ryuken Ishida", 40_000, 2_900,
     [("Sanrei Glove", 15), ("Quincy Cross", 10), ("Almighty Eye", 1),
      ("Horn of Salvation", 2), ("Soul King", 2)]),
]


def _image_url(image_key: str) -> str:
    """Older entries pass a pre-encoded filename fragment; newer ones
    pass the roster character's exact name, which soul.CHARACTER_IMAGES
    already maps to the right GitHub URL."""
    if image_key in CHARACTER_IMAGES:
        return CHARACTER_IMAGES[image_key]
    if " " in image_key:  # a plain name we have no art for - encode it like the rest
        return _IMG.format(quote(image_key))
    return _IMG.format(image_key)


def seed_bossbattle() -> int:
    init_db()

    for key, emoji_id in EMOJI_IDS.items():
        ce.set_emoji_id(f"bossbattle_drop:{key}", emoji_id)

    for category, name, image_key, hp, dmg, drops in BOSSES:
        bs.upsert_preset_boss(
            category=category,
            name=name,
            image_path=_image_url(image_key),
            max_hp=hp,
            dmg_per_round=dmg,
            drops=[
                (drop_name, drop_rate, DROP_EMOJI_KEY.get(drop_name, ""))
                for drop_name, drop_rate in drops
            ],
        )

    return len(BOSSES)


if __name__ == "__main__":
    count = seed_bossbattle()
    print(f"Seeded/updated {count} boss battle bosses.")