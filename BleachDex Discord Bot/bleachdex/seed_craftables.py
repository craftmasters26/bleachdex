"""
Seeds the craftable characters (peak forms) and their multi-ingredient
recipes from the Bleach card list + BleachDex recipe list.

Run standalone (`python3 seed_craftables.py`) or from Discord with
`/admin seed craftables` (single-process hosts have no shell). It's an
upsert by character name, so re-running after editing a number below
just updates the existing row + recipe instead of duplicating it.

Each craftable is a normal row in `characters` (craftable_only=1, see
db/craftables.py) that reuses its base character's artwork - swap in
real card art afterwards with /admin edit character. The base
characters (Sosuke Aizen, Ichigo Kurosaki, ...) must already exist in
the database (seed_roster.py / /admin seed roster); any craftable
whose base character is missing is skipped and reported.

Ingredient kinds (see db/craftables.py):
    drop       boss drops (owned_boss_drops)
    weapon     owned weapon cards, matched by weapon name
    character  owned character cards, matched by name - the base
               character, or the previous form in a chain

Entry format:
    (category, name, tier, hp, damage, ability_name, base_character,
     [(kind, item_name, qty), ...])

NOT OBTAINABLE YET - these recipe ingredients exist in the recipe list
but nothing in the bot hands them out today, so the recipes needing
them can't be completed until they exist:
    drops:   Reiatsu Fragment, Bankai Training Essence, Konpaku Fragment,
             Fullbring Focus, True Bankai Core
    weapons: Arrogante, Suzumushi, Enma Korogi, Sanpo Kenju, Itegumo,
             Tengumaru, Kubikiri Orochi

Boss drops are ONLY the items in the "Boss Drops" art folder (Almighty Eye,
Hollow Mask, Hogyoku, Quincy Cross, Sanrei Glove, Cross of Scaffold, Xcution
Badge, Shinigami Badge, Vasto Lorde, Horn of Salvation, Soul King's Heart,
Shin'eiyaku, Jigokucho and the 12 flowers). Everything else in a recipe is a
character or a weapon: e.g. the Bankai items are the mythic Bankai WEAPONS
(Zanka no Tachi, Senbonzakura Kageyoshi, ...). Where a Shikai weapon and its
Bankai weapon share a name (Minazuki, Nozarashi) - or the Bankai weapon
doesn't exist separately (Sogyo no Kotowari) - the recipe asks for 2 of that
weapon. (One leftover: Yhwach (Soul King Absorbed) still asks for the "Soul
King" drop, which is not in that folder.)
"""

from db.connection import init_db
from db import characters as ch, craftables as cf

