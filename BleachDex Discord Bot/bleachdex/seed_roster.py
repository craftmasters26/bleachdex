"""
One-time seed script: adds every character & weapon from the master
Bleach roster (name, tier, HP/ATK, ability name + description, and
spawn artwork pulled straight from soul.py / zanpaku.py's GitHub
links) into the database in one go.

Run once from the project root (same folder as bot.py):
    python seed_roster.py

Safe to re-run - characters/weapons already in the database (matched
by name) are never duplicated. If you've changed a character's HP,
ATK, tier, or ability text in the CHARACTERS list below, re-running
this script now updates that existing row in place (image_path,
card_template_path, and card_image_path are left untouched, so any
custom card art you've set via /admin edit character is preserved).
If nothing changed, the row is left alone.

WHAT THIS DOES NOT DO: it does not touch card_image_path or
card_template_path. That means /card view and pack reveals will show
the plain spawn artwork (same as CHARACTER_IMAGES/WEAPON_IMAGES) until
you run /admin edit character (or /admin edit weapon) per entry to
pick real card art from card.py - exactly like you asked, that part
stays manual.
"""

import asyncio
from pathlib import Path
from urllib.parse import unquote

import aiohttp

from db import characters as ch, weapons as wp, collection as coll
from db.connection import init_db
from soul import CHARACTER_IMAGES
from zanpaku import WEAPON_IMAGES

UPLOAD_DIR = Path(__file__).parent / "admin" / "static" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

