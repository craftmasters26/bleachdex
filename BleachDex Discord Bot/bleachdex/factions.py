"""
Faction classification for the WHOLE roster - all 289 characters (spawnable
and craftable) and all 64 weapons. Redone from scratch for the 353-item
roster; the old file only knew the first ~170 names, and weapon_faction()
returned "" for every weapon because it tried to read the owner out of names
like "Tensa Zangetsu (Bankai - Ichigo)" that no longer exist.

Used by:
  - /shop           (5 faction pages + a boss-drop page)
  - /collection completion tabs
  - /admin spawn and /admin bossbattle faction option
  - card templates / stat colours (cards/render.py, packs, card_view)

There are 5 groups: Soul Reaper, Vizard, Quincy, Hollow, Full Bringer.
Everything is defined ONCE, in FACTION_MEMBERS below, by exact roster name
(a name that is both a character and a weapon, e.g. "Zabimaru", is in the
same group for both). Everything else in this file is derived from it.

To move somebody: delete their name from one list and add it to another.
To classify a new character/weapon: add its exact name to a list.
Names in UNAFFILIATED, and names in no list at all, never appear on a shop
page. `python factions.py` prints anyone in the database that is in no list.

Judgement calls worth knowing about (change them if you disagree):
  - Ichigo, Isshin, Urahara, Yoruichi and the Gotei 13 filler / zanpakuto
    spirits are Soul Reaper. Ichigo's Visored form is Vizard, his Full
    Hollow form is Hollow, his Fullbring form is Full Bringer.
  - Vizard is its own group (the 8 Visored, their Hollow-Mask forms, and
    their zanpakuto). It is NOT part of Soul Reaper here.
  - Sternritter are Quincy - including Nianzol Weizol, PePe Waccabrada and
    Shaz Domino, whom the old file had under Hollow.
  - Humans, Bount, modified souls and Adnyeus are unaffiliated.
  - Hikone Ubuginu ("hybrid Shinigami/Arrancar") is Soul Reaper.
"""

FACTION_NAMES = {
    "soul_reaper": "Soul Reaper",
    "vizard": "Vizard",
    "quincy": "Quincy",
    "hollow": "Hollow",
    "fullbringer": "Full Bringer",
}

