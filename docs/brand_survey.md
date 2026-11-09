# Опитування брендів на Shafa (9.11.2026)

Список: «Бренди для моніторингу Shafa / OLX» (823 позиції). Профіль розмірів для заміру: одяг L, XL · штани W34, W36, W38 · взуття 45, 45.5, 46. Розділ: чоловічий. Сирі дані: [`data/brand_survey.json`](../data/brand_survey.json), інструмент: `tools/survey.py`.

## Як міряли

1. **Id брендів:** запит сайту `filterBrand(name, first: 20)` (знайдено в коді сторінки каталогу, пошук за підрядком, без урахування діакритики), 15 назв в одному HTTP-запиті через аліаси GraphQL. 81 запит на 1 213 пошукових термінів.
2. **Ручна розмітка** неточних збігів: аліаси (інша назва на Shafa), саб-лейбли (лінійки без власного бренду: RL Purple Label, NB Made in USA, LVC…), відсутні.
3. **Частота:** для кожного бренду — товарів загалом, у чоловічому розділі, у моїх розмірах, і скільки з 100 (для гарячих — з 300) найновіших у моїх розмірах створено за 30 днів. 8 брендів в одному HTTP-запиті; 84 запити.
4. **Текстовий пошук** (`searchText`) для назв, яких немає серед брендів: чи згадують їх продавці в заголовку. 31 запит.
5. Усього ~230 HTTP-запитів з паузою 2 с, без авторизації.

## Пакети

| Пакет | Брендів | Нових у моїх розмірах за 30 днів (сума) | Пропоную опитувати | Запитів на прохід |
|---|---|---|---|---|
| A гарячі | 42 | 4997 | кожні 10 хв | 1 запит (≤100 брендів) |
| B звичайні | 76 | 728 | кожні 10 хв | 1 запит |
| C1 рідкісні (1–3/міс) | 139 | 229 | кожні 30 хв | 2 запити |
| C2 тихі (є в розмірах, 0 за 30 днів) | 178 | 0 | кожні 3 год | 2 запити |
| C3 men, але не мої розміри | 64 | 0 | раз на добу | 1 запит |
| D1 лише жін/дит/аксесуари | 51 | — | раз на тиждень | 1 запит |
| D2 бренд є, речей 0 | 32 | — | раз на тиждень | 1 запит |
| E1 текст: є згадки | 47 | — | текстовий пошук раз на добу | 5 HTTP (аліаси по 10) |
| E2 текст: нічого | 167 | — | текстовий пошук раз на тиждень | 17 HTTP (аліаси по 10) |
| S саб-лейбл | 27 | — | з батьківським брендом (A/B) + фільтр за фразою | 0 окремих |

Число в дужках біля бренду — нових речей у моїх розмірах за 30 днів. ❓ — назва загальна, id знайдено за схожістю; перевірити, що це той самий бренд.

### A гарячі — 42

Stone Island (287), Loro Piana (285), Moncler (276), Burberry (273), C.P. Company (273), Ralph Lauren (270), Lacoste (263), Asics (257), Salomon (255), Fred Perry (210), Hugo Boss (202), Timberland (159), Carhartt (134), Massimo Dutti (133), Arc'teryx (128), Patagonia (115), Lyle & Scott (105), Gant (104), Barbour (86), C&A (86), Canada Goose (78), Dickies (69), Mammut (69), Saucony Originals (67), Ecco (63), Brunello Cucinelli (58), YSL (55), Lowa (53), Paul & Shark (53), Ermenegildo Zegna (51), Alpha Industries (50), AMI Paris (47) ❓, Charles Tyrwhitt (45), Christian Dior Monsieur (43), Dior Homme (43), Helly Hansen (40), COS (39), Marc O'Polo (37), Scotch & Soda (37), Vivienne Westwood (35), Carhartt WIP (34), Prada (30)

### B звичайні — 76