CHARACTERS = CHARACTERS = [
    {"name": 'Ichigo Kurosaki', "tier": 'mythic', "hp": 2800, "atk": 2600, "ability_name": 'Getsuga Tensho', "ability_description": 'Fires a concentrated reiatsu slash.'},
    {"name": 'Kisuke Urahara', "tier": 'mythic', "hp": 2700, "atk": 2550, "ability_name": 'Benihime', "ability_description": 'Creates shields, nets, and destructive screams.'},
    {"name": 'Yoruichi Shihoin', "tier": 'mythic', "hp": 2600, "atk": 2650, "ability_name": 'Shunko', "ability_description": 'Coats body in lightning for speed and hakuda.'},
    {"name": 'Genryusai Shigekuni Yamamoto', "tier": 'mythic', "hp": 3000, "atk": 2800, "ability_name": 'Zanka no Tachi', "ability_description": 'Sun-hot flame bankai erases what it cuts.'},
    {"name": 'Sosuke Aizen', "tier": 'mythic', "hp": 2900, "atk": 2900, "ability_name": 'Kyoka Suigetsu', "ability_description": 'Complete hypnosis controls all five senses.'},
    {"name": 'Byakuya Kuchiki', "tier": 'mythic', "hp": 2700, "atk": 2600, "ability_name": 'Senbonzakura Kageyoshi', "ability_description": 'Thousand petal blades attack in swarms.'},
    {"name": 'Shunsui Kyoraku', "tier": 'mythic', "hp": 2750, "atk": 2650, "ability_name": 'Katen Kyokotsu', "ability_description": "Turns battle into deadly children's games."},
    {"name": 'Toshiro Hitsugaya', "tier": 'mythic', "hp": 2700, "atk": 2600, "ability_name": 'Daiguren Hyorinmaru', "ability_description": 'Ice bankai freezes and controls weather.'},
    {"name": 'Kenpachi Zaraki', "tier": 'mythic', "hp": 2900, "atk": 2850, "ability_name": 'Nozarashi', "ability_description": 'Massive cleaver cuts through almost anything.'},
    {"name": 'Ichibei Hyosube', "tier": 'mythic', "hp": 2800, "atk": 2750, "ability_name": 'Ichimonji', "ability_description": "Ink erases or renames a target's power."},
    {"name": 'Ulquiorra Cifer', "tier": 'mythic', "hp": 2750, "atk": 2750, "ability_name": 'Murcielago', "ability_description": 'Bat release with high-speed regen and Cero Oscuras.'},
    {"name": 'Yhwach', "tier": 'mythic', "hp": 3000, "atk": 2950, "ability_name": 'The Almighty', "ability_description": 'Sees and alters future outcomes.'},
    {"name": 'Jugram Haschwalth', "tier": 'mythic', "hp": 2800, "atk": 2750, "ability_name": 'The Balance', "ability_description": 'Redirects misfortune from allies to enemies.'},
    {"name": 'Rukia Kuchiki', "tier": 'legendary', "hp": 2500, "atk": 2400, "ability_name": 'Sode no Shirayuki', "ability_description": 'Ice dances freeze targets to absolute zero.'},
    {"name": 'Isshin Kurosaki', "tier": 'legendary', "hp": 2600, "atk": 2300, "ability_name": 'Engetsu', "ability_description": 'Fire-type Getsuga Tensho.'},
    {"name": 'Gin Ichimaru', "tier": 'legendary', "hp": 2500, "atk": 2550, "ability_name": 'Kamishini no Yari', "ability_description": 'Extends and leaves lethal poison.'},
    {"name": 'Retsu Unohana', "tier": 'legendary', "hp": 2600, "atk": 2500, "ability_name": 'Minazuki', "ability_description": 'Heals allies or melts enemies with acid.'},
    {"name": 'Jushiro Ukitake', "tier": 'legendary', "hp": 2600, "atk": 2400, "ability_name": 'Sogyo no Kotowari', "ability_description": 'Absorbs and redirects attacks.'},
    {"name": 'Mayuri Kurotsuchi', "tier": 'legendary', "hp": 2500, "atk": 2550, "ability_name": 'Konjiki Ashisogi Jizo', "ability_description": 'Poison cloud and paralyzing baby.'},
    {"name": 'Renji Abarai', "tier": 'legendary', "hp": 2550, "atk": 2400, "ability_name": 'Soo Zabimaru', "ability_description": 'Bone cannon fires massive reiatsu blast.'},
    {"name": 'Orihime Inoue', "tier": 'legendary', "hp": 2350, "atk": 1900, "ability_name": 'Shun Shun Rikka', "ability_description": 'Rejects events, healing or shielding.'},
    {"name": 'Yasutora Sado', "tier": 'legendary', "hp": 2550, "atk": 2200, "ability_name": 'Brazo Derecha de Gigante', "ability_description": 'Arm fires powerful reiatsu blasts.'},
    {"name": 'Uryu Ishida', "tier": 'legendary', "hp": 2400, "atk": 2300, "ability_name": 'Licht Regen', "ability_description": 'Rains Quincy arrows.'},
    {"name": 'Kaien Shiba', "tier": 'legendary', "hp": 2500, "atk": 2400, "ability_name": 'Nejibana', "ability_description": 'Water trident controls liquid.'},
    {"name": 'Oetsu Nimaiya', "tier": 'legendary', "hp": 2600, "atk": 2700, "ability_name": 'Sayafushi', "ability_description": 'Blade so sharp it cannot be sheathed.'},
    {"name": 'Senjumaru Shutara', "tier": 'legendary', "hp": 2550, "atk": 2500, "ability_name": 'Shutara Scale', "ability_description": 'Woven fabric creates illusions and traps.'},
    {"name": 'Tenjiro Kirinji', "tier": 'legendary', "hp": 2600, "atk": 2500, "ability_name": 'Kinpika', "ability_description": 'Light and hot-spring water attack/heal.'},
    {"name": 'Kirio Hikifune', "tier": 'legendary', "hp": 2500, "atk": 2400, "ability_name": 'Hikifune Tree', "ability_description": 'Grows reiatsu-infused food and plants.'},
    {"name": 'Shinji Hirako', "tier": 'legendary', "hp": 2600, "atk": 2500, "ability_name": 'Sakanade', "ability_description": 'Inverts enemy senses.'},
    {"name": 'Coyote Starrk', "tier": 'legendary', "hp": 2700, "atk": 2600, "ability_name": 'Los Lobos', "ability_description": 'Fires cero wolves and pistols.'},
    {"name": 'Barragan Louisenbairn', "tier": 'legendary', "hp": 2700, "atk": 2550, "ability_name": 'Respira', "ability_description": 'Ages and rots anything it touches.'},
    {"name": 'Grimmjow Jaegerjaquez', "tier": 'legendary', "hp": 2650, "atk": 2600, "ability_name": 'Pantera', "ability_description": 'Claw release with Desgarron.'},
    {"name": 'Nelliel Tu Odelschwanck', "tier": 'legendary', "hp": 2600, "atk": 2500, "ability_name": 'Gamuza', "ability_description": 'Cero Doble and healing saliva.'},
    {"name": 'Askin Nakk Le Vaar', "tier": 'legendary', "hp": 2650, "atk": 2600, "ability_name": 'Deathdealing', "ability_description": 'Controls lethal dose and immunity.'},
    {"name": 'Gremmy Thoumeaux', "tier": 'legendary', "hp": 2600, "atk": 2700, "ability_name": 'The Visionary', "ability_description": 'Turns imagination into reality.'},
    {"name": 'Gerard Valkyrie', "tier": 'legendary', "hp": 2800, "atk": 2700, "ability_name": 'The Miracle', "ability_description": 'Converts damage into size and power.'},
    {"name": 'Lille Barro', "tier": 'legendary', "hp": 2700, "atk": 2750, "ability_name": 'The X-Axis', "ability_description": 'Shots pierce anything between muzzle and target.'},
    {"name": 'Pernida Parnkgjas', "tier": 'legendary', "hp": 2600, "atk": 2600, "ability_name": 'The Compulsory', "ability_description": 'Nerves invade and evolve.'},
    {"name": 'Masaki Kurosaki', "tier": 'epic', "hp": 2000, "atk": 1900, "ability_name": 'Quincy Bow', "ability_description": 'Fires reishi arrows with Blut.'},
    {"name": 'Soi Fon', "tier": 'epic', "hp": 2300, "atk": 2400, "ability_name": 'Suzumebachi', "ability_description": 'Two-hit kill in same spot.'},
    {"name": 'Sajin Komamura', "tier": 'epic', "hp": 2600, "atk": 2300, "ability_name": "Kokujo Tengen Myo'o", "ability_description": 'Giant armored samurai mirrors moves.'},
    {"name": 'Rangiku Matsumoto', "tier": 'epic', "hp": 1188, "atk": 1155, "ability_name": 'Haineko', "ability_description": 'Ash cloud cuts like blades.'},
    {"name": 'Yachiru Kusajishi', "tier": 'epic', "hp": 2100, "atk": 2000, "ability_name": 'Sanpo Kenju', "ability_description": 'Three-blade combo attack.'},
    {"name": 'Ikkaku Madarame', "tier": 'epic', "hp": 2400, "atk": 2350, "ability_name": 'Ryumon Hozukimaru', "ability_description": 'Dragon cannon explosive thrust.'},
    {"name": 'Ginrei Kuchiki', "tier": 'epic', "hp": 2400, "atk": 2200, "ability_name": 'Senbonzakura', "ability_description": 'Petal blade swarm.'},
    {"name": 'Kensei Muguruma', "tier": 'epic', "hp": 2500, "atk": 2450, "ability_name": 'Tekken Tachikaze', "ability_description": 'Explosive wind punches.'},
    {"name": 'Harribel', "tier": 'epic', "hp": 2600, "atk": 2450, "ability_name": 'Tiburon', "ability_description": 'Water attacks and Cascada.'},
    {"name": 'Nnoitra Gilga', "tier": 'epic', "hp": 2600, "atk": 2550, "ability_name": 'Santa Teresa', "ability_description": 'Four scythe arms and high regen.'},
    {"name": 'Szayelaporro Granz', "tier": 'epic', "hp": 2400, "atk": 2350, "ability_name": 'Fornicaras', "ability_description": 'Clones and organ puppetry.'},
    {"name": 'Bambietta Basterbine', "tier": 'epic', "hp": 2500, "atk": 2450, "ability_name": 'The Explode', "ability_description": 'Turns anything into bombs.'},
    {"name": 'Bazz-B', "tier": 'epic', "hp": 2550, "atk": 2500, "ability_name": 'Burner Finger', "ability_description": 'Powerful flame fingers.'},
    {"name": 'Quilge Opie', "tier": 'epic', "hp": 2500, "atk": 2450, "ability_name": 'The Jail', "ability_description": 'Traps enemies in reishi prison.'},
    {"name": 'Royd Lloyd', "tier": 'epic', "hp": 2500, "atk": 2400, "ability_name": 'The Yourself', "ability_description": 'Copies appearance and powers.'},
    {"name": 'Kugo Ginjo', "tier": 'epic', "hp": 2500, "atk": 2450, "ability_name": 'Cross of Scaffold', "ability_description": 'Fullbring sword and reiatsu steal.'},
    {"name": 'Shukuro Tsukishima', "tier": 'epic', "hp": 2400, "atk": 2400, "ability_name": 'Book of the End', "ability_description": 'Inserts false past into targets.'},
    {"name": 'Tatsuki Arisawa', "tier": 'rare', "hp": 1800, "atk": 1600, "ability_name": 'Martial Arts', "ability_description": 'Strong human fighter.'},
    {"name": 'Tessai Tsukabishi', "tier": 'rare', "hp": 2300, "atk": 2000, "ability_name": 'Kido', "ability_description": 'High-level barrier and attack spells.'},
    {"name": 'Izuru Kira', "tier": 'rare', "hp": 2000, "atk": 1900, "ability_name": 'Wabisuke', "ability_description": 'Doubles weight with each hit.'},
    {"name": 'Momo Hinamori', "tier": 'rare', "hp": 1026, "atk": 990, "ability_name": 'Tobiume', "ability_description": 'Fireball explosions.'},
    {"name": 'Tetsuzaemon Iba', "tier": 'rare', "hp": 2000, "atk": 1900, "ability_name": 'Zanpakuto', "ability_description": 'Sword and physical combat.'},
    {"name": 'Nanao Ise', "tier": 'rare', "hp": 2000, "atk": 1850, "ability_name": 'Kido', "ability_description": 'Barriers and binding spells.'},
    {"name": 'Nemu Kurotsuchi', "tier": 'rare', "hp": 2100, "atk": 2000, "ability_name": 'Poison Body', "ability_description": 'Modified body with poison.'},
    {"name": 'Yumichika Ayasegawa', "tier": 'rare', "hp": 2200, "atk": 2100, "ability_name": "Ruri'iro Kujaku", "ability_description": 'Vines drain reiatsu.'},
    {"name": 'Kukaku Shiba', "tier": 'rare', "hp": 2300, "atk": 2200, "ability_name": 'Fireworks', "ability_description": 'Kido cannon and fireworks.'},
    {"name": 'Hiyori Sarugaki', "tier": 'rare', "hp": 2200, "atk": 2300, "ability_name": 'Kubikiri Orochi', "ability_description": 'Heavy slash and Vizard mask.'},
    {"name": 'Love Aikawa', "tier": 'rare', "hp": 2400, "atk": 2300, "ability_name": 'Tengumaru', "ability_description": 'Fire club smashes.'},
    {"name": 'Rose Otoribashi', "tier": 'rare', "hp": 2300, "atk": 2200, "ability_name": 'Kinshara', "ability_description": 'Sound illusions.'},
    {"name": 'Mashiro Kuna', "tier": 'rare', "hp": 2200, "atk": 2200, "ability_name": 'Vizard Mask', "ability_description": 'Hollow mask boosts speed.'},
    {"name": 'Lisa Yadomaru', "tier": 'rare', "hp": 2100, "atk": 2100, "ability_name": 'Hollow Mask', "ability_description": 'Mask boosts power.'},
    {"name": 'Hachigen Ushoda', "tier": 'rare', "hp": 2300, "atk": 2000, "ability_name": 'Kido Barriers', "ability_description": 'High-level barriers and seals.'},
    {"name": 'Zommari Rureaux', "tier": 'rare', "hp": 2300, "atk": 2200, "ability_name": 'Amor', "ability_description": 'Controls targets with eyes.'},
    {"name": 'Aaroniero Arruruerie', "tier": 'rare', "hp": 2300, "atk": 2200, "ability_name": 'Glotoneria', "ability_description": 'Absorbs powers by eating.'},
    {"name": 'Yammy Llargo', "tier": 'rare', "hp": 2500, "atk": 2400, "ability_name": 'Ira', "ability_description": 'Rage increases size and power.'},
    {"name": 'Wonderweiss Margela', "tier": 'rare', "hp": 2200, "atk": 2300, "ability_name": 'Extinguir', "ability_description": 'Nullifies fire abilities.'},
    {"name": 'Candice Catnipp', "tier": 'rare', "hp": 2400, "atk": 2400, "ability_name": 'Galvano Blast', "ability_description": 'Lightning arrows.'},
    {"name": 'Cang Du', "tier": 'rare', "hp": 2300, "atk": 2250, "ability_name": 'The Iron', "ability_description": 'Skin turns to iron.'},
    {"name": 'Driscoll Berci', "tier": 'rare', "hp": 2200, "atk": 2150, "ability_name": 'The Overkill', "ability_description": 'Absorbs killed souls for power.'},
    {"name": 'Giselle Gewelle', "tier": 'rare', "hp": 2300, "atk": 2200, "ability_name": 'The Zombie', "ability_description": 'Controls zombies with blood.'},
    {"name": 'Liltotto Lamperd', "tier": 'rare', "hp": 2300, "atk": 2250, "ability_name": 'The Glutton', "ability_description": 'Eats enemies and attacks.'},
    {"name": 'Meninas McAllon', "tier": 'rare', "hp": 2300, "atk": 2250, "ability_name": 'The Power', "ability_description": 'Super strength.'},
    {"name": 'Nanana Najahkoop', "tier": 'rare', "hp": 2200, "atk": 2100, "ability_name": 'The Underbelly', "ability_description": 'Analyzes and attacks weak points.'},
    {"name": 'Robert Accutrone', "tier": 'rare', "hp": 2300, "atk": 2250, "ability_name": 'Quincy Guns', "ability_description": 'Fires reishi bullets.'},
    {"name": 'BG9', "tier": 'rare', "hp": 2300, "atk": 2250, "ability_name": 'Daten', "ability_description": 'Data analysis and weapons.'},
    {"name": 'Loyd Lloyd', "tier": 'rare', "hp": 2200, "atk": 2200, "ability_name": 'The Yourself', "ability_description": 'Copies appearance and power.'},
    {"name": 'Riruka Dokugamine', "tier": 'rare', "hp": 2100, "atk": 2000, "ability_name": 'Dollhouse', "ability_description": 'Shrinks and traps in boxes.'},
    {"name": 'Yukio Hans Vorarlberna', "tier": 'rare', "hp": 2100, "atk": 2050, "ability_name": 'Invaders Must Die', "ability_description": 'Game constructs attack.'},
    {"name": 'Jackie Tristan', "tier": 'rare', "hp": 2100, "atk": 2100, "ability_name": 'Dirty Boots', "ability_description": 'Boots gain power from dirt.'},
    {"name": 'Kazui Kurosaki', "tier": 'uncommon', "hp": 1700, "atk": 1500, "ability_name": 'Potential', "ability_description": 'Inherited high reiatsu.'},
    {"name": 'Chojiro Sasakibe', "tier": 'uncommon', "hp": 1134, "atk": 1045, "ability_name": 'Gonryomaru', "ability_description": 'Lightning spear.'},
    {"name": 'Isane Kotetsu', "tier": 'uncommon', "hp": 1026, "atk": 935, "ability_name": 'Healing Kido', "ability_description": 'Heals wounds.'},
    {"name": 'Luppi Antenor', "tier": 'uncommon', "hp": 2100, "atk": 2150, "ability_name": 'Trepadora', "ability_description": 'Tentacle release.'},
    {"name": 'Tesra Lindocruz', "tier": 'uncommon', "hp": 1026, "atk": 990, "ability_name": 'Strength', "ability_description": 'Physical combat.'},
    {"name": 'Moe Shishigawara', "tier": 'uncommon', "hp": 1026, "atk": 1045, "ability_name": 'Jackpot Knuckle', "ability_description": 'Lucky punch power.'},
    {"name": 'Yuzu Kurosaki', "tier": 'common', "hp": 1200, "atk": 600, "ability_name": 'Human', "ability_description": 'Ordinary human.'},
    {"name": 'Karin Kurosaki', "tier": 'common', "hp": 1300, "atk": 800, "ability_name": 'Human', "ability_description": 'Can see spirits.'},
    {"name": 'Kon', "tier": 'common', "hp": 1000, "atk": 500, "ability_name": 'Modified Soul', "ability_description": 'Can possess and fight.'},
    {"name": 'Keigo Asano', "tier": 'common', "hp": 900, "atk": 400, "ability_name": 'Human', "ability_description": 'Ordinary human.'},
    {"name": 'Mizuiro Kojima', "tier": 'common', "hp": 850, "atk": 450, "ability_name": 'Human', "ability_description": 'Ordinary human.'},
    {"name": 'Chizuru Honsho', "tier": 'common', "hp": 800, "atk": 500, "ability_name": 'Human', "ability_description": 'Ordinary human.'},
    {"name": 'Don Kanonji', "tier": 'common', "hp": 1100, "atk": 700, "ability_name": 'Spiritual Power', "ability_description": 'Fires weak spirit ball.'},
    {"name": 'Jinta Hanakari', "tier": 'common', "hp": 1400, "atk": 1200, "ability_name": 'Strength', "ability_description": 'Strong human.'},
    {"name": 'Ururu Tsumugiya', "tier": 'common', "hp": 1300, "atk": 1100, "ability_name": 'Strength', "ability_description": 'Modified strength.'},
    {"name": 'Marechiyo Omaeda', "tier": 'common', "hp": 1800, "atk": 1400, "ability_name": 'Gegetsuburi', "ability_description": 'Flail smash.'},
    {"name": 'Hanataro Yamada', "tier": 'common', "hp": 1500, "atk": 1100, "ability_name": 'Hisagomaru', "ability_description": 'Heals by releasing stored damage.'},
    {"name": 'Kiyone Kotetsu', "tier": 'common', "hp": 1600, "atk": 1300, "ability_name": 'Kido', "ability_description": 'Basic kido.'},
    {"name": 'Sentaro Kotsubaki', "tier": 'common', "hp": 1700, "atk": 1400, "ability_name": 'Kido', "ability_description": 'Basic kido.'},
    {"name": 'Makizo Aramaki', "tier": 'common', "hp": 1600, "atk": 1300, "ability_name": 'Strength', "ability_description": 'Physical combat.'},
    {"name": 'Ganju Shiba', "tier": 'common', "hp": 1900, "atk": 1700, "ability_name": 'Fireworks', "ability_description": 'Kido fireworks.'},
    {"name": 'Lilynette Gingerbuck', "tier": 'common', "hp": 1600, "atk": 1500, "ability_name": 'Cero', "ability_description": 'Fires cero.'},
    {"name": 'Pesche Guatiche', "tier": 'common', "hp": 1700, "atk": 1500, "ability_name": 'Infinite Slick', "ability_description": 'Slippery spit.'},
    {"name": 'Dondochakka Birstanne', "tier": 'common', "hp": 1800, "atk": 1600, "ability_name": 'Spit', "ability_description": 'Sticky spit.'},
    {"name": 'PePe Waccabrada', "tier": 'common', "hp": 2000, "atk": 1900, "ability_name": 'The Love', "ability_description": 'Controls targets with love.'},
    {"name": 'Shaz Domino', "tier": 'common', "hp": 1900, "atk": 1800, "ability_name": 'Quincy', "ability_description": 'Reishi attacks.'},
    {"name": 'Giriko Kutsuzawa', "tier": 'common', "hp": 1800, "atk": 1700, "ability_name": 'Time Tells No Lies', "ability_description": 'Fullbring time-based.'},
    {"name": 'Adnyeus', "tier": 'mythic', "hp": 1620, "atk": 1623, "ability_name": '', "ability_description": ''},
    {"name": 'Hikone Ubuginu', "tier": 'mythic', "hp": 2900, "atk": 2800, "ability_name": 'Ikomikidomoe', "ability_description": 'Hybrid Shinigami/Arrancar power boosts all stats.'},
    {"name": 'Tokinada Tsunayashiro', "tier": 'legendary', "hp": 2750, "atk": 2700, "ability_name": 'Enrakyoten', "ability_description": 'Copies other zanpakuto abilities.'},
    {"name": 'Kageroza Inaba', "tier": 'legendary', "hp": 2700, "atk": 2650, "ability_name": 'Reigai', "ability_description": 'Creates clones with copied powers.'},
    {"name": 'Mask De Masculine', "tier": 'legendary', "hp": 2650, "atk": 2600, "ability_name": 'The Superstar', "ability_description": 'Cheers increase power and healing.'},
    {"name": 'Muramasa', "tier": 'legendary', "hp": 2600, "atk": 2650, "ability_name": 'Mind Control', "ability_description": 'Turns zanpakuto spirits against owners.'},
    {"name": 'Kaname Tosen', "tier": 'legendary', "hp": 2600, "atk": 2550, "ability_name": 'Suzumushi', "ability_description": 'Sound-based illusions and black dome.'},
    {"name": 'Ryuken Ishida', "tier": 'legendary', "hp": 2600, "atk": 2500, "ability_name": 'Quincy Archery', "ability_description": 'Master arrow shots and Blut.'},
    {"name": 'Äs Nödt', "tier": 'legendary', "hp": 2550, "atk": 2500, "ability_name": 'The Fear', "ability_description": 'Thorns induce absolute fear.'},
    {"name": 'Ohana Katen', "tier": 'legendary', "hp": 2550, "atk": 2450, "ability_name": 'Katen Kyokotsu', "ability_description": 'Reality game abilities.'},
    {"name": 'Okyo Kyokotsu', "tier": 'legendary', "hp": 2500, "atk": 2550, "ability_name": 'Kyokotsu', "ability_description": 'Game-based support and attacks.'},
    {"name": 'Sogyo no Kotowari', "tier": 'legendary', "hp": 2500, "atk": 2400, "ability_name": 'Redirect', "ability_description": 'Absorbs and returns attacks.'},
    {"name": 'Hozukimaru', "tier": 'legendary', "hp": 2400, "atk": 2300, "ability_name": 'Spear Thrust', "ability_description": 'Extends and explodes on impact.'},
    {"name": 'Suzumebachi', "tier": 'legendary', "hp": 1334, "atk": 1170, "ability_name": 'Nigeki Kessatsu', "ability_description": 'Second hit in same spot kills.'},
    {"name": 'Hisagomaru', "tier": 'legendary', "hp": 1318, "atk": 1139, "ability_name": 'Healing Gauge', "ability_description": 'Stores damage then releases as healing.'},
    {"name": 'Narunosuke', "tier": 'legendary', "hp": 1301, "atk": 1107, "ability_name": 'Spirit Support', "ability_description": 'Filler zanpakuto spirit supports with kido.'},
    {"name": 'Shintaro', "tier": 'legendary', "hp": 1285, "atk": 1076, "ability_name": 'Spirit Blade', "ability_description": 'Filler zanpakuto spirit slashes with reiatsu.'},
    {"name": 'Sakanade', "tier": 'legendary', "hp": 1269, "atk": 1045, "ability_name": 'Sense Invert', "ability_description": 'Inverts enemy senses.'},
    {"name": 'Tenken', "tier": 'epic', "hp": 1404, "atk": 1403, "ability_name": 'Giant Limb', "ability_description": 'Summons giant arm/leg.'},
    {"name": 'Zabimaru', "tier": 'epic', "hp": 1388, "atk": 1386, "ability_name": 'Snake Blade', "ability_description": 'Extends and bites.'},
    {"name": 'Ashisogi Jizo', "tier": 'epic', "hp": 1373, "atk": 1369, "ability_name": 'Poison Sting', "ability_description": 'Paralyzes and poisons.'},
    {"name": 'Kazeshini', "tier": 'epic', "hp": 3017, "atk": 2703, "ability_name": '', "ability_description": ''},
    {"name": 'Kokuto', "tier": 'epic', "hp": 2500, "atk": 2500, "ability_name": 'Dark Zanpakuto', "ability_description": 'Dark energy slashes.'},
    {"name": 'Shusuke Amagai', "tier": 'epic', "hp": 2500, "atk": 2450, "ability_name": 'Raika', "ability_description": 'Fire and lightning blade.'},
    {"name": 'Jin Kariya', "tier": 'epic', "hp": 2500, "atk": 2400, "ability_name": 'Doll Wind', "ability_description": 'Wind doll attacks and defense.'},
    {"name": 'Sojiro Kusaka', "tier": 'epic', "hp": 2450, "atk": 2400, "ability_name": 'Ice Zanpakuto', "ability_description": 'Ice attacks and freezing.'},
    {"name": 'Oko Yushima', "tier": 'epic', "hp": 2450, "atk": 2350, "ability_name": 'Reigai Fusion', "ability_description": 'Absorbs powers and kido.'},
    {"name": 'Gantenbainne Mosqueda', "tier": 'epic', "hp": 2450, "atk": 2300, "ability_name": 'Dragra', "ability_description": 'Armored arm blasts.'},
    {"name": "Ruri'iro Kujaku", "tier": 'epic', "hp": 2777, "atk": 2464, "ability_name": '', "ability_description": ''},
    {"name": 'Haineko', "tier": 'epic', "hp": 1234, "atk": 1215, "ability_name": 'Ash Cloud', "ability_description": 'Ash cuts like blades.'},
    {"name": 'Aura Michibane', "tier": 'epic', "hp": 2400, "atk": 2350, "ability_name": 'Fullbring Matter', "ability_description": 'Controls matter and reishi.'},
    {"name": 'Dordoni Alessandro Del Socaccio', "tier": 'epic', "hp": 2400, "atk": 2350, "ability_name": 'Giralda', "ability_description": 'Wind-based kicks and tornado.'},
    {"name": 'Senna', "tier": 'epic', "hp": 2400, "atk": 2350, "ability_name": 'Shinken', "ability_description": 'Memory blade cuts memories.'},
    {"name": 'Ouko Yushima', "tier": 'epic', "hp": 2400, "atk": 2300, "ability_name": 'Reigai Tech', "ability_description": 'Copies and enhances powers.'},
    {"name": 'Cirucci Sanderwicci', "tier": 'epic', "hp": 2350, "atk": 2400, "ability_name": 'Golondrina', "ability_description": 'Blade wings and feather attacks.'},
    {"name": 'Shuhei Hisagi', "tier": 'epic', "hp": 2350, "atk": 2250, "ability_name": 'Kazeshini', "ability_description": 'Twin scythes on chains.'},
    {"name": 'Rudbornn Chelute', "tier": 'epic', "hp": 2300, "atk": 2250, "ability_name": 'Calaveras', "ability_description": 'Summons Exequias minions.'},
    {"name": 'Gonryomaru', "tier": 'epic', "hp": 1111, "atk": 1079, "ability_name": 'Lightning Spear', "ability_description": 'Lightning spear strikes.'},
    {"name": 'Wabisuke', "tier": 'epic', "hp": 1095, "atk": 1062, "ability_name": 'Weight Double', "ability_description": "Doubles target's weight."},
    {"name": 'Nozomi Kujo', "tier": 'epic', "hp": 1080, "atk": 1045, "ability_name": 'Modified Soul', "ability_description": 'Kido and reiatsu bursts.'},
    {"name": 'Tobiume', "tier": 'rare', "hp": 1350, "atk": 1320, "ability_name": 'Fireball', "ability_description": 'Throws explosive fireballs.'},
    {"name": 'Gegetsuburi', "tier": 'rare', "hp": 1331, "atk": 1298, "ability_name": 'Flail', "ability_description": 'Heavy flail smashes.'},
    {"name": 'Shuren', "tier": 'rare', "hp": 2300, "atk": 2250, "ability_name": 'Fire Doll', "ability_description": 'Fire-based Bount doll.'},
    {"name": 'Choe Neng Poww', "tier": 'rare', "hp": 2300, "atk": 2200, "ability_name": 'Hippo', "ability_description": 'Massive strength and cero.'},
    {"name": 'Kuruyashiki Kenpachi', "tier": 'rare', "hp": 2300, "atk": 2200, "ability_name": 'Sword', "ability_description": 'Kenpachi swordsmanship.'},
    {"name": 'Edrad Liones', "tier": 'rare', "hp": 2250, "atk": 2150, "ability_name": 'Volcano', "ability_description": 'Fire punches and explosions.'},
    {"name": 'Makoto Kibune', "tier": 'rare', "hp": 2250, "atk": 2150, "ability_name": 'Kido', "ability_description": 'Binding and attack spells.'},
    {"name": 'Ggio Vega', "tier": 'rare', "hp": 2200, "atk": 2150, "ability_name": 'Tigre', "ability_description": 'Claw and speed release.'},
    {"name": 'Kenpachi Kiganjo', "tier": 'rare', "hp": 2200, "atk": 2150, "ability_name": 'Sword', "ability_description": 'Kenpachi swordsmanship.'},
    {"name": 'Charlotte Chuhlhourne', "tier": 'rare', "hp": 2200, "atk": 2100, "ability_name": 'Reina de Rosas', "ability_description": 'Rose attacks and beauty.'},
    {"name": 'Ganryu', "tier": 'rare', "hp": 2200, "atk": 2100, "ability_name": 'Bount Doll', "ability_description": 'Doll with energy attacks.'},
    {"name": 'Go Koga', "tier": 'rare', "hp": 2200, "atk": 2100, "ability_name": 'Dark Zanpakuto', "ability_description": 'Dark energy attacks.'},
    {"name": 'Shawlong Koufang', "tier": 'rare', "hp": 2200, "atk": 2100, "ability_name": 'Tijereta', "ability_description": 'Claw release and ice.'},
    {"name": 'Yylfordt Granz', "tier": 'rare', "hp": 2200, "atk": 2100, "ability_name": 'Del Toro', "ability_description": 'Horns and charging.'},
    {"name": 'Cyan Sun-Sun', "tier": 'rare', "hp": 2150, "atk": 2100, "ability_name": 'Anaconda', "ability_description": 'Snake tail and poison.'},
    {"name": 'Emilou Apacci', "tier": 'rare', "hp": 2150, "atk": 2100, "ability_name": 'Cierva', "ability_description": 'Antler and cero.'},
    {"name": 'Franceska Mila Rose', "tier": 'rare', "hp": 2150, "atk": 2100, "ability_name": 'Leona', "ability_description": 'Lion strength and roar.'},
    {"name": 'Nirgge Parduoc', "tier": 'rare', "hp": 2150, "atk": 2100, "ability_name": 'Mammoth', "ability_description": 'Heavy strength and charge.'},
    {"name": 'Findorr Calius', "tier": 'rare', "hp": 2150, "atk": 2050, "ability_name": 'Pinza', "ability_description": 'Crab claw and water.'},
    {"name": 'Abirama Redder', "tier": 'rare', "hp": 2100, "atk": 2150, "ability_name": 'Aguila', "ability_description": 'Winged claw attacks.'},
    {"name": 'Maki Ichinose', "tier": 'rare', "hp": 2100, "atk": 2050, "ability_name": 'Light Zanpakuto', "ability_description": 'Light-based slashes.'},
    {"name": 'Roka Paramia', "tier": 'rare', "hp": 2100, "atk": 2050, "ability_name": 'Arrancar', "ability_description": 'Healing and research.'},
    {"name": 'Grand Fisher', "tier": 'rare', "hp": 2000, "atk": 2100, "ability_name": 'Lure', "ability_description": 'Uses lure to eat souls.'},
    {"name": 'Kirikaze', "tier": 'rare', "hp": 2000, "atk": 1950, "ability_name": 'Wind', "ability_description": 'Wind blade.'},
    {"name": 'Lurichiyo Kasumiōji', "tier": 'rare', "hp": 2000, "atk": 1900, "ability_name": 'Noble Blade', "ability_description": 'Royal zanpakuto.'},
    {"name": 'Hanza Nukui', "tier": 'rare', "hp": 1950, "atk": 1900, "ability_name": 'Assassin', "ability_description": 'Stealth and blade.'},
    {"name": 'Taikun', "tier": 'rare', "hp": 1950, "atk": 1900, "ability_name": 'Lightning', "ability_description": 'Lightning attacks.'},
    {"name": 'Garogai', "tier": 'rare', "hp": 1900, "atk": 1850, "ability_name": 'Earth', "ability_description": 'Earth attacks.'},
    {"name": 'Gyakuaku Kumoi', "tier": 'rare', "hp": 1900, "atk": 1850, "ability_name": 'Kido', "ability_description": 'Political and kido attacks.'},
    {"name": 'Homura', "tier": 'rare', "hp": 1900, "atk": 1800, "ability_name": 'Fire', "ability_description": 'Fire attacks.'},
    {"name": 'Shizuku', "tier": 'rare', "hp": 1900, "atk": 1800, "ability_name": 'Water', "ability_description": 'Water attacks.'},
    {"name": 'Gunjo', "tier": 'uncommon', "hp": 2309, "atk": 2050, "ability_name": '', "ability_description": ''},
    {"name": 'Jinnai Douko', "tier": 'rare', "hp": 1850, "atk": 1800, "ability_name": 'Kido', "ability_description": 'Binding spells.'},
    {"name": 'Genga', "tier": 'rare', "hp": 1800, "atk": 1750, "ability_name": 'Bount', "ability_description": 'Bount physical combat.'},
    {"name": 'Yang', "tier": 'rare', "hp": 1800, "atk": 1750, "ability_name": 'Twin', "ability_description": 'Twin combat.'},
    {"name": 'Yin', "tier": 'rare', "hp": 1800, "atk": 1750, "ability_name": 'Twin', "ability_description": 'Twin combat.'},
    {"name": 'Enryu', "tier": 'rare', "hp": 1800, "atk": 1700, "ability_name": 'Doll', "ability_description": 'Modified soul doll.'},
    {"name": 'Jai', "tier": 'rare', "hp": 1800, "atk": 1700, "ability_name": 'Bount', "ability_description": 'Bount combat.'},
    {"name": 'Kenryu', "tier": 'rare', "hp": 1800, "atk": 1700, "ability_name": 'Doll', "ability_description": 'Modified soul doll.'},
    {"name": 'Ryu Kuzu', "tier": 'rare', "hp": 1750, "atk": 1700, "ability_name": 'Bount', "ability_description": 'Bount combat.'},
    {"name": 'Benin', "tier": 'rare', "hp": 1750, "atk": 1650, "ability_name": 'Bount', "ability_description": 'Bount combat.'},
    {"name": 'Bau', "tier": 'rare', "hp": 1700, "atk": 1600, "ability_name": 'Bount', "ability_description": 'Bount combat.'},
    {"name": 'Ririn', "tier": 'rare', "hp": 1700, "atk": 1600, "ability_name": 'Doll', "ability_description": 'Modified soul doll.'},
    {"name": 'Kurudo', "tier": 'rare', "hp": 1700, "atk": 1550, "ability_name": 'Doll', "ability_description": 'Modified soul doll.'},
    {"name": 'Mue', "tier": 'rare', "hp": 1650, "atk": 1550, "ability_name": 'Bount', "ability_description": 'Bount combat.'},
    {"name": 'Noba', "tier": 'rare', "hp": 1600, "atk": 1500, "ability_name": 'Doll', "ability_description": 'Modified soul doll.'},
    {"name": 'Riyan', "tier": 'rare', "hp": 1600, "atk": 1500, "ability_name": 'Bount', "ability_description": 'Bount combat.'},
    {"name": 'Ho', "tier": 'common', "hp": 2280, "atk": 1953, "ability_name": '', "ability_description": ''},
    {"name": 'Yoshino Soma', "tier": 'uncommon', "hp": 1900, "atk": 1800, "ability_name": 'Goethe', "ability_description": 'Fire doll.'},
    {"name": 'Ban', "tier": 'uncommon', "hp": 1850, "atk": 1750, "ability_name": 'Doll', "ability_description": 'Bount doll.'},
    {"name": 'Mabashi', "tier": 'uncommon', "hp": 1850, "atk": 1750, "ability_name": 'Doll', "ability_description": 'Bount doll.'},
    {"name": 'Gesell', "tier": 'uncommon', "hp": 1800, "atk": 1700, "ability_name": 'Doll', "ability_description": 'Bount doll.'},
    {"name": 'Sawatari', "tier": 'uncommon', "hp": 1800, "atk": 1700, "ability_name": 'Doll', "ability_description": 'Bount doll.'},
    {"name": 'Ugaki', "tier": 'uncommon', "hp": 1800, "atk": 1700, "ability_name": 'Gesell', "ability_description": 'Doll attacks.'},
    {"name": 'Ikumi Unagiya', "tier": 'uncommon', "hp": 1800, "atk": 1600, "ability_name": 'Human', "ability_description": 'Strong will.'},
    {"name": 'Yoshi', "tier": 'uncommon', "hp": 1750, "atk": 1650, "ability_name": 'Flying Doll', "ability_description": 'Flying doll.'},
    {"name": 'Kaoru Unagiya', "tier": 'uncommon', "hp": 1500, "atk": 1200, "ability_name": 'Human', "ability_description": 'Ordinary human.'},
    {"name": 'Nianzol Weizol', "tier": 'common', "hp": 1900, "atk": 1850, "ability_name": 'The Wind', "ability_description": 'Redirects attacks with wind.'},
    {"name": 'Sojun Kuchiki', "tier": 'common', "hp": 1500, "atk": 1400, "ability_name": 'Kuchiki Blade', "ability_description": 'Noble swordsmanship.'},
    {"name": 'Soul King', "tier": 'mythic', "hp": 3100, "atk": 3200, "ability_name": 'Soul King Reiatsu', "ability_description": 'Stabilizes realms and grants precognitive power.'},
]