FACTION_MEMBERS = {
    "soul_reaper": [
        # --- characters ---
        "Ichigo Kurosaki", "Kisuke Urahara", "Yoruichi Shihoin",
        "Genryusai Shigekuni Yamamoto", "Sosuke Aizen", "Byakuya Kuchiki",
        "Shunsui Kyoraku", "Toshiro Hitsugaya", "Kenpachi Zaraki",
        "Ichibei Hyosube", "Rukia Kuchiki", "Isshin Kurosaki", "Gin Ichimaru",
        "Retsu Unohana", "Jushiro Ukitake", "Mayuri Kurotsuchi", "Renji Abarai",
        "Kaien Shiba", "Oetsu Nimaiya", "Senjumaru Shutara", "Tenjiro Kirinji",
        "Kirio Hikifune", "Soi Fon", "Sajin Komamura", "Rangiku Matsumoto",
        "Yachiru Kusajishi", "Ikkaku Madarame", "Ginrei Kuchiki",
        "Tessai Tsukabishi", "Izuru Kira", "Momo Hinamori", "Tetsuzaemon Iba",
        "Nanao Ise", "Nemu Kurotsuchi", "Yumichika Ayasegawa", "Kukaku Shiba",
        "Chojiro Sasakibe", "Isane Kotetsu", "Marechiyo Omaeda",
        "Hanataro Yamada", "Kiyone Kotetsu", "Sentaro Kotsubaki",
        "Makizo Aramaki", "Kaname Tosen", "Shuhei Hisagi", "Shusuke Amagai",
        "Sojun Kuchiki", "Kenpachi Kiganjo", "Kuruyashiki Kenpachi",
        "Tokinada Tsunayashiro", "Hikone Ubuginu", "Kageroza Inaba", "Muramasa",
        "Ohana Katen", "Okyo Kyokotsu", "Go Koga", "Senna", "Makoto Kibune",
        "Sojiro Kusaka", "Oko Yushima", "Ouko Yushima", "Maki Ichinose",
        "Hanza Nukui", "Lurichiyo Kasumiōji", "Gyakuaku Kumoi",
        # --- zanpakuto spirits that are roster characters (also weapons) ---
        "Sogyo no Kotowari", "Hozukimaru", "Suzumebachi", "Hisagomaru",
        "Narunosuke", "Shintaro", "Tenken", "Zabimaru", "Ashisogi Jizo",
        "Kazeshini", "Kokuto", "Ruri'iro Kujaku", "Haineko", "Gonryomaru",
        "Wabisuke", "Tobiume", "Gegetsuburi", "Kirikaze", "Taikun", "Garogai",
        "Homura", "Shizuku",
        # --- craftable characters ---
        "Aizen (First Fusion)", "Aizen (Chrysalis)", "Aizen (Butterfly)",
        "Aizen (Monster)", "Aizen (Final Fusion)",
        "Ichigo (Substitute Shinigami)", "Ichigo (Shikai)", "Ichigo (Bankai)",
        "Ichigo (Dangai / Mugetsu)", "Ichigo (True Shikai / Dual Blades)",
        "Ichigo (Horn of Salvation / True Bankai)",
        "Yamamoto (Bankai)", "Soi Fon (Bankai)", "Gin (Bankai)",
        "Unohana (Bankai)", "Byakuya (Bankai)", "Komamura (Bankai)",
        "Shunsui (Bankai)", "Tosen (Bankai)", "Hitsugaya (Bankai)",
        "Kenpachi (Bankai)", "Mayuri (Bankai)", "Ukitake (Bankai)",
        "Renji (Soo Zabimaru)", "Rukia (Hakka no Togame)", "Izuru (Wabisuke)",
        "Momo (Tobiume)", "Hisagi (Kazeshini)", "Rangiku (Haineko)",
        "Yachiru (Sanpo Kenju)", "Isane (Itegumo)", "Iba (Zanpakuto)",
        "Nanao (Kido)", "Nemu (Poison Body)",
        # --- weapons ---
        "Tensa Zangetsu", "Zanka no Tachi", "Kyoka Suigetsu",
        "Senbonzakura Kageyoshi", "Daiguren Hyorinmaru", "Nozarashi",
        "Kamishini no Yari", "Katen Kyokotsu Karamatsu Shinju", "Minazuki",
        "Hakka no Togame", "Kannonbiraki Benihime Aratame", "Ryujin Jakka",
        "Konjiki Ashisogi Jizo", "Soo Zabimaru", "Zangetsu", "Ichimonji",
        "Hyorinmaru", "Benihime", "Katen Kyokotsu", "Sode no Shirayuki",
        "Senbonzakura", "Shinso", "Kokujo Tengen Myo'o", "Jakuho Raikoben",
        "Nejibana", "Ryumon Hozukimaru", "Sealed Nozarashi",
    ],

    "vizard": [
        # --- characters ---
        "Shinji Hirako", "Hiyori Sarugaki", "Love Aikawa", "Rose Otoribashi",
        "Mashiro Kuna", "Lisa Yadomaru", "Hachigen Ushoda", "Kensei Muguruma",
        # --- craftable characters ---
        "Ichigo (Hollow Mask / Visored)", "Shinji (Hollow Mask)",
        "Kensei (Hollow Mask)", "Rose (Hollow Mask)", "Love (Hollow Mask)",
        "Hiyori (Hollow Mask)", "Lisa (Hollow Mask)", "Mashiro (Hollow Mask)",
        "Hachi (Hollow Mask)",
        # --- zanpakuto (character + weapon share the name) ---
        "Sakanade",
        # --- weapons ---
        "Sakashima Yokoshima Happo Fusagari", "Kinshara Butodan",
        "Tekken Tachikaze", "Tachikaze", "Kinshara", "Haguro Tonbo",
    ],

    "quincy": [
        # --- characters ---
        "Yhwach", "Jugram Haschwalth", "Uryu Ishida", "Askin Nakk Le Vaar",
        "Gremmy Thoumeaux", "Gerard Valkyrie", "Lille Barro",
        "Pernida Parnkgjas", "Bambietta Basterbine", "Bazz-B", "Quilge Opie",
        "Royd Lloyd", "Loyd Lloyd", "Candice Catnipp", "Cang Du",
        "Driscoll Berci", "Giselle Gewelle", "Liltotto Lamperd",
        "Meninas McAllon", "NaNaNa Najahkoop", "Robert Accutrone", "BG9",
        "Äs Nödt", "Mask De Masculine", "Ryuken Ishida", "Masaki Kurosaki",
        "Nianzol Weizol", "PePe Waccabrada", "Shaz Domino",
        # --- craftable characters ---
        "Yhwach (The Almighty Awakened)", "Yhwach (Soul King Absorbed)",
        "Yhwach (True Soul King / God Form)", "Quilge Opie (Biskiel)",
        "Bambietta (Zofiel)", "Candice (Barbarriel)", "Äs Nödt (Tatarforas)",
        "Lille Barro (Jilliel)", "Gerard (Aschetonig)", "Pernida (Vollständig)",
        "Askin (Hasshein)", "Bazz-B (Vollständig)",
        "Mask De Masculine (Vollständig)", "Robert Accutrone (Grimaniel)",
        "Giselle (Azhalbiora)", "Liltotto (Vollständig)",
        "Meninas (Vollständig)",
        # --- weapons ---
        "Kruzifix", "Freund Schild", "Diagramm", "Tatar Foras", "Ginrei Kojaku",
    ],

    "hollow": [
        # --- characters (Espada, Fraccion, Arrancar, Hollows) ---
        "Ulquiorra Cifer", "Coyote Starrk", "Barragan Louisenbairn",
        "Grimmjow Jaegerjaquez", "Nelliel Tu Odelschwanck", "Tier Harribel",
        "Nnoitra Gilga", "Szayelaporro Granz", "Zommari Rureaux",
        "Aaroniero Arruruerie", "Yammy Llargo", "Wonderweiss Margela",
        "Luppi Antenor", "Tesra Lindocruz", "Lilynette Gingerbuck",
        "Pesche Guatiche", "Dondochakka Birstanne", "Emilou Apacci",
        "Franceska Mila Rose", "Cyan Sun-Sun", "Abirama Redder",
        "Findorr Calius", "Shawlong Koufang", "Yylfordt Granz",
        "Nirgge Parduoc", "Ggio Vega", "Dordoni Alessandro Del Socaccio",
        "Cirucci Sanderwicci", "Gantenbainne Mosqueda", "Rudbornn Chelute",
        "Charlotte Chuhlhourne", "Edrad Liones", "Choe Neng Poww",
        "Roka Paramia", "Grand Fisher",
        # --- craftable characters ---
        "Ichigo (Vasto Lorde / Full Hollow)",
        "Ulquiorra (Resurreccion: Murcielago)", "Coyote Starrk (Los Lobos)",
        "Baraggan (Arrogante)", "Tier Harribel (Tiburon)", "Nelliel (Gamuza)",
        "Grimmjow (Pantera)", "Nnoitra (Santa Teresa)", "Zommari (Brujeria)",
        "Szayelaporro (Fornicaras)", "Aaroniero (Glotoneria)", "Yammy (Ira)",
        # --- weapons ---
        "Murcielago", "Los Lobos", "Pantera", "Gamuza", "Tiburon",
        "Santa Teresa", "Fornicaras", "Brujeria", "Glotoneria", "Ira",
    ],

    "fullbringer": [
        # --- characters (Xcution) ---
        "Kugo Ginjo", "Shukuro Tsukishima", "Riruka Dokugamine",
        "Yukio Hans Vorarlberna", "Jackie Tristan", "Moe Shishigawara",
        "Giriko Kutsuzawa", "Aura Michibane",
        # --- craftable characters ---
        "Ginjo (Fullbring: Cross of Scaffold)", "Ginjo (Armor Form / Bankai)",
        "Ichigo (Fullbring)",
    ],
}