CRAFTABLES = CRAFTABLES = [
    ('Aizen', 'Aizen (First Fusion)', 'mythic', 3050, 3150, 'Hogyoku Fusion',
     'Sosuke Aizen',
     [('character', 'Sosuke Aizen', 1), ('weapon', 'Kyoka Suigetsu', 1), ('drop', 'Hogyoku', 1), ('drop', 'Hollow Mask', 1)]),
    ('Aizen', 'Aizen (Chrysalis)', 'mythic', 3150, 3250, 'Chrysalis',
     'Sosuke Aizen',
     [('character', 'Aizen (First Fusion)', 1), ('drop', 'Hogyoku', 1), ('drop', 'Hollow Mask', 1), ('drop', "Shin'eiyaku", 1)]),
    ('Aizen', 'Aizen (Butterfly)', 'mythic', 3400, 3500, 'Butterfly Form',
     'Sosuke Aizen',
     [('character', 'Aizen (Chrysalis)', 1), ('drop', 'Hogyoku', 1), ('drop', 'Jigokuchō', 2)]),
    ('Aizen', 'Aizen (Monster)', 'mythic', 3500, 3600, 'Transcendent Reiatsu',
     'Sosuke Aizen',
     [('character', 'Aizen (Butterfly)', 1), ('drop', 'Hogyoku', 1), ('drop', 'Hollow Mask', 3), ('weapon', 'Kyoka Suigetsu', 1)]),
    ('Aizen', 'Aizen (Final Fusion)', 'mythic', 3800, 4250, 'Kyoka Suigetsu (Evolved)',
     'Sosuke Aizen',
     [('character', 'Aizen (Monster)', 1), ('drop', 'Hogyoku', 2), ('drop', 'Hollow Mask', 3), ('drop', 'Jigokuchō', 2)]),
    ('Ichigo', 'Ichigo (Substitute Shinigami)', 'epic', 2850, 2700, 'Zangetsu (Sealed)',
     'Ichigo Kurosaki',
     [('character', 'Ichigo Kurosaki', 1), ('drop', 'Hogyoku', 1), ('weapon', 'Zangetsu', 1), ('drop', 'Shinigami Badge', 1)]),
    ('Ichigo', 'Ichigo (Shikai)', 'epic', 2850, 2700, 'Zangetsu',
     'Ichigo Kurosaki',
     [('character', 'Ichigo (Substitute Shinigami)', 1), ('weapon', 'Zangetsu', 1), ('drop', 'Shinigami Badge', 1), ('drop', 'Reiatsu Fragment', 1)]),
    ('Ichigo', 'Ichigo (Bankai)', 'legendary', 2900, 2800, 'Tensa Zangetsu',
     'Ichigo Kurosaki',
     [('character', 'Ichigo (Shikai)', 1), ('weapon', 'Tensa Zangetsu', 1), ('drop', 'Bankai Training Essence', 1), ('drop', 'Konpaku Fragment', 1)]),
    ('Ichigo', 'Ichigo (Hollow Mask / Visored)', 'legendary', 3000, 2900, 'Hollow Mask',
     'Ichigo Kurosaki',
     [('character', 'Ichigo (Substitute Shinigami)', 1), ('drop', 'Hollow Mask', 3)]),
    ('Ichigo', 'Ichigo (Vasto Lorde / Full Hollow)', 'mythic', 3200, 3100, 'Full Hollow',
     'Ichigo Kurosaki',
     [('character', 'Ichigo (Hollow Mask / Visored)', 1), ('drop', 'Vasto Lorde', 2), ('drop', 'Hollow Mask', 1)]),
    ('Ichigo', 'Ichigo (Dangai / Mugetsu)', 'mythic', 3700, 4000, 'Mugetsu',
     'Ichigo Kurosaki',
     [('character', 'Ichigo (Vasto Lorde / Full Hollow)', 1), ('weapon', 'Tensa Zangetsu', 1), ('weapon', 'Zangetsu', 1)]),
    ('Ichigo', 'Ichigo (Fullbring)', 'epic', 2950, 2850, 'Fullbring',
     'Ichigo Kurosaki',
     [('character', 'Ichigo (Dangai / Mugetsu)', 1), ('drop', 'Xcution Badge', 2), ('drop', 'Fullbring Focus', 1)]),
    ('Ichigo', 'Ichigo (True Shikai / Dual Blades)', 'mythic', 3300, 3200, 'Dual Zangetsu',
     'Ichigo Kurosaki',
     [('character', 'Ichigo (Fullbring)', 1), ('weapon', 'Zangetsu', 1), ('drop', 'Quincy Cross', 3), ('drop', 'Hollow Mask', 3)]),
    ('Ichigo', 'Ichigo (Horn of Salvation / True Bankai)', 'mythic', 4000, 4500, 'True Bankai',
     'Ichigo Kurosaki',
     [('character', 'Ichigo (True Shikai / Dual Blades)', 1), ('drop', 'True Bankai Core', 1), ('drop', 'Horn of Salvation', 1), ('drop', 'Almighty Eye', 2)]),
    ('Yhwach', 'Yhwach (The Almighty Awakened)', 'mythic', 3200, 3300, 'The Almighty',
     'Yhwach',
     [('character', 'Yhwach', 1), ('drop', 'Almighty Eye', 1)]),
    ('Yhwach', 'Yhwach (Soul King Absorbed)', 'mythic', 3900, 4400, 'The Almighty + Soul King',
     'Yhwach',
     [('character', 'Yhwach (The Almighty Awakened)', 1), ('drop', 'Soul King', 1)]),
    ('Yhwach', 'Yhwach (True Soul King / God Form)', 'mythic', 4250, 4750, 'The Almighty',
     'Yhwach',
     [('character', 'Yhwach (Soul King Absorbed)', 1), ('drop', "Soul King's Heart", 1), ('drop', 'Almighty Eye', 1)]),
    ('Ulquiorra', 'Ulquiorra (Resurreccion: Murcielago)', 'mythic', 3150, 3200, 'Murcielago',
     'Ulquiorra Cifer',
     [('character', 'Ulquiorra Cifer', 1), ('weapon', 'Murcielago', 1), ('drop', 'Hollow Mask', 1)]),
    ('Ginjo', 'Ginjo (Fullbring: Cross of Scaffold)', 'legendary', 2700, 2700, 'Cross of Scaffold',
     'Kugo Ginjo',
     [('character', 'Kugo Ginjo', 1), ('drop', 'Cross of Scaffold', 1), ('drop', 'Xcution Badge', 1)]),
    ('Ginjo', 'Ginjo (Armor Form / Bankai)', 'legendary', 2800, 2800, 'Cross of Scaffold',
     'Kugo Ginjo',
     [('character', 'Ginjo (Fullbring: Cross of Scaffold)', 1), ('character', 'Ichigo (Fullbring)', 1), ('drop', 'Jigokuchō', 1)]),
    ('Espada Resurrección', 'Coyote Starrk (Los Lobos)', 'legendary', 3000, 3050, 'Los Lobos',
     'Coyote Starrk',
     [('character', 'Coyote Starrk', 1), ('weapon', 'Los Lobos', 1), ('drop', 'Hogyoku', 1)]),
    ('Espada Resurrección', 'Baraggan (Arrogante)', 'legendary', 1485, 1450, 'Respira Aging',
     'Barragan Louisenbairn',
     [('character', 'Barragan Louisenbairn', 1), ('weapon', 'Arrogante', 1), ('drop', 'Hogyoku', 1)]),
    ('Espada Resurrección', 'Tier Harribel (Tiburon)', 'epic', 2700, 2700, 'Tiburon',
     'Tier Harribel',
     [('character', 'Tier Harribel', 1), ('weapon', 'Tiburon', 1), ('drop', 'Hogyoku', 1)]),
    ('Espada Resurrección', 'Nelliel (Gamuza)', 'legendary', 2900, 2850, 'Gamuza',
     'Nelliel Tu Odelschwanck',
     [('character', 'Nelliel Tu Odelschwanck', 1), ('weapon', 'Gamuza', 1), ('drop', 'Hogyoku', 1)]),
    ('Espada Resurrección', 'Grimmjow (Pantera)', 'legendary', 1463, 1475, 'Desgarron Claws',
     'Grimmjow Jaegerjaquez',
     [('character', 'Grimmjow Jaegerjaquez', 1), ('weapon', 'Pantera', 1), ('drop', 'Hogyoku', 1)]),
    ('Espada Resurrección', 'Nnoitra (Santa Teresa)', 'epic', 2950, 3000, 'Santa Teresa',
     'Nnoitra Gilga',
     [('character', 'Nnoitra Gilga', 1), ('weapon', 'Santa Teresa', 1), ('drop', 'Hogyoku', 1)]),
    ('Espada Resurrección', 'Zommari (Brujeria)', 'rare', 2700, 2700, 'Amor',
     'Zommari Rureaux',
     [('character', 'Zommari Rureaux', 1), ('weapon', 'Brujeria', 1), ('drop', 'Hogyoku', 1)]),
    ('Espada Resurrección', 'Szayelaporro (Fornicaras)', 'epic', 2700, 2700, 'Fornicaras',
     'Szayelaporro Granz',
     [('character', 'Szayelaporro Granz', 1), ('weapon', 'Fornicaras', 1), ('drop', 'Hogyoku', 1)]),
    ('Espada Resurrección', 'Aaroniero (Glotoneria)', 'rare', 2700, 2700, 'Glotoneria',
     'Aaroniero Arruruerie',
     [('character', 'Aaroniero Arruruerie', 1), ('weapon', 'Glotoneria', 1), ('drop', 'Hogyoku', 1)]),
    ('Espada Resurrección', 'Yammy (Ira)', 'legendary', 2850, 2800, 'Ira',
     'Yammy Llargo',
     [('character', 'Yammy Llargo', 1), ('weapon', 'Ira', 1), ('drop', 'Hogyoku', 1)]),
    ('Quincy Vollständig', 'Quilge Opie (Biskiel)', 'epic', 2650, 2650, 'The Jail',
     'Quilge Opie',
     [('character', 'Quilge Opie', 1), ('drop', 'Sanrei Glove', 1), ('drop', 'Quincy Cross', 1)]),
    ('Quincy Vollständig', 'Bambietta (Zofiel)', 'epic', 2650, 2650, 'The Explode',
     'Bambietta Basterbine',
     [('character', 'Bambietta Basterbine', 1), ('drop', 'Sanrei Glove', 1), ('drop', 'Quincy Cross', 1)]),
    ('Quincy Vollständig', 'Candice (Barbarriel)', 'rare', 2600, 2600, 'Galvano Blast',
     'Candice Catnipp',
     [('character', 'Candice Catnipp', 1), ('drop', 'Sanrei Glove', 1), ('drop', 'Quincy Cross', 1)]),
    ('Quincy Vollständig', 'Äs Nödt (Tatarforas)', 'legendary', 2600, 2600, 'The Fear',
     'Äs Nödt',
     [('character', 'Äs Nödt', 1), ('drop', 'Sanrei Glove', 1), ('drop', 'Quincy Cross', 1)]),
    ('Quincy Vollständig', 'Lille Barro (Jilliel)', 'legendary', 3050, 3150, 'The X-Axis',
     'Lille Barro',
     [('character', 'Lille Barro', 1), ('drop', 'Sanrei Glove', 1), ('drop', 'Quincy Cross', 1)]),
    ('Quincy Vollständig', 'Gerard (Aschetonig)', 'legendary', 2850, 2800, 'The Miracle',
     'Gerard Valkyrie',
     [('character', 'Gerard Valkyrie', 1), ('drop', 'Sanrei Glove', 1), ('drop', 'Quincy Cross', 1)]),
    ('Quincy Vollständig', 'Pernida (Vollständig)', 'legendary', 2650, 2650, 'The Compulsory',
     'Pernida Parnkgjas',
     [('character', 'Pernida Parnkgjas', 1), ('drop', 'Sanrei Glove', 1), ('drop', 'Quincy Cross', 1)]),
    ('Quincy Vollständig', 'Askin (Hasshein)', 'legendary', 2750, 2750, 'Deathdealing',
     'Askin Nakk Le Vaar',
     [('character', 'Askin Nakk Le Vaar', 1), ('drop', 'Sanrei Glove', 1), ('drop', 'Quincy Cross', 1)]),
    ('Quincy Vollständig', 'Bazz-B (Vollständig)', 'epic', 2600, 2600, 'Burner Finger',
     'Bazz-B',
     [('character', 'Bazz-B', 1), ('drop', 'Sanrei Glove', 1), ('drop', 'Quincy Cross', 1)]),
    ('Quincy Vollständig', 'Mask De Masculine (Vollständig)', 'legendary', 2650, 2650, 'The Superstar',
     'Mask De Masculine',
     [('character', 'Mask De Masculine', 1), ('drop', 'Sanrei Glove', 1), ('drop', 'Quincy Cross', 1)]),
    ('Quincy Vollständig', 'Robert Accutrone (Grimaniel)', 'rare', 2650, 2650, 'Quincy Guns',
     'Robert Accutrone',
     [('character', 'Robert Accutrone', 1), ('drop', 'Sanrei Glove', 1), ('drop', 'Quincy Cross', 1)]),
    ('Quincy Vollständig', 'Giselle (Azhalbiora)', 'rare', 2650, 2650, 'The Zombie',
     'Giselle Gewelle',
     [('character', 'Giselle Gewelle', 1), ('drop', 'Sanrei Glove', 1), ('drop', 'Quincy Cross', 1)]),
    ('Quincy Vollständig', 'Liltotto (Vollständig)', 'rare', 2650, 2650, 'The Glutton',
     'Liltotto Lamperd',
     [('character', 'Liltotto Lamperd', 1), ('drop', 'Sanrei Glove', 1), ('drop', 'Quincy Cross', 1)]),
    ('Quincy Vollständig', 'Meninas (Vollständig)', 'rare', 2650, 2650, 'The Power',
     'Meninas McAllon',
     [('character', 'Meninas McAllon', 1), ('drop', 'Sanrei Glove', 1), ('drop', 'Quincy Cross', 1)]),
    ('Soul Reaper Captains', 'Yamamoto (Bankai)', 'mythic', 3300, 3400, 'Zanka no Tachi',
     'Genryusai Shigekuni Yamamoto',
     [('character', 'Genryusai Shigekuni Yamamoto', 1), ('weapon', 'Ryujin Jakka', 1), ('weapon', 'Zanka no Tachi', 1), ('drop', 'Jigokuchō', 2), ('drop', 'Chrysanthemum', 1)]),
    ('Soul Reaper Captains', 'Soi Fon (Bankai)', 'legendary', 2750, 2750, 'Jakuho Raikoben',
     'Soi Fon',
     [('character', 'Soi Fon', 1), ('weapon', 'Suzumebachi', 1), ('weapon', 'Jakuho Raikoben', 1), ('drop', 'Jigokuchō', 2), ('drop', 'Pasque Flower', 1)]),
    ('Soul Reaper Captains', 'Gin (Bankai)', 'legendary', 2800, 2800, 'Kamishini no Yari',
     'Gin Ichimaru',
     [('character', 'Gin Ichimaru', 1), ('weapon', 'Shinso', 1), ('weapon', 'Kamishini no Yari', 1), ('drop', 'Jigokuchō', 2), ('drop', 'Marigold', 1)]),
    ('Soul Reaper Captains', 'Unohana (Bankai)', 'mythic', 3100, 3150, 'Minazuki (Bankai)',
     'Retsu Unohana',
     [('character', 'Retsu Unohana', 1), ('weapon', 'Minazuki', 2), ('drop', 'Jigokuchō', 2), ('drop', 'Bellflower', 1)]),
    ('Soul Reaper Captains', 'Byakuya (Bankai)', 'mythic', 3000, 3100, 'Senbonzakura Kageyoshi',
     'Byakuya Kuchiki',
     [('character', 'Byakuya Kuchiki', 1), ('weapon', 'Senbonzakura', 1), ('weapon', 'Senbonzakura Kageyoshi', 1), ('drop', 'Jigokuchō', 2), ('drop', 'Camellia', 1)]),
    ('Soul Reaper Captains', 'Komamura (Bankai)', 'legendary', 2900, 2850, "Kokujo Tengen Myo'o",
     'Sajin Komamura',
     [('character', 'Sajin Komamura', 1), ('weapon', 'Tenken', 1), ('weapon', "Kokujo Tengen Myo'o", 1), ('drop', 'Jigokuchō', 2), ('drop', 'Iris', 1)]),
    ('Soul Reaper Captains', 'Shunsui (Bankai)', 'mythic', 3100, 3150, 'Katen Kyokotsu: Karamatsu Shinju',
     'Shunsui Kyoraku',
     [('character', 'Shunsui Kyoraku', 1), ('weapon', 'Katen Kyokotsu', 1), ('weapon', 'Katen Kyokotsu Karamatsu Shinju', 1), ('drop', 'Jigokuchō', 2), ('drop', 'Bird of Paradise', 1)]),
    ('Soul Reaper Captains', 'Tosen (Bankai)', 'legendary', 2950, 3000, 'Suzumushi Tsuishiki: Enma Korogi',
     'Kaname Tosen',
     [('character', 'Kaname Tosen', 1), ('weapon', 'Suzumushi', 1), ('weapon', 'Enma Korogi', 1), ('drop', 'Jigokuchō', 2), ('drop', 'White Poppy', 1)]),
    ('Soul Reaper Captains', 'Hitsugaya (Bankai)', 'mythic', 3000, 3100, 'Daiguren Hyorinmaru',
     'Toshiro Hitsugaya',
     [('character', 'Toshiro Hitsugaya', 1), ('weapon', 'Hyorinmaru', 1), ('weapon', 'Daiguren Hyorinmaru', 1), ('drop', 'Jigokuchō', 2), ('drop', 'Daffodil', 1)]),
    ('Soul Reaper Captains', 'Kenpachi (Bankai)', 'mythic', 3250, 3350, 'Bankai',
     'Kenpachi Zaraki',
     [('character', 'Kenpachi Zaraki', 1), ('weapon', 'Nozarashi', 2), ('drop', 'Jigokuchō', 2), ('drop', 'Yarrow', 1)]),
    ('Soul Reaper Captains', 'Mayuri (Bankai)', 'legendary', 2800, 2800, 'Konjiki Ashisogi Jizo',
     'Mayuri Kurotsuchi',
     [('character', 'Mayuri Kurotsuchi', 1), ('weapon', 'Ashisogi Jizo', 1), ('weapon', 'Konjiki Ashisogi Jizo', 1), ('drop', 'Jigokuchō', 2), ('drop', 'Thistle', 1)]),
    ('Soul Reaper Captains', 'Ukitake (Bankai)', 'mythic', 2950, 2950, 'Sogyo no Kotowari (Bankai)',
     'Jushiro Ukitake',
     [('character', 'Jushiro Ukitake', 1), ('weapon', 'Sogyo no Kotowari', 2), ('drop', 'Jigokuchō', 2), ('drop', 'Snowdrop', 1)]),
    ('Soul Reaper Lieutenants', 'Renji (Soo Zabimaru)', 'legendary', 2850, 2800, 'Soo Zabimaru',
     'Renji Abarai',
     [('character', 'Renji Abarai', 1), ('weapon', 'Zabimaru', 1), ('drop', 'Camellia', 1), ('drop', 'Jigokuchō', 2)]),
    ('Soul Reaper Lieutenants', 'Rukia (Hakka no Togame)', 'legendary', 2800, 2750, 'Hakka no Togame',
     'Rukia Kuchiki',
     [('character', 'Rukia Kuchiki', 1), ('weapon', 'Sode no Shirayuki', 1), ('drop', 'Snowdrop', 1), ('drop', 'Jigokuchō', 2)]),
    ('Soul Reaper Lieutenants', 'Izuru (Wabisuke)', 'rare', 2600, 2600, 'Wabisuke',
     'Izuru Kira',
     [('character', 'Izuru Kira', 1), ('weapon', 'Wabisuke', 1), ('drop', 'Marigold', 1), ('drop', 'Jigokuchō', 2)]),
    ('Soul Reaper Lieutenants', 'Momo (Tobiume)', 'rare', 2550, 2550, 'Tobiume',
     'Momo Hinamori',
     [('character', 'Momo Hinamori', 1), ('weapon', 'Tobiume', 1), ('drop', 'Lily of the Valley', 1), ('drop', 'Jigokuchō', 2)]),
    ('Soul Reaper Lieutenants', 'Hisagi (Kazeshini)', 'epic', 2650, 2650, 'Kazeshini',
     'Shuhei Hisagi',
     [('character', 'Shuhei Hisagi', 1), ('weapon', 'Kazeshini', 1), ('drop', 'White Poppy', 1), ('drop', 'Jigokuchō', 2)]),
    ('Soul Reaper Lieutenants', 'Rangiku (Haineko)', 'epic', 2300, 2250, 'Ash Cloud',
     'Rangiku Matsumoto',
     [('character', 'Rangiku Matsumoto', 1), ('weapon', 'Haineko', 1), ('drop', 'Daffodil', 1), ('drop', 'Jigokuchō', 2)]),
    ('Soul Reaper Lieutenants', 'Yachiru (Sanpo Kenju)', 'epic', 2600, 2600, 'Sanpo Kenju',
     'Yachiru Kusajishi',
     [('character', 'Yachiru Kusajishi', 1), ('weapon', 'Sanpo Kenju', 1), ('drop', 'Yarrow', 1), ('drop', 'Jigokuchō', 2)]),
    ('Soul Reaper Lieutenants', 'Isane (Itegumo)', 'uncommon', 2550, 2550, 'Itegumo',
     'Isane Kotetsu',
     [('character', 'Isane Kotetsu', 1), ('weapon', 'Itegumo', 1), ('drop', 'Bellflower', 1), ('drop', 'Jigokuchō', 2)]),
    ('Soul Reaper Lieutenants', 'Iba (Zanpakuto)', 'uncommon', 2550, 2550, 'Zanpakuto',
     'Tetsuzaemon Iba',
     [('character', 'Tetsuzaemon Iba', 1), ('drop', 'Iris', 1), ('drop', 'Jigokuchō', 2)]),
    ('Soul Reaper Lieutenants', 'Nanao (Kido)', 'rare', 2550, 2550, 'Kido',
     'Nanao Ise',
     [('character', 'Nanao Ise', 1), ('drop', 'Bird of Paradise', 1), ('drop', 'Jigokuchō', 2)]),
    ('Soul Reaper Lieutenants', 'Nemu (Poison Body)', 'rare', 2600, 2600, 'Poison Body',
     'Nemu Kurotsuchi',
     [('character', 'Nemu Kurotsuchi', 1), ('drop', 'Thistle', 1), ('drop', 'Jigokuchō', 2)]),
    ('Visored', 'Shinji (Hollow Mask)', 'legendary', 2900, 2850, 'Sakanade',
     'Shinji Hirako',
     [('character', 'Shinji Hirako', 1), ('weapon', 'Sakanade', 1), ('drop', 'Hollow Mask', 1)]),
    ('Visored', 'Kensei (Hollow Mask)', 'legendary', 2800, 2750, 'Tekken Tachikaze',
     'Kensei Muguruma',
     [('character', 'Kensei Muguruma', 1), ('weapon', 'Tachikaze', 1), ('drop', 'Hollow Mask', 1)]),
    ('Visored', 'Rose (Hollow Mask)', 'legendary', 2700, 2700, 'Kinshara',
     'Rose Otoribashi',
     [('character', 'Rose Otoribashi', 1), ('weapon', 'Kinshara', 1), ('drop', 'Hollow Mask', 1)]),
    ('Visored', 'Love (Hollow Mask)', 'legendary', 2650, 2650, 'Tengumaru',
     'Love Aikawa',
     [('character', 'Love Aikawa', 1), ('weapon', 'Tengumaru', 1), ('drop', 'Hollow Mask', 1)]),
    ('Visored', 'Hiyori (Hollow Mask)', 'epic', 2600, 2600, 'Kubikiri Orochi',
     'Hiyori Sarugaki',
     [('character', 'Hiyori Sarugaki', 1), ('weapon', 'Kubikiri Orochi', 1), ('drop', 'Hollow Mask', 1)]),
    ('Visored', 'Lisa (Hollow Mask)', 'epic', 2600, 2600, 'Haguro Tonbo',
     'Lisa Yadomaru',
     [('character', 'Lisa Yadomaru', 1), ('weapon', 'Haguro Tonbo', 1), ('drop', 'Hollow Mask', 1)]),
    ('Visored', 'Mashiro (Hollow Mask)', 'epic', 2600, 2600, 'Vizard Mask',
     'Mashiro Kuna',
     [('character', 'Mashiro Kuna', 1), ('drop', 'Hollow Mask', 1)]),
    ('Visored', 'Hachi (Hollow Mask)', 'epic', 2700, 2650, 'Kido Barriers',
     'Hachigen Ushoda',
     [('character', 'Hachigen Ushoda', 1), ('drop', 'Hollow Mask', 1)]),
    ('Soul King', 'Soul King (True Form)', 'mythic', 4500, 5000, 'Soul King Reiatsu',
     'Adnyeus',
     []),
]