WEAPONS = [
    {"name": 'Tensa Zangetsu', "tier": 'mythic', 'boost_type': 'damage', 'boost_percent': 50, 'ability_name': 'Tensho', 'ability_description': 'Supercharged Getsuga that cuts through dimensions', 'image_key': 'Tensa Zangetsu'},
    {"name": 'Zanka no Tachi', "tier": 'mythic', 'boost_type': 'damage', 'boost_percent': 49, 'ability_name': 'East: Rising Sun Edge', 'ability_description': 'Everything touched ceases to exist', 'image_key': 'Zanka no Tachi'},
    {"name": 'Kyoka Suigetsu', "tier": 'mythic', 'boost_type': 'damage', 'boost_percent': 48, 'ability_name': 'Kanzen Saimin', 'ability_description': 'Complete control over all five senses', 'image_key': 'Kyoka Suigetsu'},
    {"name": 'Senbonzakura Kageyoshi', "tier": 'mythic', 'boost_type': 'damage', 'boost_percent': 45, 'ability_name': 'Gokei', 'ability_description': 'Thousand blades become a death dome crushing everything inside', 'image_key': 'Senbonzakura Kageyoshi'},
    {"name": 'Katen Kyokotsu Karamatsu Shinju', "tier": 'mythic', 'boost_type': 'hp', 'boost_percent': 40, 'ability_name': 'Acts out a tragic play where all participants share wounds', 'ability_description': '', 'image_key': 'Katen Kyokotsu Karamatsu Shinju'},
    {"name": 'Daiguren Hyorinmaru', "tier": 'mythic', 'boost_type': 'damage', 'boost_percent': 44, 'ability_name': 'Hyoten Hyakkaso', 'ability_description': 'Freezes everything in a 10-mile radius', 'image_key': 'Daiguren Hyorinmaru'},
    {"name": 'Nozarashi', "tier": 'mythic', 'boost_type': 'damage', 'boost_percent': 43, 'ability_name': 'Slash that cuts through space itself', 'ability_description': '', 'image_key': 'Nozarashi (Bankai)'},
    {"name": 'Kamishini no Yari', "tier": 'mythic', 'boost_type': 'damage', 'boost_percent': 42, 'ability_name': 'Extends at light speed with a deadly cell-destroying poison', 'ability_description': '', 'image_key': 'Kamishini no Yari'},
    {"name": 'Minazuki', "tier": 'mythic', 'boost_type': 'hp', 'boost_percent': 39, 'ability_name': 'Blood-Red Healing Acid', 'ability_description': 'Melts and heals enemies simultaneously', 'image_key': 'minazuki bankai'},
    {"name": 'Minazuki', "tier": 'mythic', 'boost_type': 'hp', 'boost_percent': 38, 'ability_name': '', 'ability_description': '', 'image_key': 'Minazuki (Shikai)'},
    {"name": 'Hakka no Togame', "tier": 'legendary', 'boost_type': 'damage', 'boost_percent': 35, 'ability_name': 'Absolute Zero', 'ability_description': 'Flash freezes everything to absolute zero', 'image_key': 'Hakka no Togame'},
    {"name": 'Kannonbiraki Benihime Aratame', "tier": 'legendary', 'boost_type': 'damage', 'boost_percent': 34, 'ability_name': 'Restructures anything it touches', 'ability_description': 'healing or destroying', 'image_key': 'Kannonbiraki Benihime Aratame'},
    {"name": 'Soo Zabimaru', "tier": 'legendary', 'boost_type': 'damage', 'boost_percent': 31, 'ability_name': 'Orochio Higa', 'ability_description': 'Fires colossal snake-shaped energy', 'image_key': 'Soo Zabimaru'},
    {"name": 'Konjiki Ashisogi Jizo', "tier": 'legendary', 'boost_type': 'damage', 'boost_percent': 32, 'ability_name': 'Poison Gas that stops all bodily functions', 'ability_description': '', 'image_key': 'Konjiki Ashisogi Jizo'},
    {"name": 'Sakashima Yokoshima Happo Fusagari', "tier": 'legendary', 'boost_type': 'hp', 'boost_percent': 33, 'ability_name': 'Reverses everything', 'ability_description': 'friend/foe, directions, perceptions', 'image_key': 'Sakashima Yokoshima Happo Fusagari'},
    {"name": 'Kinshara Butodan', "tier": 'legendary', 'boost_type': 'hp', 'boost_percent': 31, 'ability_name': 'Musical dance that burns and entrances enemies', 'ability_description': '', 'image_key': 'Kinshara Butodan'},
    {"name": 'Tekken Tachikaze', "tier": 'legendary', 'boost_type': 'damage', 'boost_percent': 28, 'ability_name': 'Explosive brute force punches that detonate on impact', 'ability_description': '', 'image_key': 'Tekken Tachikaze'},
    {"name": 'Ryumon Hozukimaru', "tier": 'epic', 'boost_type': 'damage', 'boost_percent': 21, 'ability_name': 'Dragon Gate', 'ability_description': "Massive energy from the staff's tip", 'image_key': 'Ryumon Hozukimaru'},
    {"name": 'Jakuho Raikoben', "tier": 'epic', 'boost_type': 'damage', 'boost_percent': 23, 'ability_name': 'Missile of Lightning', 'ability_description': 'Devastating homing missile', 'image_key': 'Jakuho Raikoben'},
    {"name": "Kokujo Tengen Myo'o", "tier": 'epic', 'boost_type': 'hp', 'boost_percent': 24, 'ability_name': 'Giant Warrior', 'ability_description': 'Massive armored giant that fights for him', 'image_key': "Kokujo Tengen Myo'o"},
    {"name": 'Zangetsu', "tier": 'legendary', 'boost_type': 'damage', 'boost_percent': 30, 'ability_name': 'Getsuga Tensho', 'ability_description': 'Crescent moon energy slash', 'image_key': 'Zangetsu'},
    {"name": 'Ichimonji', "tier": 'legendary', 'boost_type': 'damage', 'boost_percent': 30, 'ability_name': '', 'ability_description': '', 'image_key': 'Ichimonji'},
    {"name": 'Ryujin Jakka', "tier": 'legendary', 'boost_type': 'damage', 'boost_percent': 33, 'ability_name': 'Ennetsu Jigoku', 'ability_description': 'Flame Prison of Hell', 'image_key': 'Ryujin Jakka'},
    {"name": 'Sode no Shirayuki', "tier": 'legendary', 'boost_type': 'hp', 'boost_percent': 28, 'ability_name': 'Tsukishiro', 'ability_description': 'Creates an ice prison around the enemy', 'image_key': 'Sode no Shirayuki'},
    {"name": 'Senbonzakura', "tier": 'legendary', 'boost_type': 'damage', 'boost_percent': 25, 'ability_name': 'Scatters into thousands of controllable cherry blossom blades', 'ability_description': '', 'image_key': 'Senbonzakura'},
    {"name": 'Katen Kyokotsu', "tier": 'legendary', 'boost_type': 'hp', 'boost_percent': 28, 'ability_name': 'Daruma-san ga Koronda', 'ability_description': 'The child game becomes a death trap', 'image_key': 'Katen Kyokotsu'},
    {"name": 'Hyorinmaru', "tier": 'legendary', 'boost_type': 'damage', 'boost_percent': 29, 'ability_name': 'Ryusenka', 'ability_description': 'Ice pillar that freezes everything in its radius', 'image_key': 'Hyorinmaru'},
    {"name": 'Nozarashi', "tier": 'legendary', 'boost_type': 'damage', 'boost_percent': 29, 'ability_name': 'Cleaves through any defense without hesitation', 'ability_description': '', 'image_key': 'Nozarashi Shikai'},
    {"name": 'Shinso', "tier": 'legendary', 'boost_type': 'damage', 'boost_percent': 25, 'ability_name': 'Extends suddenly without warning', 'ability_description': '', 'image_key': 'Shinso'},
    {"name": 'Benihime', "tier": 'legendary', 'boost_type': 'damage', 'boost_percent': 29, 'ability_name': 'Chikasumi no Tate', 'ability_description': 'Blood mist shield that absorbs attacks', 'image_key': 'Benihime'},
    {"name": 'Zabimaru', "tier": 'epic', 'boost_type': 'hp', 'boost_percent': 19, 'ability_name': 'Renji', 'ability_description': 'Extends like a giant snake of blade segments', 'image_key': 'Zabimaru'},
    {"name": 'Hozukimaru', "tier": 'epic', 'boost_type': 'hp', 'boost_percent': 18, 'ability_name': 'Three-section staff mode with explosive reach', 'ability_description': '', 'image_key': 'Hozukimaru'},
    {"name": 'Suzumebachi', "tier": 'epic', 'boost_type': 'damage', 'boost_percent': 23, 'ability_name': 'Death Sting', 'ability_description': 'Two stings = guaranteed death', 'image_key': 'Suzumebachi'},
    {"name": 'Tobiume', "tier": 'epic', 'boost_type': 'hp', 'boost_percent': 17, 'ability_name': 'Tobiume', 'ability_description': 'Creates exploding fireballs', 'image_key': 'Tobiume'},
    {"name": 'Haineko', "tier": 'epic', 'boost_type': 'hp', 'boost_percent': 21, 'ability_name': 'Ash Cut', 'ability_description': 'Turns into dust that cuts anything', 'image_key': 'Haineko (Shikai)'},
    {"name": 'Sakanade', "tier": 'epic', 'boost_type': 'hp', 'boost_percent': 24, 'ability_name': 'Inversion', 'ability_description': 'Reverses all directions and perceptions', 'image_key': 'Sakanade'},
    {"name": 'Kazeshini', "tier": 'epic', 'boost_type': 'hp', 'boost_percent': 19, 'ability_name': 'Wind Scythe', 'ability_description': 'Dual blades that slice with wind force', 'image_key': 'Kazeshini'},
    {"name": 'Tenken', "tier": 'epic', 'boost_type': 'hp', 'boost_percent': 18, 'ability_name': 'Giant Sword', 'ability_description': "Summons a giant's arm to strike", 'image_key': 'Tenken'},
    {"name": 'Tachikaze', "tier": 'epic', 'boost_type': 'hp', 'boost_percent': 22, 'ability_name': 'Wind Explosion', 'ability_description': 'Creates wind that detonates after cutting', 'image_key': 'Tachikaze'},
    {"name": 'Kinshara', "tier": 'epic', 'boost_type': 'hp', 'boost_percent': 17, 'ability_name': 'Sound Whip', 'ability_description': 'Whip that creates haunting melodies', 'image_key': 'Kinshara'},
    {"name": 'Sogyo no Kotowari', "tier": 'epic', 'boost_type': 'hp', 'boost_percent': 21, 'ability_name': 'Attack Redirection', 'ability_description': 'Deflects any attack back at the enemy', 'image_key': 'Sogyo no Kotowari'},
    {"name": 'Nejibana', "tier": 'epic', 'boost_type': 'hp', 'boost_percent': 22, 'ability_name': 'Water Dragon', 'ability_description': 'Twisting water that pierces everything', 'image_key': 'Nejibana'},
    {"name": 'Ashisogi Jizo', "tier": 'epic', 'boost_type': 'hp', 'boost_percent': 19, 'ability_name': 'Paralytic Venom', 'ability_description': 'Stops enemy movement', 'image_key': 'Ashisogi Jizo'},
    {"name": "Ruri'iro Kujaku", "tier": 'epic', 'boost_type': 'hp', 'boost_percent': 18, 'ability_name': 'Spiritual Absorption', 'ability_description': 'Drains enemy spiritual pressure', 'image_key': "Ruri'iro Kujaku"},
    {"name": 'Gonryomaru', "tier": 'epic', 'boost_type': 'hp', 'boost_percent': 22, 'ability_name': 'Lightning Strike', 'ability_description': 'Electric-based attack', 'image_key': 'Gonryomaru'},
    {"name": 'Haguro Tonbo', "tier": 'epic', 'boost_type': 'hp', 'boost_percent': 17, 'ability_name': 'Straight Slash', 'ability_description': 'Simple but powerful direct attack', 'image_key': 'Haguro Tonbo'},
    {"name": 'Gegetsuburi', "tier": 'epic', 'boost_type': 'hp', 'boost_percent': 21, 'ability_name': 'Spiked Ball', 'ability_description': 'Giant crushing flail attack', 'image_key': 'Gegetsuburi'},
    {"name": 'Wabisuke', "tier": 'epic', 'boost_type': 'hp', 'boost_percent': 23, 'ability_name': 'Curse of Weight', 'ability_description': 'Doubles the weight of anything it cuts', 'image_key': 'Wabisuke'},
    {"name": 'Sealed Nozarashi', "tier": 'epic', 'boost_type': 'hp', 'boost_percent': 20, 'ability_name': '', 'ability_description': '', 'image_key': 'Sealed Nozarashi'},
    {"name": 'Murcielago', "tier": 'mythic', 'boost_type': 'damage', 'boost_percent': 41, 'ability_name': '', 'ability_description': '', 'image_key': 'Murcielago'},
    {"name": 'Los Lobos', "tier": 'legendary', 'boost_type': 'damage', 'boost_percent': 27, 'ability_name': '', 'ability_description': '', 'image_key': 'Los Lobos'},
    {"name": 'Pantera', "tier": 'legendary', 'boost_type': 'hp', 'boost_percent': 27, 'ability_name': '', 'ability_description': '', 'image_key': 'Pantera'},
    {"name": 'Gamuza', "tier": 'legendary', 'boost_type': 'hp', 'boost_percent': 27, 'ability_name': '', 'ability_description': '', 'image_key': 'Gamuza'},
    {"name": 'Tiburon', "tier": 'epic', 'boost_type': 'hp', 'boost_percent': 20, 'ability_name': '', 'ability_description': '', 'image_key': 'Tiburon Harribel'},
    {"name": 'Santa Teresa', "tier": 'epic', 'boost_type': 'hp', 'boost_percent': 22, 'ability_name': '', 'ability_description': '', 'image_key': 'Santa Teresa'},
    {"name": 'Fornicaras', "tier": 'epic', 'boost_type': 'damage', 'boost_percent': 20, 'ability_name': '', 'ability_description': '', 'image_key': 'Fornicaras'},
    {"name": 'Brujeria', "tier": 'rare', 'boost_type': 'hp', 'boost_percent': 20, 'ability_name': '', 'ability_description': '', 'image_key': 'Brujeria'},
    {"name": 'Glotoneria', "tier": 'rare', 'boost_type': 'hp', 'boost_percent': 19, 'ability_name': '', 'ability_description': '', 'image_key': 'Glotoneria'},
    {"name": 'Ira', "tier": 'rare', 'boost_type': 'hp', 'boost_percent': 18, 'ability_name': '', 'ability_description': '', 'image_key': 'Ira'},
    {"name": 'Kruzifix', "tier": 'mythic', 'boost_type': 'damage', 'boost_percent': 47, 'ability_name': '', 'ability_description': '', 'image_key': 'Kruzifix'},
    {"name": 'Freund Schild', "tier": 'mythic', 'boost_type': 'damage', 'boost_percent': 46, 'ability_name': '', 'ability_description': '', 'image_key': 'Freund Schild'},
    {"name": 'Diagramm', "tier": 'legendary', 'boost_type': 'damage', 'boost_percent': 30, 'ability_name': '', 'ability_description': '', 'image_key': 'Diagramm'},
    {"name": 'Tatar Foras', "tier": 'legendary', 'boost_type': 'damage', 'boost_percent': 26, 'ability_name': '', 'ability_description': '', 'image_key': 'Tatar Foras'},
    {"name": 'Ginrei Kojaku', "tier": 'legendary', 'boost_type': 'hp', 'boost_percent': 26, 'ability_name': '', 'ability_description': '', 'image_key': 'Ginrei Kojaku'},
]