# Deliberately in no faction: humans, Bount, modified souls, Adnyeus and the
# Soul King. They still exist and are obtainable everywhere else - they just
# never show up in a faction shop page or a faction card template.
UNAFFILIATED = [
    "Orihime Inoue", "Yasutora Sado", "Tatsuki Arisawa", "Kazui Kurosaki",
    "Yuzu Kurosaki", "Karin Kurosaki", "Kon", "Keigo Asano", "Mizuiro Kojima",
    "Chizuru Honsho", "Don Kanonji", "Jinta Hanakari", "Ururu Tsumugiya",
    "Ganju Shiba", "Ikumi Unagiya", "Kaoru Unagiya", "Nozomi Kujo",
    "Adnyeus", "Soul King (True Form)",
    # Bount and other doll users
    "Jin Kariya", "Shuren", "Ganryu", "Yoshino Soma", "Ban", "Jai", "Riyan",
    "Kurudo", "Ryu Kuzu", "Bau", "Mue", "Enryu", "Kenryu", "Noba", "Ririn",
    "Mabashi", "Gesell", "Sawatari", "Ugaki", "Yoshi", "Yang", "Yin",
    "Gunjo", "Jinnai Douko", "Genga", "Benin", "Ho",
]

# name -> one of the 5 groups
_FACTION_BY_NAME = {name: faction
                    for faction, names in FACTION_MEMBERS.items()
                    for name in names}


