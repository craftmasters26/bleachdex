"""
Zanpakuto/weapon artwork - GitHub-hosted images used by /admin weapon add.

All images now live in one consolidated repo folder
("New Weapons images/New Weapons images"), replacing the old
"images/zanputo image" folder. Keys are the exact file name (without
extension) so the two Shikai/Bankai pairs that share a bare weapon
name in the database - Nozarashi and Minazuki - still resolve to two
different images. See seed_roster.py's WEAPONS list ("image_key" on
each entry) for how a given (name, tier, atk) maps to one of these
keys.
"""

WEAPON_IMAGES = {
    'Ira': 'https://raw.githubusercontent.com/craftmasters26/bleachdex/main/New%20Weapons%20images/New%20Weapons%20images/Ira.png',
    'Ashisogi Jizo': 'https://raw.githubusercontent.com/craftmasters26/bleachdex/main/New%20Weapons%20images/New%20Weapons%20images/Ashisogi%20Jizo.png',
    'Benihime': 'https://raw.githubusercontent.com/craftmasters26/bleachdex/main/New%20Weapons%20images/New%20Weapons%20images/Benihime.png',
    'Brujeria': 'https://raw.githubusercontent.com/craftmasters26/bleachdex/main/New%20Weapons%20images/New%20Weapons%20images/Brujeria.png',
    'Daiguren Hyorinmaru': 'https://raw.githubusercontent.com/craftmasters26/bleachdex/main/New%20Weapons%20images/New%20Weapons%20images/Daiguren%20Hyorinmaru.png',
    'Diagramm': 'https://raw.githubusercontent.com/craftmasters26/bleachdex/main/New%20Weapons%20images/New%20Weapons%20images/Diagramm.png',
    'Fornicaras': 'https://raw.githubusercontent.com/craftmasters26/bleachdex/main/New%20Weapons%20images/New%20Weapons%20images/Fornicaras.png',
    'Freund Schild': 'https://raw.githubusercontent.com/craftmasters26/bleachdex/main/New%20Weapons%20images/New%20Weapons%20images/Freund%20Schild.png',
    'Gamuza': 'https://raw.githubusercontent.com/craftmasters26/bleachdex/main/New%20Weapons%20images/New%20Weapons%20images/Gamuza.png',
    'Gegetsuburi': 'https://raw.githubusercontent.com/craftmasters26/bleachdex/main/New%20Weapons%20images/New%20Weapons%20images/Gegetsuburi.png',
    'Ginrei Kojaku': 'https://raw.githubusercontent.com/craftmasters26/bleachdex/main/New%20Weapons%20images/New%20Weapons%20images/Ginrei%20Kojaku.png',
    'Glotoneria': 'https://raw.githubusercontent.com/craftmasters26/bleachdex/main/New%20Weapons%20images/New%20Weapons%20images/Glotoneria.png',
    'Gonryomaru': 'https://raw.githubusercontent.com/craftmasters26/bleachdex/main/New%20Weapons%20images/New%20Weapons%20images/Gonryomaru.png',
    'Haguro Tonbo': 'https://raw.githubusercontent.com/craftmasters26/bleachdex/main/New%20Weapons%20images/New%20Weapons%20images/Haguro%20Tonbo.png',
    'Haineko (Shikai)': 'https://raw.githubusercontent.com/craftmasters26/bleachdex/main/New%20Weapons%20images/New%20Weapons%20images/Haineko%20%28Shikai%29.png',
    'Hakka no Togame': 'https://raw.githubusercontent.com/craftmasters26/bleachdex/main/New%20Weapons%20images/New%20Weapons%20images/Hakka%20no%20Togame.png',
    'Hozukimaru': 'https://raw.githubusercontent.com/craftmasters26/bleachdex/main/New%20Weapons%20images/New%20Weapons%20images/Hozukimaru.png',
    'Hyorinmaru': 'https://raw.githubusercontent.com/craftmasters26/bleachdex/main/New%20Weapons%20images/New%20Weapons%20images/Hyorinmaru.png',
    'Ichimonji': 'https://raw.githubusercontent.com/craftmasters26/bleachdex/main/New%20Weapons%20images/New%20Weapons%20images/Ichimonji.png',
    'Jakuho Raikoben': 'https://raw.githubusercontent.com/craftmasters26/bleachdex/main/New%20Weapons%20images/New%20Weapons%20images/Jakuho%20Raikoben.png',
    'Kamishini no Yari': 'https://raw.githubusercontent.com/craftmasters26/bleachdex/main/New%20Weapons%20images/New%20Weapons%20images/Kamishini%20no%20Yari.png',
    'Kannonbiraki Benihime Aratame': 'https://raw.githubusercontent.com/craftmasters26/bleachdex/main/New%20Weapons%20images/New%20Weapons%20images/Kannonbiraki%20Benihime%20Aratame.png',
    'Katen Kyokotsu': 'https://raw.githubusercontent.com/craftmasters26/bleachdex/main/New%20Weapons%20images/New%20Weapons%20images/Katen%20Kyokotsu.png',
    'Katen Kyokotsu Karamatsu Shinju': 'https://raw.githubusercontent.com/craftmasters26/bleachdex/main/New%20Weapons%20images/New%20Weapons%20images/Katen%20Kyokotsu%20Karamatsu%20Shinju.png',
    'Kazeshini': 'https://raw.githubusercontent.com/craftmasters26/bleachdex/main/New%20Weapons%20images/New%20Weapons%20images/Kazeshini.png',
    'Kinshara': 'https://raw.githubusercontent.com/craftmasters26/bleachdex/main/New%20Weapons%20images/New%20Weapons%20images/Kinshara.png',
    'Kinshara Butodan': 'https://raw.githubusercontent.com/craftmasters26/bleachdex/main/New%20Weapons%20images/New%20Weapons%20images/Kinshara%20Butodan.png',
    "Kokujo Tengen Myo'o": 'https://raw.githubusercontent.com/craftmasters26/bleachdex/main/New%20Weapons%20images/New%20Weapons%20images/Kokujo%20Tengen%20Myo%27o.png',
    'Konjiki Ashisogi Jizo': 'https://raw.githubusercontent.com/craftmasters26/bleachdex/main/New%20Weapons%20images/New%20Weapons%20images/Konjiki%20Ashisogi%20Jizo.png',
    'Kruzifix': 'https://raw.githubusercontent.com/craftmasters26/bleachdex/main/New%20Weapons%20images/New%20Weapons%20images/Kruzifix.png',
    'Kyoka Suigetsu': 'https://raw.githubusercontent.com/craftmasters26/bleachdex/main/New%20Weapons%20images/New%20Weapons%20images/Kyoka%20Suigetsu.png',
    'Los Lobos': 'https://raw.githubusercontent.com/craftmasters26/bleachdex/main/New%20Weapons%20images/New%20Weapons%20images/Los%20Lobos.png',
    'Minazuki (Shikai)': 'https://raw.githubusercontent.com/craftmasters26/bleachdex/main/New%20Weapons%20images/New%20Weapons%20images/Minazuki%20%28Shikai%29.png',
    'minazuki bankai': 'https://raw.githubusercontent.com/craftmasters26/bleachdex/main/New%20Weapons%20images/New%20Weapons%20images/minazuki%20bankai.png',
    'Murcielago': 'https://raw.githubusercontent.com/craftmasters26/bleachdex/main/New%20Weapons%20images/New%20Weapons%20images/Murcielago.png',
    'Nejibana': 'https://raw.githubusercontent.com/craftmasters26/bleachdex/main/New%20Weapons%20images/New%20Weapons%20images/Nejibana.png',
    'Nozarashi (Bankai)': 'https://raw.githubusercontent.com/craftmasters26/bleachdex/main/New%20Weapons%20images/New%20Weapons%20images/Nozarashi%20%28Bankai%29.png',
    'Nozarashi Shikai': 'https://raw.githubusercontent.com/craftmasters26/bleachdex/main/New%20Weapons%20images/New%20Weapons%20images/Nozarashi%20Shikai.png',
    'Pantera': 'https://raw.githubusercontent.com/craftmasters26/bleachdex/main/New%20Weapons%20images/New%20Weapons%20images/Pantera.png',
    "Ruri'iro Kujaku": 'https://raw.githubusercontent.com/craftmasters26/bleachdex/main/New%20Weapons%20images/New%20Weapons%20images/Ruri%27iro%20Kujaku.png',
    'Ryujin Jakka': 'https://raw.githubusercontent.com/craftmasters26/bleachdex/main/New%20Weapons%20images/New%20Weapons%20images/Ryujin%20Jakka.png',
    'Ryumon Hozukimaru': 'https://raw.githubusercontent.com/craftmasters26/bleachdex/main/New%20Weapons%20images/New%20Weapons%20images/Ryumon%20Hozukimaru.png',
    'Sakanade': 'https://raw.githubusercontent.com/craftmasters26/bleachdex/main/New%20Weapons%20images/New%20Weapons%20images/Sakanade.png',
    'Sakashima Yokoshima Happo Fusagari': 'https://raw.githubusercontent.com/craftmasters26/bleachdex/main/New%20Weapons%20images/New%20Weapons%20images/Sakashima%20Yokoshima%20Happo%20Fusagari.png',
    'Santa Teresa': 'https://raw.githubusercontent.com/craftmasters26/bleachdex/main/New%20Weapons%20images/New%20Weapons%20images/Santa%20Teresa.png',
    'Sealed Nozarashi': 'https://raw.githubusercontent.com/craftmasters26/bleachdex/main/New%20Weapons%20images/New%20Weapons%20images/Sealed%20Nozarashi.png',
    'Senbonzakura': 'https://raw.githubusercontent.com/craftmasters26/bleachdex/main/New%20Weapons%20images/New%20Weapons%20images/Senbonzakura.png',
    'Senbonzakura Kageyoshi': 'https://raw.githubusercontent.com/craftmasters26/bleachdex/main/New%20Weapons%20images/New%20Weapons%20images/Senbonzakura%20Kageyoshi.png',
    'Shinso': 'https://raw.githubusercontent.com/craftmasters26/bleachdex/main/New%20Weapons%20images/New%20Weapons%20images/Shinso.png',
    'Sode no Shirayuki': 'https://raw.githubusercontent.com/craftmasters26/bleachdex/main/New%20Weapons%20images/New%20Weapons%20images/Sode%20no%20Shirayuki.png',
    'Sogyo no Kotowari': 'https://raw.githubusercontent.com/craftmasters26/bleachdex/main/New%20Weapons%20images/New%20Weapons%20images/Sogyo%20no%20Kotowari.png',
    'Soo Zabimaru': 'https://raw.githubusercontent.com/craftmasters26/bleachdex/main/New%20Weapons%20images/New%20Weapons%20images/Soo%20Zabimaru.png',
    'Suzumebachi': 'https://raw.githubusercontent.com/craftmasters26/bleachdex/main/New%20Weapons%20images/New%20Weapons%20images/Suzumebachi.png',
    'Tachikaze': 'https://raw.githubusercontent.com/craftmasters26/bleachdex/main/New%20Weapons%20images/New%20Weapons%20images/Tachikaze.png',
    'Tatar Foras': 'https://raw.githubusercontent.com/craftmasters26/bleachdex/main/New%20Weapons%20images/New%20Weapons%20images/Tatar%20Foras.png',
    'Tekken Tachikaze': 'https://raw.githubusercontent.com/craftmasters26/bleachdex/main/New%20Weapons%20images/New%20Weapons%20images/Tekken%20Tachikaze.png',
    'Tenken': 'https://raw.githubusercontent.com/craftmasters26/bleachdex/main/New%20Weapons%20images/New%20Weapons%20images/Tenken.png',
    'Tensa Zangetsu': 'https://raw.githubusercontent.com/craftmasters26/bleachdex/main/New%20Weapons%20images/New%20Weapons%20images/Tensa%20Zangetsu.png',
    'Tiburon Harribel': 'https://raw.githubusercontent.com/craftmasters26/bleachdex/main/New%20Weapons%20images/New%20Weapons%20images/Tiburon%20Harribel.png',
    'Tobiume': 'https://raw.githubusercontent.com/craftmasters26/bleachdex/main/New%20Weapons%20images/New%20Weapons%20images/Tobiume.png',
    'Wabisuke': 'https://raw.githubusercontent.com/craftmasters26/bleachdex/main/New%20Weapons%20images/New%20Weapons%20images/Wabisuke.png',
    'Zabimaru': 'https://raw.githubusercontent.com/craftmasters26/bleachdex/main/New%20Weapons%20images/New%20Weapons%20images/Zabimaru.png',
    'Zangetsu': 'https://raw.githubusercontent.com/craftmasters26/bleachdex/main/New%20Weapons%20images/New%20Weapons%20images/Zangetsu.png',
    'Zanka no Tachi': 'https://raw.githubusercontent.com/craftmasters26/bleachdex/main/New%20Weapons%20images/New%20Weapons%20images/Zanka%20no%20Tachi.png',
}