async def _save_from_url(session: aiohttp.ClientSession, url: str, prefix: str) -> str:
    ext = Path(url.split("?")[0]).suffix or ".png"
    dest = UPLOAD_DIR / f"{prefix}{ext}"
    async with session.get(url) as resp:
        resp.raise_for_status()
        data = await resp.read()
    dest.write_bytes(data)
    return str(dest)


_AMBIGUOUS = object()


def _find_existing_weapon(w: dict):
    """Finds the DB row for one WEAPONS entry by name AND tier, and when two
    rows share both (the two mythic Minazuki, Bankai and Shikai) tells them
    apart by the entry's image_key inside the row's image_path.

    Returns the Weapon, None if there is no such weapon yet, or _AMBIGUOUS
    if it still can't tell which row is meant (the caller skips it rather
    than guess - guessing is what used to overwrite the wrong Minazuki).
    wp.find_weapon_by_name() only ever returns the first row with a name,
    so it can't be used for names shared by two weapons."""
    same_tier = [
        x for x in wp.list_weapons(enabled_only=False)
        if x.name.lower() == w["name"].lower() and x.tier == w["tier"]
    ]
    if len(same_tier) <= 1:
        return same_tier[0] if same_tier else None
    key = (w.get("image_key") or w["name"]).lower()
    matches = [x for x in same_tier if key in unquote(x.image_path).lower()]
    return matches[0] if len(matches) == 1 else _AMBIGUOUS