def faction_of(name: str) -> str:
    """The 5-group faction key for a character OR weapon name, or ''."""
    return _FACTION_BY_NAME.get(name, "")


# ---------------------------------------------------------------------------
# 4-faction view used by card templates / stat colours (/admin edit
# faction-template only has Soul Reaper / Quincy / Hollow / Full Bringer, so
# Vizard cards keep using the Soul Reaper look, exactly as before).
# ---------------------------------------------------------------------------

def _card_faction(faction: str) -> str:
    return "soul_reaper" if faction == "vizard" else faction


CHARACTER_FACTIONS = {name: _card_faction(f) for name, f in _FACTION_BY_NAME.items()}

# Kept because cards/render.py imports it. Everything is in
# CHARACTER_FACTIONS now, so there is nothing extra to list.
COMPLETION_EXTRA_FACTIONS: dict = {}


def weapon_faction(weapon_name: str) -> str:
    """Card-template faction (4-faction view) for a weapon, by name."""
    return CHARACTER_FACTIONS.get(weapon_name, "")


# ---------------------------------------------------------------------------
# /collection completion tabs, /admin spawn, /admin bossbattle, /shop
# ---------------------------------------------------------------------------

# Kept for anything that imports it: every Vizard-group name.
VISORED_NAMES = set(FACTION_MEMBERS["vizard"])


def completion_group(char_name: str) -> str:
    """Which of the 5 groups ('soul_reaper', 'vizard', 'quincy', 'hollow',
    'fullbringer') a character or weapon belongs to, or '' for none."""
    return faction_of(char_name)


ADMIN_FACTION_CHOICES = [
    ("Soul Reaper", "soul_reaper"),
    ("Vizard", "vizard"),
    ("Quincy", "quincy"),
    ("Hollow", "hollow"),
    ("Full Bringer", "fullbringer"),
]
ADMIN_FACTION_LABELS = {value: label for label, value in ADMIN_FACTION_CHOICES}

# Boss categories (seed_bossbattle.py) -> faction. "Final Boss" (Aizen /
# Yhwach) and "Crafting Boss" have no single faction, so no faction pick
# ever matches them - leave the faction empty to include them.
BOSS_CATEGORY_FACTIONS = {
    "Captain": "soul_reaper",
    "Lieutenant": "soul_reaper",
    "Visored": "vizard",
    "Sternritter": "quincy",
    "Espada": "hollow",
    "Fullbringer": "fullbringer",
}


def character_in_faction(char_name: str, faction: str) -> bool:
    """True if this character belongs to `faction` (an ADMIN_FACTION_CHOICES
    value) - same grouping as the /collection completion tabs."""
    return completion_group(char_name) == faction


def boss_categories_for_faction(faction: str) -> set:
    """The bossbattle_bosses.category values that belong to `faction`."""
    return {cat for cat, fac in BOSS_CATEGORY_FACTIONS.items() if fac == faction}


# ---------------------------------------------------------------------------
# Self-check: `python factions.py` from the project folder lists anyone in the
# database that no list above mentions (e.g. a character added later).
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sqlite3
    from pathlib import Path

    db = Path(__file__).parent / "db" / "bleachdex.sqlite3"
    conn = sqlite3.connect(db)
    known = set(_FACTION_BY_NAME) | set(UNAFFILIATED)
    missing = [(kind, name) for kind, name in
               [("character", r[0]) for r in conn.execute("SELECT name FROM characters")] +
               [("weapon", r[0]) for r in conn.execute("SELECT name FROM weapons")]
               if name not in known]
    seen = set()
    for kind, name in missing:
        if name not in seen:
            print(f"not in any list: {name} ({kind})")
            seen.add(name)
    print(f"{len(seen)} name(s) not in any list.")