Strellson (26), Kenzo (23), Reiss (22), Kiton (21), Paul Smith (21), Bogner (20), Banana Republic (19), Peak Performance (19), Givenchy Gentleman (17), Hackett London (17), Selected Homme (17), Acne Studios (16), Fjallraven (16), Loewe (16), Roy Robson (13), Schott NYC (13), Suitsupply (13), Belstaff (12), Berluti (12), Brioni (12), Eton (12), Giorgio Armani (12), Haglofs (12), Hermes (12), Herno (11), Lanvin (11), Maison Margiela (11), Canali (10), Digel (10), Schoffel (10), ARKET (9), Anerkjendt (9), Lands' End (9), Mizuno (9), Alberto (8), Etro (8), Glenmuir (8), Harris Tweed (8), Olymp (8), Eterna (7), Hawes & Curtis (7), Lloyd (7), Maerz Muenchen (7), Pringle of Scotland (7), Rukka (7), Aquascutum (6), Austin Reed (6), Gran Sasso (6), Jaeger (6), Lindbergh (6), Pal Zileri (6), Rick Owens (6), Scarpa (6), T.M. Lewin (6), Birkenstock (5), Brooks Brothers (5), Carl Gross (5), Casablanca (5), Folk (5), Iceberg (5), Meyer (5), Onitsuka Tiger (5), Peuterey (5), Santoni (5), The Kooples (5), van Laack (5), Bally (4), Corneliani (4), Eduard Dressler (4), J.Lindeberg (4), Jean Paul Gaultier (4), Meindl (4), Montbell (4), Oscar Jacobson (4), Tod's (4), Universal Works (4)

### C1 рідкісні (1–3/міс) — 139

Aigle (3), Berwich (3), Bottega Veneta (3), Cavallaro Napoli (3), Eddie Bauer (3), Edwin (3), Fedeli (3), Filippo De Laurentiis (3), Florsheim Imperial (3), Hiltl (3), Kronstadt (3), Lardini (3), Lodenfrey (3), Missoni (3), Norrona (3), Norse Projects (3), Orvis (3), Percival (3), Profuomo (3), Seidensticker (3), Tenson (3), Thomas Pink (3), A.P.C. (2), And Wander (2), Baldessarini (2), Bertoni (2), Briglia 1949 (2), Bruun & Stengade (2), Cinque (2), Circolo 1901 (2), Crombie (2), Cruciani (2), Daks (2), Dale of Norway (2), Denham (2), Eleventy (2), Filippa K (2), Gianfranco Ferre (2), Gieves & Hawkes (2), Gloverall (2), Gramicci (2), Halti (2), Incotex (2), Les Deux (2), Loake (2), Maharishi (2), Malo (2), Matinique (2), Mephisto (2), Minimum (2), Musto (2), Penfield (2), Raf Simons (2), Reda (2), Rene Lezard (2), Sandro Paris (2), Schneiders Salzburg (2), Sebago (2), Stenstroms (2), Undercover (2), Van Gils (2), Viyella (2), Warehouse (2), Wood Wood (2), Woolrich (2), Woolrich Woolen Mills (2), Yohji Yamamoto Pour Homme (2), Zimmerli (2), Aime Leon Dore (1), Aran Crafts (1), Avant Toi (1), Barker (1), Benvenuto (1), Bergans (1), Blaumann Jeanshosen (1), Bob Company (1), Caruso (1), Celine (1), Cerruti 1881 (1), Chester Barrie (1), Closed (1), Club Monaco (1), Cockpit USA (1), Common Projects (1), Coogi (1), Devold (1), Driza-Bone (1), Drykorn (1), Dunhill (1), El Ganso (1), Faconnable (1), Fay (1), Geiger (1), Giesswein (1), Green Label Relaxing (1) ❓, Han Kjobenhavn (1), Hanwag (1), Hawick Knitwear (1), Helmut Lang (1), Holubar (1), J.Crew (1), J.M. Weston (1), Jacquemus (1), Johnstons of Elgin (1), L.B.M. 1911 (1), Luhta (1), Magee 1866 (1), Maison Kitsune (1), Marimekko (1), Mazzarelli (1), NN07 (1), Nobis (1), Nudie Jeans (1), Number (N)ine (1), Oliver Spencer (1), Orlebar Brown (1), PT Torino (1), Paoloni (1), Paul James Knitwear (1), Peter Scott (1), Rains (1), Red Wing (1), Sacai (1), Samsoe Samsoe (1), Scabal (1), Seeland (1), Sorel (1), Sperry Top-Sider (1), Steinbock (1), Tagliatore (1), Theory (1), Thorogood (1), Tiger of Sweden (1), Uniforms for the Dedicated (1), Vilebrequin (1), Vince (1), Windsor (1), Wolsey (1), Woodbird (1)

### C2 тихі (є в розмірах, 0 за 30 днів) — 178

