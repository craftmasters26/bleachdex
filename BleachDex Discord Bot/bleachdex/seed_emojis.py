"""
Sets the custom emoji ID on every character/weapon whose emoji was
uploaded to the Developer Portal (Application Emojis) - the same thing
`/admin emoji add` does one at a time, done in bulk.

Run from Discord with `/admin seed emojis` (single-process hosts have no
shell), or standalone: `python3 seed_emojis.py`. Safe to re-run - it just
(re)writes the same IDs. Matches by EXACT name, so it works on the live
database whatever its row IDs are, and never touches player data.

Why this exists instead of just looping `/admin emoji add`: 13 names are
both a zanpakuto spirit CHARACTER and its WEAPON (Zabimaru, Tobiume,
Kazeshini, ...), and `/admin emoji add` refuses those as ambiguous. Here
each one is assigned explicitly - the weapon-icon emoji go to the weapon.

Not assigned (no matching row in the bot): the "shinsoshikai" emoji.
"""

from db.connection import get_connection, init_db

# (exact character name, emoji ID)
CHARACTER_EMOJI = [
    ('Abirama Redder', '1548683278330896454'),
    ('Aura Michibane', '1548683286782550126'),
    ('Ban', '1548683291123523715'),
    ('Barragan Louisenbairn', '1548683293220671548'),
    ('Bau', '1548683296177660005'),
    ('Benin', '1548683299411599380'),
    ('Charlotte Chuhlhourne', '1548683308576276490'),
    ('Choe Neng Poww', '1548683312623521852'),
    ('Cirucci Sanderwicci', '1548683316222230700'),
    ('Cyan Sun-Sun', '1548683320697557082'),
    ('Dordoni Alessandro Del Socaccio', '1548683326783619162'),
    ('Edrad Liones', '1548683331548487740'),
    ('Emilou Apacci', '1548683334517788772'),
    ('Enryu', '1548683336342569091'),
    ('Findorr Calius', '1548683338280206346'),
    ('Franceska Mila Rose', '1548683340432023602'),
    ('Ganryu', '1548683344156295321'),
    ('Gantenbainne Mosqueda', '1548683346006118460'),
    ('Garogai', '1548683347851747429'),
    ('Genga', '1548683351785742446'),
    ('Gesell', '1548683357532070009'),
    ('Ggio Vega', '1548683359746654288'),
    ('Go Koga', '1548683369397756025'),
    ('Grand Fisher', '1548683373252317224'),
    ('Grimmjow Jaegerjaquez', '1548683376746037268'),
    ('Gunjo', '1548683378436345926'),
    ('Gyakuaku Kumoi', '1548683380361535508'),
    ('Haineko', '1548683383968899082'),
    ('Hanza Nukui', '1548683387810742272'),
    ('Hikone Ubuginu', '1548683391950651504'),
    ('Hisagomaru', '1548683394265784371'),
    ('Ho', '1548683399282167919'),
    ('Homura', '1548683401370927194'),
    ('Ichigo Kurosaki', '1548683406324400269'),
    ('Ikumi Unagiya', '1548683410984403096'),
    ('Izuru Kira', '1550409142798123088'),
    ('Jai', '1548683420526448650'),
    ('Jin Kariya', '1548683423130976327'),
    ('Jinnai Douko', '1548683425555419317'),
    ('Jushiro Ukitake', '1548683694984790087'),
    ('Kageroza Inaba', '1548683431393763418'),
    ('Kaname Tosen', '1548683435302723705'),
    ('Kaoru Unagiya', '1548683437454659735'),
    ('Karin Kurosaki', '1548683450519781466'),
    ('Kazui Kurosaki', '1548683455121068113'),
    ('Kenpachi Kiganjo', '1548683458879160422'),
    ('Kenryu', '1548683462616154212'),
    ('Kirikaze', '1548683466583842907'),
    ('Kirio Hikifune', '1548683390214086706'),
    ('Kokuto', '1548683472753664110'),
    ('Kurudo', '1548683485642891294'),
    ('Kuruyashiki Kenpachi', '1548683487782109184'),
    ('Lurichiyo Kasumiōji', '1548683601753936022'),
    ('Mabashi', '1548683501845352588'),
    ('Maki Ichinose', '1548683506639708180'),
    ('Makoto Kibune', '1548683510548537414'),
    ('Mask De Masculine', '1548683519243329577'),
    ('Mue', '1548683530341715998'),
    ('Muramasa', '1548683532111450253'),
    ('Narunosuke', '1548683537522233395'),
    ('Nianzol Weizol', '1548683543255720130'),
    ('Nirgge Parduoc', '1548683545399005275'),
    ('Noba', '1548683549954015352'),
    ('Nozomi Kujo', '1548683554416885800'),
    ('Ohana Katen', '1548683559521222656'),
    ('Oko Yushima', '1548683562625269841'),
    ('Okyo Kyokotsu', '1548683564713906176'),
    ('Orihime Inoue', '1548683566714593310'),
    ('Ouko Yushima', '1548683569650466857'),
    ('Renji Abarai', '1548683580392345630'),
    ('Ririn', '1548683584481661009'),
    ('Riyan', '1548683588562714725'),
    ('Roka Paramia', '1548683592216088596'),
    ('Rudbornn Chelute', '1548683598067142749'),
    ('Rukia Kuchiki', '1548683599845396530'),
    ('Ryu Kuzu', '1548683606497558709'),
    ('Ryuken Ishida', '1548683609500819486'),
    ('Sawatari', '1548683625111748639'),
    ('Senna', '1548683628538630294'),
    ('Shawlong Koufang', '1548683632493731960'),
    ('Shinji Hirako', '1548683636293763143'),
    ('Shintaro', '1548683638407954585'),
    ('Shizuku', '1548683640215568384'),
    ('Shuhei Hisagi', '1548683642350342235'),
    ('Shuren', '1548683648516104282'),
    ('Shusuke Amagai', '1548683650764243035'),
    ('Sojiro Kusaka', '1548683656556576839'),
    ('Sojun Kuchiki', '1548683658850869280'),
    ('Soul King', '1548683662940311725'),
    ('Taikun', '1548683670116638750'),
    ('Tier Harribel', '1548683684465348658'),
    ('Tokinada Tsunayashiro', '1548683688043220992'),
    ('Ugaki', '1548683692011028661'),
    ('Uryu Ishida', '1548683700844232804'),
    ('Yachiru Kusajishi', '1548683708976857228'),
    ('Yang', '1548683713846583346'),
    ('Yasutora Sado', '1548683716484927538'),
    ('Yin', '1548683720700067910'),
    ('Yoshi', '1548683727394054175'),
    ('Yoshino Soma', '1548683730409885776'),
    ('Yylfordt Granz', '1548683738043387914'),
    ('Äs Nödt', '1548683280214261791'),
]