async def main():
    init_db()
    added_c = skipped_c = missing_c = updated_c = 0
    added_w = skipped_w = missing_w = updated_w = 0

    async with aiohttp.ClientSession() as session:
        print(f"Seeding {len(CHARACTERS)} characters...")
        for c in CHARACTERS:
            existing = ch.find_character_by_name(c["name"], enabled_only=False)
            if existing is not None:
                if (existing.hp, existing.attack, existing.tier,
                        existing.ability_name, existing.ability_description) == (
                        c["hp"], c["atk"], c["tier"],
                        c["ability_name"], c["ability_description"]):
                    skipped_c += 1
                    continue
                # Already exists but stats/ability/tier changed in CHARACTERS
                # above - update in place. This deliberately never touches
                # image_path, card_template_path, or card_image_path, so any
                # custom card art you've already set via /admin edit
                # character is left alone.
                ch.update_character_stats(
                    existing.id,
                    hp=c["hp"],
                    attack=c["atk"],
                    tier=c["tier"],
                    ability_name=c["ability_name"],
                    ability_description=c["ability_description"],
                )
                updated_c += 1
                print(f"  ~ {c['name']} updated ({c['tier']}, {c['hp']} HP / {c['atk']} ATK)")
                continue
            url = CHARACTER_IMAGES.get(c["name"])
            if not url:
                print(f"  ! no image mapped in soul.py for {c['name']!r}, skipping")
                missing_c += 1
                continue
            path = await _save_from_url(session, url, c["name"].lower().replace(" ", "_"))
            ch.add_character(
                name=c["name"],
                image_path=path,
                hp=c["hp"],
                attack=c["atk"],
                tier=c["tier"],
                ability_name=c["ability_name"],
                ability_description=c["ability_description"],
            )
            added_c += 1
            print(f"  + {c['name']} ({c['tier']})")

        print(f"\nSeeding {len(WEAPONS)} weapons...")
        seeded_this_run: set[tuple[str, str, str, int]] = set()
        for w in WEAPONS:
            # Some names are shared by two entries on purpose (e.g. the
            # Shikai and Bankai forms of "Nozarashi" and "Minazuki" are
            # both just called by the bare name now). _find_existing_weapon
            # matches on name + tier (+ image_key when two rows still tie),
            # and dupe_key below also keys on boost_type + boost_percent.
            dupe_key = (w["name"], w["tier"], w["boost_type"], w["boost_percent"])
            existing = _find_existing_weapon(w)
            if existing is _AMBIGUOUS:
                print(f"  ! {w['name']} ({w['tier']}): two rows match, can't tell which is {w.get('image_key')!r} - skipped")
                skipped_w += 1
                continue
            if existing is not None and (existing.tier, existing.boost_type, existing.boost_percent) == (w["tier"], w["boost_type"], w["boost_percent"]):
                skipped_w += 1
                continue
            if existing is not None and existing.tier == w["tier"]:
                # Same weapon (matched by name+tier), just a stale
                # boost_type/boost_percent - update it in place instead of
                # inserting a duplicate row. This was the actual bug: every
                # weapon already in the DB was seeded back when boost_percent
                # was still 0/unset, and this loop had no update-in-place
                # path (unlike the CHARACTERS loop above), so re-running the
                # seed after adding real percentages to WEAPONS never
                # actually reached the DB - it just kept skipping-or-would-
                # have-duplicated instead of correcting the existing row.
                wp.update_weapon_card(
                    existing.id, boost_type=w["boost_type"], boost_percent=w["boost_percent"]
                )
                updated_w += 1
                print(f"  ~ {w['name']} updated (+{w['boost_percent']}% {w['boost_type'].upper()})")
                continue
            if dupe_key in seeded_this_run:
                skipped_w += 1
                continue
            image_key = w.get("image_key") or w["name"]
            url = WEAPON_IMAGES.get(image_key)
            if not url:
                print(f"  ! no image mapped in zanpaku.py for {image_key!r}, skipping")
                missing_w += 1
                continue
            path = await _save_from_url(session, url, "weapon_" + image_key.lower().replace(" ", "_"))
            wp.add_weapon(
                name=w["name"],
                image_path=path,
                boost_type=w["boost_type"],
                boost_percent=w["boost_percent"],
                tier=w["tier"],
                ability_name=w["ability_name"],
                ability_description=w["ability_description"],
            )
            seeded_this_run.add(dupe_key)
            added_w += 1
            print(f"  + {w['name']} ({w['tier']})")

    # Master weapons table may have just gotten corrected boost_type/
    # boost_percent values above, but anyone who already caught one of
    # those weapons has a SNAPSHOT of the old (stale) values baked into
    # their owned_weapons row from catch time (see grant_weapon() in
    # db/collection.py) - fixing the master row alone doesn't touch
    # copies already in players' inventories/equipped in battle. Push
    # the corrected numbers down to every existing owned copy too.
    resynced_w = coll.resync_owned_weapon_stats()

    print("\n" + "=" * 50)
    print(f"Characters: {added_c} added, {updated_c} updated, {skipped_c} unchanged, {missing_c} missing an image mapping")
    print(f"Weapons:    {added_w} added, {updated_w} updated, {skipped_w} unchanged, {missing_w} missing an image mapping")
    print(f"Owned weapon copies resynced to corrected boosts: {resynced_w}")
    print("=" * 50)
    print(
        "\nEverything above is catchable/spawnable now with real stats and "
        "abilities. Card art (/card view, pack reveals) still falls back to "
        "the plain spawn image until you run /admin edit character or "
        "/admin edit weapon per entry to pick real card art from card.py."
    )

    return {
        "added_c": added_c, "updated_c": updated_c, "skipped_c": skipped_c, "missing_c": missing_c,
        "added_w": added_w, "updated_w": updated_w, "skipped_w": skipped_w, "missing_w": missing_w,
        "resynced_w": resynced_w,
    }


if __name__ == "__main__":
    asyncio.run(main())