120% Lino (0), 66 North (0), A Day's March (0), A Kind of Guise (0) ❓, A.Testoni (0), Adolfo Dominguez (0), Agnes b. (0), Alan Paine (0), Albam (0), Alfred Sargent (0), Allen Edmonds (0), Altea (0), Amundsen Sports (0), Armor-Lux (0), Asket (0), Aspesi (0), Axel Arigato (0), Bagutta (0), Ballantyne (0), Baracuta (0), Barba Napoli (0), Barena Venezia (0), Barrett (0), Barrie (0), Beams (0), Bellerose (0), Belvest (0), Berwick 1707 (0), Bobson (0), Boglioli (0), BonneGueule (0), Boris Bidjan Saberi (0), Brora (0), Bruuns Bazaar (0), Byblos (0), Cafe Coton (0), Camper (0), Cantarelli (0), Cesare Attolini (0), Cheaney (0), Christian Lacroix (0), Church's (0), Claude Montana (0), Colorful Standard (0), Cordings (0), Crockett & Jones (0), Daniele Alessandrini (0), Danner (0), Didriksons (0), Dormeuil (0), Doucal's (0), Drake's (0), Dries Van Noten (0), Drumohr (0), Duvetica (0), Ede & Ravenscroft (0), Elvine (0), Engineered Garments (0), Ferragamo (0), Filling Pieces (0), Finamore (0), Fisherman Out of Ireland (0) ❓, Five Brother (0), Fratelli Rossetti (0), Frye (0), G.H. Bass (0), GTA Moda (0) ❓, Gabba (0), Gitman Vintage (0), Glanshirt (0), Goldwin (0), Grenfell (0), Grenson (0), Habsburg (0), Hamaki-Ho (0), Hanro (0), Hardy Amies (0), Harkila (0), Hartford (0), Hawico (0), Henrik Vibskov (0), Heschung (0), Hessnatur (0), Hoggs of Fife (0), Holland & Holland (0), Holzweiler (0), Hope Stockholm (0) ❓, Houdini (0), Isaia (0), John Smedley (0), Julius (0), Junk de Luxe (0), Junya Watanabe MAN (0), Kapital (0), Karhu (0), Kestin (0), Kings of Indigo (0), Klattermusen (0), KnowledgeCotton Apparel (0), L.L.Bean (0), Lemaire (0), Lewis Leathers (0), Libertine-Libertine (0), Los Angeles Apparel (0), Lubiam (0), Luigi Borrelli (0), Mackintosh (0), Mads Norgaard (0), Magnanni (0), Makia (0), Marinella (0), Marni (0), Marsell (0), Martine Rose (0), Mey & Edlich (0), Mister Freedom (0), Moonstar (0), Moorer (0), Moreschi (0), Morris Stockholm (0) ❓, Mr P. (0), Muji (0), Nanamica (0), Nanushka (0), National Standard (0), Nigel Cabourn (0), Novesta (0), Octobre Editions (0), Officine Creative (0), Oger (0), Oliver Cabell (0), Onia (0), Original Montgomery (0) ❓, Our Legacy (0), Outerknown (0), Panama Jack (0), Paolo Pecora (0), Parajumpers (0), Pedro del Hierro (0), Pendleton (0), Portuguese Flannel (0), R.M. Williams (0), Rag & Bone (0), Regent (0), Richard James (0), Roberto Collina (0), Romeo Gigli (0), Rundholz (0), Saint James (0), Samurai Jeans (0) ❓, Sand Copenhagen (0), Sasta (0), Sauce Zhan (0), Shoepassion (0), Sierra Designs (0), Solovair (0), St. John's Bay (0), Stephan Schneider (0), Still by Hand (0), Strenesse (0), Studio Nicholson (0), Sunspel (0), Superga (0), Tintoria Mattei 954 (0), Transit Uomo (0), Tricker's (0), Turnbull & Asser (0), Turo (0), Ulvang (0), Veja (0), Vitale Barberis Canonico (0), Waldviertler (0), Wax London (0), William Lockie (0), Wooyoungmi (0), Xacus (0), YMC (0), Zanone (0)

### C3 men, але не мої розміри — 64