# (exact weapon name, emoji ID)
WEAPON_EMOJI = [
    ('Ashisogi Jizo', '1548683024122515496'),
    ('Brujeria', '1548683028560220161'),
    ('Daiguren Hyorinmaru', '1548683030393004032'),
    ('Diagramm', '1548683032381358211'),
    ('Fornicaras', '1548683034310610974'),
    ('Freund Schild', '1548683039901618267'),
    ('Gamuza', '1548683042925711481'),
    ('Ginrei Kojaku', '1548683047417675886'),
    ('Glotoneria', '1548683049405784094'),
    ('Gonryomaru', '1548683051217719296'),
    ('Haguro Tonbo', '1548683052979331112'),
    ('Hakka no Togame', '1548683057307979796'),
    ('Hozukimaru', '1548683059472236584'),
    ('Hyorinmaru', '1548683061497958441'),
    ('Ichimonji', '1548683063418953768'),
    ('Ira', '1548683066052976771'),
    ('Jakuho Raikoben', '1548683068066504834'),
    ('Kamishini no Yari', '1548683070079500309'),
    ('Kannonbiraki Benihime Aratame', '1548683072021598209'),
    ('Katen Kyokotsu', '1548683076199252009'),
    ('Kazeshini', '1548683078656987188'),
    ('Kinshara', '1548683083266654268'),
    ('Kinshara Butodan', '1548683081358114826'),
    ("Kokujo Tengen Myo'o", '1548683085611012096'),
    ('Konjiki Ashisogi Jizo', '1548683088022732881'),
    ('Kruzifix', '1548683090224873552'),
    ('Kyoka Suigetsu', '1548683092473024643'),
    ('Los Lobos', '1548683094658261135'),
    ('Murcielago', '1548683100446400533'),
    ('Nejibana', '1548683102321246208'),
    ('Pantera', '1548683108235219074'),
    ("Ruri'iro Kujaku", '1548683110630301706'),
    ('Ryujin Jakka', '1548683112408555612'),
    ('Ryumon Hozukimaru', '1548683114467958904'),
    ('Sakanade', '1548683118997672067'),
    ('Sakashima Yokoshima Happo Fusagari', '1548683122101723238'),
    ('Santa Teresa', '1548683124228096080'),
    ('Sealed Nozarashi', '1548683125935185981'),
    ('Senbonzakura', '1548683130741727333'),
    ('Senbonzakura Kageyoshi', '1548683128048980060'),
    ('Shinso', '1548683135703580693'),
    ('Sode no Shirayuki', '1548683137750532106'),
    ('Sogyo no Kotowari', '1548683140137099365'),
    ('Soo Zabimaru', '1548683142016143451'),
    ('Suzumebachi', '1548683144255901756'),
    ('Tachikaze', '1548683146227220561'),
    ('Tatar Foras', '1548683148399742986'),
    ('Tekken Tachikaze', '1548683150375391312'),
    ('Tenken', '1548683152539521116'),
    ('Tensa Zangetsu', '1548683154393665717'),
    ('Tiburon', '1548683156692148294'),
    ('Tobiume', '1548683160336859156'),
    ('Wabisuke', '1548683162522091703'),
    ('Zabimaru', '1548683164552274002'),
    ('Zangetsu', '1548683166921793586'),
    ('Zanka no Tachi', '1548683168976994324'),
]


def seed_emojis() -> dict:
    """Returns {"characters": n, "weapons": n, "missing": [(kind, name), ...]}."""
    init_db()
    conn = get_connection()
    done = {"characters": 0, "weapons": 0}
    missing: list[tuple[str, str]] = []
    try:
        for table, kind, pairs in (
            ("characters", "character", CHARACTER_EMOJI),
            ("weapons", "weapon", WEAPON_EMOJI),
        ):
            for name, emoji_id in pairs:
                cur = conn.execute(f"UPDATE {table} SET emoji = ? WHERE name = ?", (emoji_id, name))
                if cur.rowcount:
                    done[table] += cur.rowcount
                else:
                    missing.append((kind, name))
        conn.commit()
    finally:
        conn.close()
    return {**done, "missing": missing}


if __name__ == "__main__":
    r = seed_emojis()
    print(f"Emoji set on {r['characters']} characters and {r['weapons']} weapons.")
    for kind, name in r["missing"]:
        print(f"  not found: {kind} {name}")