def seed_craftables() -> dict:
    """Returns {"created": n, "updated": n, "skipped": [(name, reason)]}."""
    init_db()
    created = updated = 0
    skipped: list[tuple[str, str]] = []

    for category, name, tier, hp, dmg, ability, base_name, ingredients in CRAFTABLES:
        base = ch.find_character_by_name(base_name, enabled_only=False)
        if base is None:
            skipped.append((name, f"base character '{base_name}' isn't in the database"))
            continue
        try:
            _, was_created = cf.upsert_craftable(
                name=name,
                image_path=base.image_path,
                card_image_path=base.card_image_path or "",
                hp=hp,
                attack=dmg,
                tier=tier,
                ability_name=ability,
                ability_description="",
                category=category,
                ingredients=[cf.Ingredient(k, n, q) for k, n, q in ingredients],
            )
        except cf.CraftError as e:
            skipped.append((name, str(e)))
            continue
        if was_created:
            created += 1
        else:
            updated += 1

    return {"created": created, "updated": updated, "skipped": skipped}


if __name__ == "__main__":
    result = seed_craftables()
    print(f"Craftables: {result['created']} created, {result['updated']} updated, "
          f"{len(result['skipped'])} skipped.")
    for name, reason in result["skipped"]:
        print(f"  skipped {name}: {reason}")