04651/A Trip in a Bag (0), Alden (0), Ann Demeulemeester (0), Auralee (0), Big John (0), Blarney Woollen Mills (0) ❓, Bode (0), Buttero (0), CamperLab (0), Carmina (0), Castaner (0), Chippewa (0), Corridor NYC (0) ❓, Craig Green (0), Damir Doma (0), Diemme (0), Eastland (0), Eternal (0), Eytys (0), Filson (0), Fracap (0), Gabriele Pasini (0), Golden Bear (0), Grant Stone (0), Heinrich Dinkelacker (0), Iron Heart (0), J.Press (0), Japan Blue Jeans (0), Jeanerica (0), Jil Sander (0), Jofama (0), John Lobb (0), Journal Standard (0), Kiko Kostadinov (0), Le Chameau (0), Lochcarron of Scotland (0), Ludwig Reiter (0), Mackage (0), Margaret Howell (0), Marithe Francois Girbaud (0), Meermin (0), Montedoro (0), Naked & Famous (0), New & Lingwood (0), Noah (0), Officine Generale (0), OshKosh B'Gosh (0), Paraboot (0), Peregrine (0), Pointer Brand (0) ❓, Post O'Alls (0), Pyrenex (0), Rancourt & Co (0), Reigning Champ (0), Sanders (0), Snow Peak (0), Soulland (0), Stutterheim (0), Tonsure (0), Tretorn (0), Visvim (0), Walker Slater (0), Whyred (0), Zamberlan (0)

### D1 лише жін/дит/аксесуари — 51

Anglo-Italian, Asahi, Bark, Beauty & Youth, Begg x Co, Blundstone, Casey Casey, Corgi, Danefae, Denime, Dents, Emma Willis ❓, Frescobol Carioca, Glenmac, Guidi, Haider Ackermann, Hanna Hats, Harley of Scotland, Hestra, Inis Meain, Joshua Ellis, Jumper 1234, Kinloch Anderson, Krizia Uomo, Lapuan Kankurit, London Tradition, Manebi, Manifattura Ceccarelli, Manufactum, Masnada, Massimo Alba, Murray Allan, N.Peal, Nanga, Pike Brothers, Porter Yoshida & Co, Raleigh Denim ❓, Roberto Verino, Rocky Mountain Featherbed ❓, Samuji, Sandqvist, Sassafras, Stein, Sunnei, Tomorrowland, Tweedmill, Uma Wang, Uniqlo +J, Vanson, White Mountaineering, Zespa

### D2 бренд є, речей 0 — 32

Abraham Moon, Arela, Ben Davis, Blackhorse Lane Ateliers, Buck Mason, De Bonne Facture, Freenote Cloth, Freewheelers, Guy Rover, Hancock, Howlin by Morrison, Kent & Curwen, Kleman, Livid Jeans, Magliano, Matchless, Merz b. Schwanen, Palto, Pherrow's, Red Tornado, Resolute, S.N.S. Herning, Schnayderman's, Sefr, Stan Ray, Sulka, Valstar, Vass, Wallace & Barnes, Wings + Horns, Woolpower, Ziggy Chen

### E1 текст: є згадки — 47

- **100% Linen / Lino / Leinen / Lin**: згадок усього 76895, у моїх розмірах 3828, за 30 днів 77. Приклад: «Чоловіча вишиванка козацька бежева льон s-4xl [None]»
- **100% Silk / Pure Silk / Seta**: згадок усього 56460, у моїх розмірах 659, за 30 днів 66. Приклад: «Базовий светр з шовку та кашеміру [Galeria]»
- **45R**: згадок усього 17, у моїх розмірах 1, за 30 днів 0. Приклад: «Челсі massimo dutti 45r 29 см шкіряні original [Massimo Dutti]»
- **Albini**: згадок усього 6, у моїх розмірах 1, за 30 днів 0. Приклад: «Сорочка чоловіча premium riley slim fit, 100% бавовна albini (італія), розмір l, квітковий принт [RILEY]»
- **Andersen-Andersen**: згадок усього 111, у моїх розмірах 2, за 30 днів 1. Приклад: «Andersen -andersen светр [None]»
- **Andersson Bell**: згадок усього 9, у моїх розмірах 1, за 30 днів 0. Приклад: «Чоловічі кросівки asics andersson bell x gel 1090 'black silver' [Asics]»
- **Balibaris**: згадок усього 56, у моїх розмірах 23, за 30 днів 0. Приклад: «00073 чоловіча вельветова сорочка бренду balibaris [None]»
- **Blue Blue Japan**: згадок усього 18, у моїх розмірах 3, за 30 днів 0. Приклад: «Зіп худі bape a bathing ape x 30th anniversary blue camo made in japan [A Bathing Ape]»
- **Cale**: згадок усього 10, у моїх розмірах 1, за 30 днів 0. Приклад: «Шикарний класичний костюм strellson cale madden marsotto blue wool extra slim fit formal men's suit [Strellson»
- **Cinquanta**: згадок усього 1, у моїх розмірах 1, за 30 днів 0. Приклад: «Теплий чоловічий піджак cinquanta в карту розмір xl [None]»
- **Cmmn Swdn**: згадок усього 1, у моїх розмірах 1, за 30 днів 0. Приклад: «Світшот реглан від шведського бренду cmmn swdn [None]»
- **Doppiaa**: згадок усього 2, у моїх розмірах 1, за 30 днів 0. Приклад: «Брюки штани джинси doppiaa aantioco [None]»
- **Golden Fleece**: згадок усього 3, у моїх розмірах 1, за 30 днів 0. Приклад: «Талія 88 см spiewak golden fleece рідкісні vintage   джинси  size 34 style s212 col tan  made in uk [None]»
- **Hansen Garments**: згадок усього 1, у моїх розмірах 1, за 30 днів 0. Приклад: «Кофта hansen garments зеленого кольору в сіточку легенька розмір хл-ххл [None]»
- **Holland & Sherry**: згадок усього 3, у моїх розмірах 1, за 30 днів 0. Приклад: «Holland & sherry 2 xl [None]»
- **ISTO.**: згадок усього 3, у моїх розмірах 1, за 30 днів 0. Приклад: «Isto світшот чоловічий л/м мінімалізм 🩶 [None]»
- **Irish Linen**: згадок усього 13, у моїх розмірах 1, за 30 днів 0. Приклад: «Hammond x bair mcnudd irish linen піджак чоловічий льон [None]»
- **Jan-Jan Van Essche**: згадок усього 1, у моїх розмірах 1, за 30 днів 0. Приклад: «Дизайнерське пальто jan-jan van essche  шерсть яка нове [Yohji Yamamoto]»
- **Kuro**: згадок усього 27, у моїх розмірах 1, за 30 днів 0. Приклад: «Кросівки чоловічі велосипедні vaude kuro mid stx чорні хакі розмір 45 [Vaude]»
- **La Paz**: згадок усього 8, у моїх розмірах 1, за 30 днів 0. Приклад: «Італійська сорочка поло la paz [None]»
- **Mastai Ferretti**: згадок усього 12, у моїх розмірах 4, за 30 днів 0. Приклад: «Сорочка mastai ferretti [None]»
- **Momotaro Jeans**: згадок усього 2, у моїх розмірах 1, за 30 днів 0. Приклад: «36/36; 36/34; / simon miller / japan denim / momotaro / selvedge jeans / джинси селвідж з японського деніму / »
- **Monitaly**: згадок усього 1, у моїх розмірах 1, за 30 днів 0. Приклад: «Monitaly blazer jacket  чоловічий піджак [None]»
- **N.Hoolywood**: згадок усього 11, у моїх розмірах 7, за 30 днів 0. Приклад: «Чоловічі кросівки new balance 1906r n.hoolywood x invincible gray swan [New Balance]»
- **NPS**: згадок усього 6, у моїх розмірах 1, за 30 днів 0. Приклад: «Кроссовки adidas originals zx flux nps updt [Adidas]»
- **Needles**: згадок усього 209, у моїх розмірах 5, за 30 днів 2. Приклад: «Футболка needles фіолетова з вишивкою [None]»
- **Rota**: згадок усього 6, у моїх розмірах 1, за 30 днів 1. Приклад: «Брюки мужские rota микро вельвет коричневые 52 на 50 [None]»
- **Scott & Charters**: згадок усього 3, у моїх розмірах 1, за 30 днів 0. Приклад: «Светр scott charters 100% вовна мериносів made in scotland оригінал [None]»
- **Sealup**: згадок усього 3, у моїх розмірах 2, за 30 днів 2. Приклад: «Чоловіча куртка-тренч sealup "motorcycle trench" (made in italy) [None]»
- **Solbiati**: згадок усього 2, у моїх розмірах 1, за 30 днів 0. Приклад: «Gino venturini x solbiati linen bespoke теніска [None]»
- **Song for the Mute**: згадок усього 160, у моїх розмірах 55, за 30 днів 4. Приклад: «Чоловічі кросівки adidas adistar cushion x song for the mute mustard brown [Adidas]»
- **Spence Bryson**: згадок усього 2, у моїх розмірах 1, за 30 днів 0. Приклад: «Комір 41 см spence bryson regular fit size 16/41   легка в смужку сорочка  made in britain [None]»
- **Spiewak**: згадок усього 9, у моїх розмірах 6, за 30 днів 0. Приклад: «Талія 88 см spiewak golden fleece рідкісні vintage   джинси  size 34 style s212 col tan  made in uk [None]»
- **Stewart**: згадок усього 108, у моїх розмірах 6, за 30 днів 0. Приклад: «Сорочка lescott stewart [None]»
- **Sunflower**: згадок усього 197, у моїх розмірах 1, за 30 днів 0. Приклад: «Кеди converse chuck 70 high top sunflower [Converse]»
- **Ten C**: згадок усього 2, у моїх розмірах 1, за 30 днів 0. Приклад: «Still by hand japan coat (чоловіча куртка пальто японія ten c) [None]»
- **Tessuto Loro Piana**: згадок усього 7693, у моїх розмірах 2622, за 30 днів 96. Приклад: «Чоловіча сорочка, темно-синій колір, loro piana, розмір xl [Loro Piana]»
- **Thomas Mason**: згадок усього 8, у моїх розмірах 3, за 30 днів 0. Приклад: «Сорочка у полоску hackett london x thomas mason класична полосата [Hackett]»
- **Todd Snyder**: згадок усього 2, у моїх розмірах 1, за 30 днів 0. Приклад: «Мужской свитшот champion x todd snyder, размер l [Champion]»
- **Tundra**: згадок усього 291, у моїх розмірах 12, за 30 днів 0. Приклад: «5.11 tactical aggressor tundra тактическая куртка дождевик ветровка треккинговая горная туристична трекінгова »
- **Urban Research**: згадок усього 8, у моїх розмірах 3, за 30 днів 0. Приклад: «Urban research doors linen navy blue short sleeve shirt [smh016764] [Eton]»
- **Velva Sheen**: згадок усього 1, у моїх розмірах 1, за 30 днів 0. Приклад: «Walt disney by velva sheen вінтажна футболка [American Vintage]»
- **Ventile**: згадок усього 2, у моїх розмірах 2, за 30 днів 2. Приклад: «Вінтажна чоловіча куртка stone island ventile 3/1 ss 2007 l чорна [Stone Island]»
- **Wales Bonner**: згадок усього 645, у моїх розмірах 46, за 30 днів 4. Приклад: «Adidas originals × wales bonner. кросівки  під замовлення, в двох кольорах [Adidas]»
- **Woolmark**: згадок усього 1070, у моїх розмірах 114, за 30 днів 13. Приклад: «Стильні нарядні штани брюки woolmark.34.л [None]»
- **Workers K&T H MFG**: згадок усього 15, у моїх розмірах 3, за 30 днів 1. Приклад: «Кофта чоловіча lron workers [None]»
- **Yanko**: згадок усього 10, у моїх розмірах 1, за 30 днів 0. Приклад: «Броги чоловічі paul smith count чорні туфлі оксфорди дербі шкіряні взуття італія оригінал 45-46 р/31 см       »

### E2 текст: нічого — 167

18 East, 3sixteen, A.Presse, Aero Leather, Alex Mill, Arnys, Arpenteur, Arts & Science, Astorflex, Baird McNutt, Barns Outfitters, Batoner, Battenwear, Big Mac, Bills Khakis, Blurhms, Braemar, Bronson Mfg., Budd, Burgus Plus, Buzz Rickson's, CQP, Camber USA, Camiel Fortgens, Campbell's of Beauly, Charvet, Ciota, Clan Douglas, Commas, Community Clothing, Comoli, Connolly, Crepuscule, Crescent Down Works, Croix, Cushman, Danton, De Petrillo, Dry Bones, Edifice, Edward Green, Endless Joy, European Flax, FOB Factory, Faherty, Feathered Friends, Forme d'Expression, Fox Brothers, Frahm, Full Count, Gaziano & Girling, Graph Zero, Graphpaper, Guernsey Woollens, Heimat Textil, Hender Scheme, Herill, Hevo, Hilditch & Key, Hiut Denim, Hogg of Hawick, House of Blanks, Husbands Paris, Inverallan, Jamieson & Smith, Jamieson's of Shetland, Jelado, Kaptain Sunshine, Kardo, Kato, Kerry Woollen Mills, Kilgour, Koio, Kojima Genes, Kolor, L.C. King, Label Under Construction, Laurence J. Smith, Le Laboureur, Le Minor, Le Tricoteur, Left Field NYC, Libeco, LinenMe, Loopwheeler, Lovat Mill, MHL., MagicLinen, Markaware, Masters of Linen, McGeorge of Scotland, Mfpen, Nano Universe, Nepenthes, Nicholas Daley, Nicks Boots, Nokian Footwear, Nonnative, Norwegian Rain, OAMC, Oak Street Bootmakers, Old Town, Oliver Church, Omnigod, Oni Denim, Ooe Yofukuten, Orcival, Ordinary Fits, Orslow, Padmore & Barnes, Pantherella, Phigvel, Porter Classic, Private White V.C., Pure Blue Japan, Quoddy, Railcar Fine Goods, Real Japan Blues, Reproduction of Found, Ring Jacket, Rogue Territory, Russell Moccasin, SEH Kelly, Sage Nation, Sartoria Partenopea, Scye, Seraphin, Shetland Woollen Co, Ships, Shoes Like Pottery, Skull Jeans, Somet, South2 West8, Spalwart, Spellbound, Steven Alan, Stevenson Overall Co, Story mfg., Strike Gold, Studio D'Artisan, Studious, Sugar Cane, Sunsea, TCB Jeans, TLB Mallorca, Takahiromiyashita The Soloist, Tanuki, Taylor Stitch, Teatora, Tellason, The Flat Head, The Real McCoy's, Toogood, Toys McCoy, Trophy Clothing, UES, United Arrows, Vetra, Viberg, Wacko Maria, Wesco, West End Knitwear, White's Boots, Y's for men, Yaeca, Yoke, Yuketen

### S саб-лейбл — 27

- **The North Face Purple Label** → батьківський id [3926], фраза `purple label|nanamica`; текстовий пошук: усього 1, у моїх розмірах 0, за 30 днів 0
- **Arc'teryx Veilance** → батьківський id [45282], фраза `veilance`; текстовий пошук: усього 2, у моїх розмірах 2, за 30 днів 0
- **Polo Country** → батьківський id [143, 47965], фраза `polo country`; текстовий пошук: усього 4, у моїх розмірах 1, за 30 днів 0
- **RRL** → батьківський id [143, 47965], фраза `\brrl\b|double rl`; текстовий пошук: усього 8, у моїх розмірах 2, за 30 днів 0
- **Ralph Lauren Purple Label** → батьківський id [143, 47965], фраза `purple label`; текстовий пошук: усього 16, у моїх розмірах 4, за 30 днів 0
- **Rugby Ralph Lauren** → батьківський id [143, 47965], фраза `\brugby\b`; текстовий пошук: усього 50, у моїх розмірах 27, за 30 днів 19
- **Calvin Klein Collection** → батьківський id [197], фраза `calvin klein collection|ck collection`; текстовий пошук: усього 17, у моїх розмірах 1, за 30 днів 0
- **New Balance Made in UK** → батьківський id [385], фраза `made in (uk|england)|\b(991|1500|576)\b|англі`; текстовий пошук: усього 39, у моїх розмірах 2, за 30 днів 0
- **New Balance Made in USA** → батьківський id [385], фраза `made in usa|\b99[0-3]\b|сша`; текстовий пошук: усього 111, у моїх розмірах 29, за 30 днів 4
- **Levi's Made & Crafted** → батьківський id [82], фраза `made\s*(&|and)\s*crafted|\blmc\b`; текстовий пошук: усього 41, у моїх розмірах 6, за 30 днів 2
- **Levi's Vintage Clothing** → батьківський id [82], фраза `\blvc\b|vintage clothing|big\s*e\b|501xx`; текстовий пошук: усього 16, у моїх розмірах 3, за 30 днів 0
- **Wrangler Blue Bell** → батьківський id [176], фраза `blue bell|broken twill|124mj`; текстовий пошук: усього 1, у моїх розмірах 1, за 30 днів 0
- **Champion Reverse Weave** → батьківський id [4982], фраза `reverse weave`; текстовий пошук: усього 37, у моїх розмірах 8, за 30 днів 2
- **Uniqlo U** → батьківський id [386], фраза `uniqlo\s*u\b|lemaire|christophe`; текстовий пошук: усього 368, у моїх розмірах 48, за 30 днів 5
- **Clarks Originals** → батьківський id [746], фраза `desert|wallabee|originals`; текстовий пошук: усього 50, у моїх розмірах 3, за 30 днів 1
- **Lee 101** → батьківський id [83], фраза `\b101\b|rider`; текстовий пошук: усього 17, у моїх розмірах 1, за 30 днів 0
- **Dr. Martens Made in England** → батьківський id [557], фраза `made in england|vintage|англі`; текстовий пошук: усього 34, у моїх розмірах 2, за 30 днів 1
- **Descente Allterrain** → батьківський id [54096], фраза `allterrain|mizusawa`; текстовий пошук: усього 1, у моїх розмірах 0, за 30 днів 0
- **Comme des Garcons Homme** → батьківський id [44406], фраза `homme`; текстовий пошук: усього 1, у моїх розмірах 0, за 30 днів 0
- **Comme des Garcons Homme Plus** → батьківський id [44406], фраза `homme plus|homme\s*\+`; текстовий пошук: усього 1, у моїх розмірах 0, за 30 днів 0
- **Comme des Garcons Shirt** → батьківський id [44406], фраза `shirt`; текстовий пошук: усього 11, у моїх розмірах 5, за 30 днів 0
- **Diadora Heritage** → батьківський id [2738], фраза `heritage|made in italy`; текстовий пошук: усього 15, у моїх розмірах 1, за 30 днів 0
- **Homme Plisse Issey Miyake** → батьківський id [11671], фраза `homme pliss|plisse|плісе`; текстовий пошук: усього 1, у моїх розмірах 0, за 30 днів 0
- **Issey Miyake Men** → батьківський id [11671], фраза `men|homme`; текстовий пошук: усього 1, у моїх розмірах 0, за 30 днів 0
- **Schiesser Revival** → батьківський id [46233], фраза `revival`; текстовий пошук: усього 0, у моїх розмірах 0, за 30 днів 0
- **Beams Plus** → батьківський id [50312], фраза `beams\s*\+|beams plus`; текстовий пошук: усього 0, у моїх розмірах 0, за 30 днів 0
- **Wolverine 1000 Mile** → батьківський id [46067], фраза `1000`; текстовий пошук: усього 2, у моїх розмірах 0, за 30 днів 0

## Що з'ясувалося

- **Кількість запитів залежить від кількості груп, а не брендів.** Один запит бере до 100 брендів, тож рідкісний бренд «коштує» стільки ж, скільки частий: 1/100 запиту. ~620 брендів з id = 7 запитів на прохід без пакетів. Пакети з різною частотою дають ~2,5 запиту на прохід (−60 %), а аліаси GraphQL дозволяють відправити всі запити проходу одним HTTP-запитом.
- **Справжнє вузьке місце — шум і картки товарів.** Пакети A+B+C1 у моїх розмірах дають ~6 000 нових речей на місяць (~200 на добу), з них 5 000 — 42 гарячі бренди. Кожна нова річ, що пройшла швидкі фільтри, — ще один запит картки й одне повідомлення. Без категорій з твоїх нотаток це ~200 повідомлень на добу.
- **Перекупники/репліки.** Серед 100 найновіших Stone Island у моїх розмірах — десятки однакових «нових» рожевих світшотів S–XL за 2 360 грн від одного продавця (звідси 196 речей за добу). Потрібен фільтр: мультирозмірні оголошення («s-xl», «s, m, l, xl», «від s до»), «нові з бирками» для брендів, які ти береш вживаними, дублікати назв.
- **`filterBrand` знаходить не все:** Didriksons, Henrik Vibskov, Mey&Edlich, Marithé + François Girbaud, Bonne Gueule, Denime, Camper Lab він не повернув, хоча бренди є (відновлено з текстового пошуку). Решта «відсутніх» перевірена текстом.
- **Аксесуари поза чоловічим розділом:** рукавички, сумки, шарфи, краватки (Hestra, Dents, Sandqvist, Begg x Co, Tweedmill…) у розділі `men` майже не трапляються й не мають розмірів L/XL, тому потрапили в «лише жін/дит/аксесуари». Під твій профіль (одяг L/XL, штани, взуття) вони не підпадають.
- **Саб-лейбли масових брендів** (RL Purple Label, RRL, NB Made in USA/UK, LVC, Uniqlo U, Champion Reverse Weave…) окремого бренду на Shafa не мають. Ловимо через батьківський бренд (він і так у гарячих) + фразу в назві. Фраза в назві трапляється рідко (RRL — 2 речі в моїх розмірах).
- **Мітки тканин** (льон, шовк, Loro Piana як тканина, Woolmark) — це пошуки без бренду. «Льон» у моїх розмірах: 3 828 речей, ≥77 за 30 днів; «шовк»: 659, ≥66 за 30 днів. Потрібні категорії, інакше шум (білизна, вишиванки).
