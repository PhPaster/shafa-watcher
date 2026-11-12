"""Завантаження brands.yaml, групування правил у запити й локальні фільтри.

Модель (Біблія, розділ 10):
- `my_sizes` — профіль розмірів (одяг / штани / взуття), один на всі бренди, іде в запит як серверний фільтр.
- бренд має список `categories` (людські назви → slug-и), вони фільтруються локально за `catalogSlug` товару
  й не розбивають групу запитів;
- `searches` усередині бренду — кілька окремих правил для одного бренду (інший розмір, своя ціна…);
- `searches` на верхньому рівні — пошуки без бренду (наприклад, «вовняні светри»).

Правила з однаковими серверними фільтрами (розділ, розміри, стан, ціна, матеріал) йдуть одним запитом.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import yaml

# Стани на Shafa (id з filterConditions): 1 Новий, 2 Ідеальний, 3 Дуже хороший, 4 Хороший, 5 Задовільний.
CONDITIONS = {1: "Новий", 2: "Ідеальний", 3: "Дуже хороший", 4: "Хороший", 5: "Задовільний"}

# ---------------------------------------------------------------------------------------------
# Розміри чоловічого розділу: id фільтра (перевірено filterSizes 9.11.2026 для men, shtany-i-shorty, obuv).
# Id у фільтрі й id розміру в самому товарі — різні простори; фільтруємо лише на сервері.
SIZE_IDS: dict[str, dict[str, dict[str, list[int]]]] = {
    "men": {
        "одяг": {
            "XS": [147], "S": [148], "M": [149], "L": [150], "XL": [151], "XXL": [152], "3XL": [153],
            "4XL": [154], "5XL": [155], "6XL": [156], "7XL": [247, 514, 515], "8XL": [516, 517],
            "ONE SIZE": [157],
        },
        "штани": {
            "W28": [159], "W29": [160], "W30": [161], "W31": [162], "W32": [163], "W33": [164], "W34": [165],
            "W36": [166], "W38": [167], "W40": [168, 314], "W42": [169], "W44": [249], "W46": [250],
            "W48": [251], "W50": [252], "ONE SIZE": [313],
        },
        "взуття": {
            "36": [171], "37": [172], "38": [173], "38.5": [238], "39": [174], "39.5": [239], "40": [175],
            "40.5": [240], "41": [176], "41.5": [241], "42": [177], "42.5": [242], "43": [178], "43.5": [243],
            "44": [179], "44.5": [244], "45": [180], "45.5": [245], "46": [181], "46.5": [1338], "47": [182],
            "47.5": [246], "48": [183], "49": [184], "50": [1340], "ONE SIZE": [185],
        },
    },
}
# Європейські номери одягу (L/48) як синоніми літер.
_CLOTHES_EU = {"42": "XS", "44": "S", "46": "M", "48": "L", "50": "XL", "52": "XXL", "54": "3XL", "56": "4XL",
               "58": "5XL", "60": "6XL"}
# 12.11.2026: літерні розміри в самому оголошенні («M, L», «38 / M / 46», «L-XL»). Якщо серед них є хоч один
# не з профілю одягу (M поруч з L, XXL поруч з XL) — річ не надсилаємо: сервер пропускає її за L, а сидить вона як M.
_LETTER_NORM = {"XXXL": "3XL", "2XL": "XXL", "XXXXL": "4XL", "XXXS": "3XS", "2XS": "XXS"}
_LETTERS = {"3XS", "XXS", "XS", "S", "M", "L", "XL", "XXL", "3XL", "4XL", "5XL", "6XL", "7XL", "8XL"}
_SIZE_SPLIT = re.compile(r"[\s/,\-–—|]+")


def letter_sizes(names) -> list[str]:
    """Літери розмірів з назв розмірів товару: [«M», «L»] → [M, L]; «40 / L / 48» → [L]; «L-XL» → [L, XL]."""
    out = []
    for n in names or []:
        for t in _SIZE_SPLIT.split(str(n).upper()):
            t = _LETTER_NORM.get(t, t)
            if t in _LETTERS and t not in out:
                out.append(t)
    return out


SIZE_GROUP_ALIASES = {"одяг": "одяг", "clothes": "одяг", "штани": "штани", "pants": "штани",
                      "взуття": "взуття", "shoes": "взуття"}

# ---------------------------------------------------------------------------------------------
# Категорії чоловічого розділу: людська назва → slug-и `catalogSlug` товару (усі перевірено на живому API 9.11.2026).
# `x/*` = усе всередині x. Увага: частина «Кофт» має префікс `kofty/` (а `kofty` як розділ — жіночий!).
CATEGORIES: dict[str, dict[str, list[str]]] = {
    "men": {
        # Тактичний розділ (11.11.2026): продавці кладуть туди трекінгові черевики, карго й штани G-1000
        # (Lowa Renegade, Salomon, Fjällräven) — без нього такі речі відсіювались категорією.
        "джинси": ["shtany-i-shorty/dzhinsy"],
        # Спорт і відпочинок (12.11.2026): трекінгові/лижні штани, фліски, лижні куртки аутдор-брендів — лише
        # локальний фільтр брендів, як тактичний розділ (серверний catalogSlug пошуків без бренду не змінюється).
        "штани": ["shtany-i-shorty/bryuki", "shtany-i-shorty/dzhinsy", "takticheskaya-odezhda/shtany",
                  "sport-i-otdyh/sportivnyye-shtany", "sport-i-otdyh/gornolyzhnaya-odezhda/shtany"],
        "брюки": ["shtany-i-shorty/bryuki", "takticheskaya-odezhda/shtany", "sport-i-otdyh/sportivnyye-shtany",
                  "sport-i-otdyh/gornolyzhnaya-odezhda/shtany"],
        "шорти": ["shtany-i-shorty/shorty", "shtany-i-shorty/bridzhi"],
        "штани й шорти": ["shtany-i-shorty/*", "takticheskaya-odezhda/shtany", "sport-i-otdyh/sportivnyye-shtany",
                          "sport-i-otdyh/gornolyzhnaya-odezhda/shtany"],
        "футболки": ["futbolki-i-maiki/futbolki", "futbolki-i-maiki/polo"],
        "поло": ["futbolki-i-maiki/polo"],
        "майки": ["futbolki-i-maiki/maiki"],
        "сорочки": ["rubashki/rubashki"],
        "теніски": ["rubashki/tenniski"],
        "вишиванки": ["rubashki/vyshivanki"],
        # «Светри» = увесь розділ «Кофти» (як фільтр сайту за тканиною: продавці кладуть светри й у «Кофти»,
        # «Гольфи», «Світшоти»). Разом із category_materials.светри (лише вовна…) це «вовняне з розділу Кофти»
        # (рішення 10.11.2026). Строгий старий список — «светри вузько».
        "светри": ["kofti/*", "kofty/*"],
        "светри вузько": ["kofti/svitery", "kofti/dzhempery", "kofti/pulovery", "kofti/kardigany"],
        "кардигани": ["kofti/kardigany"],
        "худі": ["kofti/hudi", "kofti/svitshoty", "kofty/tolstovki"],
        "світшоти": ["kofti/hudi", "kofti/svitshoty", "kofty/tolstovki"],
        "лонгсліви": ["kofty/longsliv"],
        "олімпійки": ["kofty/olimpiiki"],
        "гольфи": ["kofty/golfy"],
        "кофти": ["kofti/*", "kofty/*", "sport-i-otdyh/sportivnyye-kofty"],
        "верхній одяг": ["verkhniaia-odezhda/*", "takticheskaya-odezhda/verhnyaya",
                         "sport-i-otdyh/gornolyzhnaya-odezhda/kurtki"],
        "куртки": ["verkhniaia-odezhda/kurtki", "verkhniaia-odezhda/vetrovki", "takticheskaya-odezhda/verhnyaya",
                   "sport-i-otdyh/gornolyzhnaya-odezhda/kurtki"],
        "пуховики": ["verkhniaia-odezhda/pukhoviki"],
        "пальто": ["verkhniaia-odezhda/palto"],
        "парки": ["verkhniaia-odezhda/parki"],
        "жилетки": ["verkhniaia-odezhda/zhiletki", "pidzhaki-i-kostiumy/zhiletki"],
        "дублянки": ["verkhniaia-odezhda/dublenki-i-shuby"],
        "піджаки": ["pidzhaki-i-kostiumy/pidzhaki", "pidzhaki-i-kostiumy/zhakety"],
        # 12.11.2026: костюмні жилети й смокінги (пошук «Піджаки з натуральних тканин» отримував їх, але відсіював)
        "костюми": ["pidzhaki-i-kostiumy/delovye-kostiumy", "pidzhaki-i-kostiumy/zhiletki",
                    "pidzhaki-i-kostiumy/smokingi"],
        "термобілизна": ["nizhnee-bele/termobele"],
        "спецодяг": ["specodezhda-men/*"],
        "взуття": ["obuv/*", "takticheskaya-odezhda/obuv"],
        "кросівки": ["obuv/krossovki", "obuv/kedy"],
        "кеди": ["obuv/kedy"],
        "черевики": ["obuv/botinki", "obuv/sapogi", "takticheskaya-odezhda/obuv"],
        "туфлі": ["obuv/tufli"],
        "мокасини": ["obuv/mokasiny"],
        "сандалі": ["obuv/sandali"],
        "спорт": ["sport-i-otdyh/*"],
        "піжами": ["odezhda-dlia-doma-i-sna/pizhamy"],
        "одяг для дому": ["odezhda-dlia-doma-i-sna/*"],
    },
}
# Верхній рівень slug-а, який можна передати в запит як catalogSlug (лише чоловічі, перевірено за URL товарів).
# `kofty/*` у чоловічому розділі лежать під `kofti`; сам `kofty` — жіночий розділ, у запит його не передаємо.
MEN_SERVER_PARENTS = {"kofti": "kofti", "kofty": "kofti", "obuv": "obuv", "futbolki-i-maiki": "futbolki-i-maiki",
                      "rubashki": "rubashki", "shtany-i-shorty": "shtany-i-shorty",
                      "verkhniaia-odezhda": "verkhniaia-odezhda", "pidzhaki-i-kostiumy": "pidzhaki-i-kostiumy",
                      "sport-i-otdyh": "sport-i-otdyh", "odezhda-dlia-doma-i-sna": "odezhda-dlia-doma-i-sna",
                      "nizhnee-bele": "nizhnee-bele"}

TACTICAL = "takticheskaya-odezhda/"
# Слаги, які додано до категорій лише як локальний фільтр брендів: серверний catalogSlug пошуків без бренду
# вони не розширюють (інакше «Вовняні брюки» перейшли б на весь розділ men, а ключ групи змінився б).
LOCAL_ONLY = ("takticheskaya-odezhda/", "sport-i-otdyh/sportivnyye-shtany", "sport-i-otdyh/gornolyzhnaya-odezhda/",
              "sport-i-otdyh/sportivnyye-kofty")

FILTER_KEYS = ("section", "sizes", "categories", "min_condition", "max_price", "min_price", "materials",
               "materials_include", "materials_exclude", "keywords_exclude", "max_age_hours",
               "package", "title_include", "text", "reseller_filter", "seller",
               "also_categories", "title_in_description", "material_rules", "characteristics",
               "title_prefer", "min_share", "genuine_only")
DEFAULT_PACKAGE = "звичайні"
# Продавець — характеристика 1757 «Продавець» (однакова в усіх категоріях, перевірено 9.11.2026):
# 10290 «Приватний», 10291 «Бізнес та інші». «Бізнес та інші» — це й магазини (нові репліки «s-xxl»), і люди,
# що не вказали статус (вживані речі). Тому за замовчуванням private_new: нові — лише від приватних, вживані — від усіх.
SELLER_PRIVATE = 10290
SELLER_MODES = {
    "private_new": "нові — лише від приватних осіб, вживані — від усіх",
    "private": "лише приватні особи (і нові, і вживані)",
    "any": "усі продавці",
}
# Перекупники/репліки: мультирозмірні оголошення нового товару («s-xl», «s, m, l, xl», «розміри від s до xl»),
# репліки й опт. «l-xl» (одна річ на межі розмірів) — не перекупник.
RESELLER_RX = re.compile(
    r"\b(xxs|xs|s|m|с|м)\s*[-–—/]\s*(xl|xxl|[2-5]xl|хл|ххл)\b"
    r"|\b(xs|s|m|l|с|м|л)\s*,\s*(s|m|l|xl|м|л|хл)\s*,\s*(m|l|xl|xxl|л|хл|ххл)\b"
    r"|розмір\w*\s+від\s+\S+\s+до|в\s+наявності\s+(всі\s+|усі\s+)?розмір|\b(всі|усі)\s+розміри"
    r"|реплік|\bкопі[яю]\b|\breplica\b|\b1\s*:\s*1\b|люкс\s*як|\blux\b|\bопт\b|оптом|дропшип|під\s+замовлення",
    re.I)
# Назви матеріалів → id для «Кофт і светрів» (`tools/lookup.py materials kofti`). Увага: в інших категоріях
# id інші (сорочки: льон 1712, шовк 1725; штани: льон 1967, шовк 1979) — там вказуй числом.
MATERIAL_IDS = {"бавовна": 1243, "вовна": 1245, "кашемір": 1225, "льон": 1230, "шовк": 1244,
                "штучний шовк": 1224, "акрил": 1206, "альпака": 2252, "ангора": 2266}


# Матеріали для правил за категоріями: шукаються в назві, описі й полі «Матеріал» (uk / ru / en).
# (include, exclude): exclude скасовує збіг («штучна шкіра» — не шкіра), якщо поруч немає «натуральна».
MATERIALS: dict[str, tuple[str, str | None]] = {
    "вовна": (r"(?<!ба)вовн|шерст|\bwool|merino|мер[іи]но|lambswool|ламбсвул|shetland|шетланд", None),
    "кашемір": (r"кашем[іи]р|cashmere", None),
    "альпака": (r"альпак|alpaca", None),
    "ангора": (r"ангор|angora", None),
    "мохер": (r"мохер|mohair", None),
    "верблюжа вовна": (r"верблюж|camel\s*hair", None),
    "шовк": (r"шовк|ш[её]лк|\bsilk|\bseta\b", None),
    "льон": (r"льон|льну|лля[нн]|льнян|\bлен\b|\bльна\b|linen|\blino\b|leinen", None),
    "бавовна": (r"бавовн|коттон|котон|хлоп(ок|ка|ко)|cotton", None),
    "шкіра": (r"шкір|кожа|кожі|кожан|leather|\bpelle\b|\bleder\b",
              r"штучн\w*\s+(шкір|кож)|еко\s*-?\s*(шкір|кож)|екошкір|экокож|кожзам|шкірзам|дерматин|"
              r"искусствен\w*\s+кож|faux\s+leather|\bpu\b|vegan\s+leather|кожвініл|"
              r"п[іо]д\s+(шкір|кож)|імітац\w*\s+(шкір|кож)|имитац\w*\s+кож"),
    "замша": (r"замш|suede", r"штучн\w*\s+замш|еко\s*-?\s*замш|искусствен\w*\s+замш|faux\s+suede|"
                        r"п[іо]д\s+замш|імітац\w*\s+замш|имитац\w*\s+замш|мікрозамш|микрозамш"),
    "нубук": (r"нубук|nubuck", None),
    "акрил": (r"акрил|acrylic", None),
    "поліестер": (r"поліест|полиэст|polyester", None),
}
# Частка вовни в складі (11.11.2026): «76% бавовна 7% вовна», «вовна 60%», «вовняний (60%)». Вовноподібні волокна
# сумуються; якщо відсотки вказано лише для інших волокон — вовни не більше за 100 − їхня сума.
WOOL_FIBERS = {"вовна", "кашемір", "альпака", "ангора", "мохер", "верблюжа вовна"}
NATURAL_FIBERS = WOOL_FIBERS | {"шовк", "льон"}   # для правил з min_share: брюки, піджаки, пальта
# Частка в category_materials (светри, шапки): вовноподібні + шовк (12.11.2026: «55% шовк, 45% кашемір» — не відсів).
KNIT_FIBERS = WOOL_FIBERS | {"шовк"}
_OTHER_FIBERS = {
    "нейлон": r"нейлон|поліамід|полиамид|nylon|polyamid",
    "віскоза": r"віскоз|вискоз|viscose|\brayon",
    "еластан": r"еластан|эластан|elastan|спандекс|spandex|лайкр|lycra",
    "модал": r"\bмодал|\bmodal",
}
_PCT = re.compile(r"(?<![\d.,])(\d{1,3}(?:[.,]\d+)?)\s*%")   # «67.9% Wool» = 68, не 9 (12.11.2026)


def _fiber_near(fragment: str, from_end: bool) -> tuple[int, str] | None:
    """Найближче до відсотка волокно у фрагменті: (відстань у символах, назва)."""
    pats = {**{k: v[0] for k, v in MATERIALS.items()}, **_OTHER_FIBERS}
    best = None
    for name, rx in pats.items():
        for m in re.finditer(rx, fragment, re.I):
            end = m.end()
            while end < len(fragment) and fragment[end].isalpha():   # «вовн|а» — рахувати від кінця слова
                end += 1
            dist = len(fragment) - end if from_end else m.start()
            if best is None or dist < best[0]:
                best = (dist, name)
    return best


def wool_share(text: str, fibers: set[str] = WOOL_FIBERS) -> int | None:
    """Відсоток волокон `fibers` (за замовчуванням вовноподібних) за складом у тексті; None — складу з відсотками немає.
    Напрям («76% бавовна» чи «бавовна 76%») визначається за першим відсотком і діє для всього тексту."""
    text = text or ""
    pairs = []
    for m in _PCT.finditer(text):
        pct = round(float(m.group(1).replace(",", ".")))
        if not 0 < pct <= 100:
            continue
        after = re.split(r"[\d%]", text[m.end():m.end() + 25], maxsplit=1)[0]
        before = re.split(r"[\d%]", text[max(0, m.start() - 25):m.start()][::-1], maxsplit=1)[0][::-1]
        pairs.append((pct, _fiber_near(after, False), _fiber_near(before, True)))
    direction = None
    for _, a, b in pairs:
        if a or b:
            direction = "after" if a and (not b or a[0] <= b[0]) else "before"
            break
    if not direction:
        return None
    found: dict[str, int] = {}
    for pct, a, b in pairs:
        hit = (a or b) if direction == "after" else (b or a)
        if hit:
            found[hit[1]] = max(found.get(hit[1], 0), pct)   # назва й опис часто повторюють склад
    wanted = sum(v for k, v in found.items() if k in fibers)
    if wanted:
        return min(wanted, 100)
    return max(0, 100 - sum(found.values()))


_GENUINE = re.compile(r"натуральн\w*\s+(шкір|кож|замш)|genuine\s+leather|real\s+leather|full\s*grain", re.I)
# Штучна шкіра/замша в назві чи описі (для пошуків шкіри без бренду: поле «Матеріал» продавці ставлять і «під замшу»).
# Без «PU»: у взутті це зазвичай підошва.
FAUX_RX = re.compile(r"штучн\w*\s+(шкір|кож|замш)|искусствен\w*\s+(кож|замш)|еко\s*-?\s*(шкір|кож|замш)|екошкір|"
                     r"экокож|кожзам|шкірзам|дерматин|faux\s+(leather|suede)|vegan\s+leather|кожвініл|"
                     r"п[іо]д\s+(шкір|кож|замш)|імітац\w*\s+(шкір|кож|замш)|имитац\w*\s+(кож|замш)|мікрозамш|микрозамш",
                     re.I)


def faux_leather(text: str) -> bool:
    return bool(FAUX_RX.search(text or "")) and not _GENUINE.search(text or "")


def detect_materials(text: str) -> set[str]:
    found = set()
    genuine = bool(_GENUINE.search(text))
    for name, (inc, exc) in MATERIALS.items():
        if re.search(inc, text, re.I):
            if exc and re.search(exc, text, re.I) and not genuine:
                continue
            found.add(name)
    return found


def resolve_material_names(values, where: str) -> list[str]:
    out = []
    for v in values or []:
        key = str(v).strip().lower()
        if key not in MATERIALS:
            raise ConfigError(f"{where}: невідомий матеріал «{v}». Відомі: {', '.join(MATERIALS)}")
        out.append(key)
    return list(dict.fromkeys(out))


@dataclass
class CategoryMaterials:
    """Правило матеріалів для категорії (для всіх брендів і пошуків).
    only — річ проходить, лише якщо знайдено хоч один із цих матеріалів;
    prefer — нічого не відсіює: збіг приходить зі ⭐ і звуком, решта — тихо."""
    category: str
    patterns: list[str]
    only: list[str] = field(default_factory=list)
    prefer: list[str] = field(default_factory=list)
    if_unknown: str = "skip"      # only + матеріал не вказано: skip — відсіяти, send — надіслати
    except_patterns: list[str] = field(default_factory=list)   # except: [худі] — ці підкатегорії без правила
    min_share: int | None = None   # мінімальний % вовноподібних волокон, якщо склад указано відсотками

CATEGORY_MATERIAL_KEYS = {"only", "prefer", "if_unknown", "except", "min_share"}


def _cm_applies(c: CategoryMaterials, slug: str | None, rule: "Rule | None", constrained: set[str]) -> bool:
    """Чи діє правило матеріалів категорії на цю річ у цьому правилі бренду.
    Не діє, якщо: підкатегорія в except; правило вимкнуло материали (material_rules: false);
    правило бренду пускає цю підкатегорію ще й через іншу назву без обмежень матеріалу
    (Patagonia [кофти]: фліс із «Кофт» приходить, хоча «светри» — лише вовна; [светри, худі]: худі — будь-які)."""
    if not category_ok(slug, c.patterns):
        return False
    if c.except_patterns and category_ok(slug, c.except_patterns):
        return False
    if rule is None:
        return True
    if not rule.material_rules:
        return False
    if c.only:   # пріоритет (prefer) лишається для всіх; обмеження only — ні
        for name, pats in rule.category_map.items():
            if name != c.category and name not in constrained and category_ok(slug, pats):
                return False
    return True


def material_check(item: dict, details: dict | None, cms: list[CategoryMaterials], rule: "Rule | None" = None) \
        -> tuple[str | None, bool | None, list[str]]:
    """→ (причина відсіву або None, пріоритет: True/False/None якщо правила prefer немає, знайдені матеріали)."""
    slug = item.get("catalogSlug")
    constrained = {c.category for c in cms if c.only}
    matched = [c for c in cms if _cm_applies(c, slug, rule, constrained)]
    text = material_text(details, item)
    found = sorted(detect_materials(text))
    if rule is not None and rule.min_share:      # правило: натуральних волокон у складі (відсотками) не менше N %
        share = wool_share(text, NATURAL_FIBERS)
        if share is not None and share < rule.min_share:
            return f"натуральних волокон у складі {share}% (треба від {rule.min_share}%)", None, found
    if not matched:
        return None, None, found
    only = {m for c in matched for m in c.only}
    prefer = {m for c in matched for m in c.prefer}
    need = max((c.min_share or 0) for c in matched)
    if need:
        share = wool_share(text, KNIT_FIBERS)
        if share is not None and share < need:
            return f"вовни й шовку в складі {share}% (треба від {need}%)", None, found
    if only and not (set(found) & only):
        if not found and all(c.if_unknown == "send" for c in matched if c.only):
            return None, False, found          # матеріал не вказано → надіслати тихо (11.11.2026)
        elif not found:
            return f"матеріал не вказано (треба: {', '.join(sorted(only))})", None, found
        else:
            return f"матеріал {', '.join(found)} (треба: {', '.join(sorted(only))})", None, found
    priority = bool(set(found) & prefer) if prefer else None
    return None, priority, found

@dataclass
class Rule:
    label: str                           # назва для логів і алертів: «COS», «Visvim #2», «Вовняні светри»
    brands: dict[int, str] = field(default_factory=dict)   # id → назва; порожньо = пошук без бренду
    enabled: bool = True
    section: str | None = "men"          # catalogSlug розділу: men, women, kids … None = усі розділи
    sizes: list[int] = field(default_factory=list)          # id фільтра розмірів (з профілю)
    categories: list[str] = field(default_factory=list)     # slug-и або `slug/*`; порожньо = усі категорії
    min_condition: int | None = None
    max_price: int | None = None
    min_price: int | None = None
    materials: list[int] = field(default_factory=list)      # id матеріалів (серверний фільтр, поле продавця)
    materials_include: str | None = None  # regex по назві + опису + полю «Матеріал»
    materials_exclude: str | None = None
    keywords_exclude: str | None = None   # regex по назві
    max_age_hours: float | None = None    # ігнорувати «підняті» старі оголошення
    package: str = DEFAULT_PACKAGE        # пакет частоти опитування (settings.packages)
    title_include: str | None = None      # regex по назві (дешево, без картки): саб-лейбли «rrl|double rl»
    text: str | None = None               # серверний текстовий пошук (для брендів, яких на Shafa немає)
    reseller_filter: bool = True          # відсіювати мультирозмірні «нові» оголошення, репліки, опт
    seller: str = "any"                   # SELLER_MODES: private_new | private | any (серверний фільтр)
    category_map: dict[str, list[str]] = field(default_factory=dict)  # назва категорії правила → slug-и
    title_in_description: bool = False    # title_include шукати ще й в описі (потрібна картка): «Uniqlo U»
    material_rules: bool = True           # false — category_materials (лише/пріоритет) не діють: Asics
    min_share: int | None = None          # мінімальний % натуральних волокон (вовна, кашемір, шовк, льон…), якщо склад указано
    title_prefer: str | None = None       # regex по назві + опису: збіг — ⭐ і звук, інакше тихо (вовняні светри без бренду)
    genuine_only: bool = False            # відсіяти, якщо в назві чи описі «штучна шкіра», «під замшу» (пошуки шкіри)
    characteristics: list[int] = field(default_factory=list)  # інші характеристики (серверний фільтр, І з матеріалом):
                                                               # «Стать: для чоловіків» шапок 2418
    size_letters: frozenset = frozenset()  # літери одягу з профілю (L, XL): інші літери в оголошенні — відсів

    @property
    def brandless(self) -> bool:
        return not self.brands

    @property
    def catalog(self) -> str | None:
        """catalogSlug для запиту. Бренди: лише розділ (категорії — локально, щоб не дробити групу).
        Пошук без бренду: найвужчий спільний чоловічий батько категорій, інакше розділ."""
        # тактичний розділ — лише локальний фільтр брендів; серверний catalogSlug пошуків без бренду
        # він не розширює (інакше «Лляні брюки» перейшли б на весь розділ men)
        cats = [c for c in self.categories if not c.startswith(LOCAL_ONLY)]
        if not self.brandless or self.section != "men" or not cats:
            return self.section
        parents = {MEN_SERVER_PARENTS.get(c.split("/")[0]) for c in cats}
        if len(parents) != 1 or None in parents:
            return self.section
        if len(cats) == 1 and not cats[0].endswith("*") and not cats[0].startswith("kofty/"):
            return cats[0]
        return parents.pop()

    def query_key(self) -> str:
        """Однакові серверні фільтри → один запит. Категорії не входять (крім пошуків без бренду,
        де вони звужують catalogSlug)."""
        k = {"catalog": self.catalog, "sizes": sorted(self.sizes), "cond": self.min_condition,
             "max_price": self.max_price, "min_price": self.min_price, "materials": sorted(self.materials),
             "brandless": self.brandless, "package": self.package, "text": self.text}
        if self.seller != "any":           # «any» не входить у ключ, щоб старі групи не перезапускались
            k["seller"] = self.seller
        if self.characteristics:
            k["chars"] = sorted(self.characteristics)
        return hashlib.sha1(json.dumps(k, sort_keys=True).encode()).hexdigest()[:12]

    @property
    def conditions(self) -> list[int]:
        if not self.min_condition:
            return []
        return [c for c in CONDITIONS if c <= int(self.min_condition)]

    def variants(self) -> list[tuple[list[int], list[int]]]:
        """Серверні варіанти запиту (стани, характеристики) — йдуть одним HTTP-запитом через аліаси.
        private_new: вживані без фільтра продавця + нові лише від приватних."""
        conds, chars = self.conditions, sorted(set(self.materials) | set(self.characteristics))
        priv = sorted(set(chars) | {SELLER_PRIVATE})
        if self.seller == "private":
            return [(conds, priv)]
        if self.seller == "private_new":
            if conds and 1 not in conds:
                return [(conds, chars)]
            used = [c for c in (conds or list(CONDITIONS)) if c != 1]
            return ([(used, chars)] if used else []) + [([1], priv)]
        return [(conds, chars)]

    def matches_brand(self, item: dict) -> bool:
        return self.brandless or (item.get("brand") or {}).get("id") in self.brands


@dataclass
class Group:
    key: str                 # base key (стан готовності) — без номера пачки
    chunk: int
    rules: list[Rule]
    brand_ids: list[int]     # порожньо = пошук без бренду

    @property
    def id(self) -> str:
        return f"{self.key}:{self.chunk}"

    @property
    def server(self) -> Rule:
        return self.rules[0]  # серверні фільтри однакові для всіх правил групи

    @property
    def package(self) -> str:
        return self.server.package

    def label(self, limit: int = 4) -> str:
        names = list(dict.fromkeys(r.label for r in self.rules))
        return ", ".join(names[:limit]) + (f" +{len(names) - limit}" if len(names) > limit else "")


@dataclass
class Config:
    rules: list[Rule]
    settings: dict
    category_materials: list[CategoryMaterials] = field(default_factory=list)
    measurements: dict = field(default_factory=dict)

    def interval_min(self, package: str) -> float:
        return float((self.settings.get("packages") or {}).get(package, 10))

    @property
    def enabled(self) -> list[Rule]:
        return [r for r in self.rules if r.enabled]

    @property
    def brand_count(self) -> int:
        return len({b for r in self.enabled for b in r.brands})

    def groups(self) -> list[Group]:
        by_key: dict[str, list[Rule]] = {}
        for r in self.enabled:
            by_key.setdefault(r.query_key(), []).append(r)
        max_brands = int(self.settings.get("max_brands_per_query", 50))
        out = []
        for key, rs in by_key.items():
            if rs[0].brandless:
                out.append(Group(key, 0, rs, []))
                continue
            ids = sorted({b for r in rs for b in r.brands})
            for i in range(0, len(ids), max_brands):
                chunk = ids[i:i + max_brands]
                out.append(Group(key, i // max_brands, [r for r in rs if set(r.brands) & set(chunk)], chunk))
        return out


# ---------------------------------------------------------------------------------------------
# Завантаження

class ConfigError(ValueError):
    pass


def _norm_size(group: str, value) -> str:
    s = str(value).strip().upper().replace(",", ".")
    if s in ("ONE SIZE", "ONESIZE", "ONE-SIZE"):
        return "ONE SIZE"
    if group == "одяг":
        s = s.split("/")[0]                     # «L/48» → «L»
        s = {"XXXL": "3XL", "2XL": "XXL"}.get(s, s)
        return _CLOTHES_EU.get(s, s)
    if group == "штани":
        return s if s.startswith("W") else f"W{s}"
    if group == "взуття":
        return s[:-2] if s.endswith(".0") else s
    return s


def resolve_sizes(spec, section: str | None, where: str) -> list[int]:
    """`spec`: список id (як є) або словник {одяг: [L, XL], штани: [W32], взуття: [43]}."""
    if spec is None:
        return []
    if isinstance(spec, list):
        try:
            return sorted({int(s) for s in spec})
        except (TypeError, ValueError):
            raise ConfigError(f"{where}: sizes-список має містити id (числа); для назв використовуй "
                              f"словник {{одяг: [L], штани: [W32], взуття: [43]}}")
    if not isinstance(spec, dict):
        raise ConfigError(f"{where}: sizes має бути словником або списком id")
    table = SIZE_IDS.get(section or "")
    ids: set[int] = set()
    for g, values in spec.items():
        group = SIZE_GROUP_ALIASES.get(str(g).strip().lower())
        if not group:
            raise ConfigError(f"{where}: невідома група розмірів «{g}» (є: одяг, штани, взуття)")
        for v in values or []:
            if isinstance(v, int) and v > 100:   # сирий id
                ids.add(v)
                continue
            if not table:
                raise ConfigError(f"{where}: назви розмірів відомі лише для розділу men; для «{section}» "
                                  f"вкажи id (python tools/lookup.py sizes {section})")
            name = _norm_size(group, v)
            if name not in table[group]:
                raise ConfigError(f"{where}: невідомий розмір «{v}» у групі {group}. "
                                  f"Є: {', '.join(table[group])}")
            ids.update(table[group][name])
    return sorted(ids)


def merge_size_specs(base, override):
    """Розміри пошуку замінюють лише вказані групи профілю: {взуття: [42.5, 43]} лишає одяг і штани."""
    if override is None:
        return base
    if isinstance(override, dict) and isinstance(base, dict):
        merged = {SIZE_GROUP_ALIASES.get(str(k).lower(), k): v for k, v in base.items()}
        for k, v in override.items():
            merged[SIZE_GROUP_ALIASES.get(str(k).lower(), k)] = v
        return merged
    return override


def resolve_categories(spec, section: str | None, where: str) -> list[str]:
    if not spec:
        return []
    if isinstance(spec, str):
        spec = [spec]
    table = CATEGORIES.get(section or "", {})
    out: list[str] = []
    for c in spec:
        key = str(c).strip().lower()
        if key in table:
            out += table[key]
        elif re.fullmatch(r"[a-z0-9-]+(/[a-z0-9-]+)*(/\*)?", key):
            out.append(key if "/" in key else f"{key}/*")       # сирий slug: «obuv» = «obuv/*»
        else:
            known = ", ".join(table) or "(словника для цього розділу немає — вкажи slug-и)"
            raise ConfigError(f"{where}: невідома категорія «{c}». Відомі: {known}")
    return list(dict.fromkeys(out))


def resolve_materials(spec, where: str) -> list[int]:
    ids = []
    for m in spec or []:
        if isinstance(m, int):
            ids.append(m)
        elif str(m).strip().lower() in MATERIAL_IDS:
            ids.append(MATERIAL_IDS[str(m).strip().lower()])
        else:
            raise ConfigError(f"{where}: невідомий матеріал «{m}». Відомі: {', '.join(MATERIAL_IDS)} "
                              f"або id (python tools/lookup.py materials kofti)")
    if len(ids) > 6:   # 11.11.2026: сервер приймає й 5 id однієї характеристики (АБО), більше не перевіряли
        raise ConfigError(f"{where}: не більше 6 матеріалів у фільтрі")
    return sorted(set(ids))


SELLER_ALIASES = {"private_new": "private_new", "нові": "private_new", "нові приватні": "private_new",
                  "private": "private", "приватні": "private", "приватний": "private",
                  "any": "any", "усі": "any", "всі": "any", "будь-хто": "any"}


def resolve_seller(spec, where: str) -> str:
    if spec is None:
        return "any"
    v = SELLER_ALIASES.get(str(spec).strip().lower())
    if not v:
        raise ConfigError(f"{where}: seller має бути private_new (нові лише від приватних), private або any")
    return v


def _check_keys(d: dict, allowed: set[str], where: str) -> None:
    unknown = set(d) - allowed
    if unknown:
        raise ConfigError(f"{where}: невідомі поля {sorted(unknown)}. Дозволені: {sorted(allowed)}")


def _build(fields: dict, label: str, brands: dict[int, str], enabled: bool) -> Rule:
    section = fields.get("section")
    where = label
    for rx in ("materials_include", "materials_exclude", "keywords_exclude", "title_include", "title_prefer"):
        if fields.get(rx):
            try:
                re.compile(fields[rx])
            except re.error as e:
                raise ConfigError(f"{where}: поганий regex у {rx}: {e}")
    cat_names = _as_list(fields.get("categories"))
    if cat_names and brands and fields.get("also_categories"):
        # also_categories (defaults: [худі]) додаються до категорій кожного бренду, у якого вони обмежені.
        cat_names += [c for c in _as_list(fields.get("also_categories")) if c not in cat_names]
    cat_map = {str(c).strip().lower(): resolve_categories([c], section, where) for c in cat_names}
    return Rule(
        label=label, brands=brands, enabled=enabled, section=section,
        sizes=resolve_sizes(fields.get("sizes"), section, where),
        categories=list(dict.fromkeys(s for pats in cat_map.values() for s in pats)),
        category_map=cat_map, title_in_description=bool(fields.get("title_in_description", False)),
        material_rules=bool(fields.get("material_rules", True)), title_prefer=fields.get("title_prefer"),
        genuine_only=bool(fields.get("genuine_only", False)),
        min_share=int(fields["min_share"]) if fields.get("min_share") else None,
        characteristics=_int_list(fields.get("characteristics"), f"{where}: characteristics"),
        min_condition=fields.get("min_condition"), max_price=fields.get("max_price"),
        min_price=fields.get("min_price"), materials=resolve_materials(fields.get("materials"), where),
        materials_include=fields.get("materials_include"), materials_exclude=fields.get("materials_exclude"),
        keywords_exclude=fields.get("keywords_exclude"), max_age_hours=fields.get("max_age_hours"),
        package=str(fields.get("package") or DEFAULT_PACKAGE), title_include=fields.get("title_include"),
        text=fields.get("text"), reseller_filter=bool(fields.get("reseller_filter", True)),
        seller=resolve_seller(fields.get("seller"), where),
        size_letters=profile_letters(fields.get("sizes"), section, where),
    )


def profile_letters(spec, section: str | None, where: str) -> frozenset:
    """Літери одягу, дозволені правилом: з id фільтра розмірів (150, 151 → L, XL)."""
    ids = set(resolve_sizes(spec, section, where))
    names = {n for n, v in SIZE_IDS["men"]["одяг"].items() if ids & set(v)}
    return frozenset(n for n in names if n in _LETTERS)


def _int_list(v, where: str) -> list[int]:
    try:
        return [int(x) for x in _as_list(v)]
    except (TypeError, ValueError):
        raise ConfigError(f"{where}: очікую список id (чисел)")


def _as_list(v) -> list:
    if not v:
        return []
    return [v] if isinstance(v, str) else list(v)


def _brand_ids(b: dict) -> list[int]:
    raw = b.get("id")
    if raw is None:
        raise ConfigError(f"У бренду «{b.get('name')}» немає id. Запусти: python tools/lookup.py fill")
    ids = raw if isinstance(raw, list) else [raw]
    try:
        return [int(i) for i in ids]
    except (TypeError, ValueError):
        raise ConfigError(f"Бренд «{b.get('name')}»: id має бути числом або списком чисел")


def load(path: str | Path) -> Config:
    return loads(Path(path).read_text(encoding="utf-8"))


def loads(text: str) -> Config:
    raw = yaml.safe_load(text) or {}
    _check_keys(raw, {"settings", "my_sizes", "defaults", "brands", "searches", "category_materials", "measurements"},
                "brands.yaml")
    settings = raw.get("settings") or {}
    defaults = dict(raw.get("defaults") or {})
    _check_keys(defaults, set(FILTER_KEYS), "defaults")
    defaults.setdefault("section", "men")
    profile = raw.get("my_sizes")
    if profile is not None and "sizes" in defaults:
        raise ConfigError("Розміри задаються або в my_sizes, або в defaults.sizes, не в обох")
    if profile is not None:
        defaults["sizes"] = profile

    rules: list[Rule] = []
    seen_ids: dict[int, str] = {}
    brand_keys = set(FILTER_KEYS) | {"name", "id", "enabled", "searches"}
    search_keys = set(FILTER_KEYS) | {"name", "enabled"}
    for b in raw.get("brands") or []:
        if not isinstance(b, dict) or not b.get("name"):
            raise ConfigError(f"У бренду немає name: {b}")
        name = str(b["name"])
        _check_keys(b, brand_keys, name)
        ids = _brand_ids(b)
        for i in ids:
            if i in seen_ids:
                raise ConfigError(f"Бренд з id {i} указано двічі ({seen_ids[i]} і {name})")
            seen_ids[i] = name
        enabled = bool(b.get("enabled", True))
        base = {**defaults, **{k: v for k, v in b.items() if k in FILTER_KEYS}}
        base["sizes"] = merge_size_specs(defaults.get("sizes"), b.get("sizes"))
        brands = {i: name for i in ids}
        searches = b.get("searches")
        if not searches:
            rules.append(_build(base, name, brands, enabled))
            continue
        for n, s in enumerate(searches, 1):
            _check_keys(s, search_keys, f"{name} → searches[{n}]")
            fields = {**base, **{k: v for k, v in s.items() if k in FILTER_KEYS}}
            fields["sizes"] = merge_size_specs(base.get("sizes"), s.get("sizes"))
            label = f"{name} · {s['name']}" if s.get("name") else f"{name} #{n}"
            rules.append(_build(fields, label, brands, enabled and bool(s.get("enabled", True))))

    all_brands = {i: str(b["name"]) for b in raw.get("brands") or [] for i in _brand_ids(b)}
    for n, s in enumerate(raw.get("searches") or [], 1):
        label = str(s.get("name") or f"Пошук #{n}")
        _check_keys(s, search_keys | {"brands"}, label)
        fields = {**defaults, **{k: v for k, v in s.items() if k in FILTER_KEYS and k != "also_categories"}}
        fields.pop("also_categories", None)
        fields["sizes"] = merge_size_specs(defaults.get("sizes"), s.get("sizes"))
        sb = s.get("brands")
        if sb in ("all", "усі"):
            sbrands = dict(all_brands)
        elif isinstance(sb, list) and sb:
            ids = _int_list(sb, f"{label}: brands")
            sbrands = {i: all_brands.get(i, str(i)) for i in ids}
        elif sb is None:
            sbrands = {}
        else:
            raise ConfigError(f"{label}: brands у пошуку — all (усі бренди зі списку) або список id")
        rule = _build(fields, label, sbrands, bool(s.get("enabled", True)))
        if not sbrands and not (rule.categories or rule.materials or rule.max_price or rule.text):
            raise ConfigError(f"{label}: пошук без бренду без категорій, матеріалу й ціни — це увесь сайт. "
                              f"Звузь його.")
        rules.append(rule)
    packages = settings.get("packages") or {}
    for r in rules:
        if packages and r.package not in packages:
            raise ConfigError(f"{r.label}: невідомий пакет «{r.package}». Є: {', '.join(packages)}")
    section = defaults.get("section")
    cms = []
    for cat, spec in (raw.get("category_materials") or {}).items():
        where = f"category_materials → {cat}"
        if not isinstance(spec, dict):
            raise ConfigError(f"{where}: очікую словник з only / prefer")
        _check_keys(spec, CATEGORY_MATERIAL_KEYS, where)
        unknown = str(spec.get("if_unknown", "skip"))
        if unknown not in ("skip", "send"):
            raise ConfigError(f"{where}: if_unknown має бути skip або send")
        cms.append(CategoryMaterials(str(cat).strip().lower(), resolve_categories([cat], section, where),
                                     resolve_material_names(spec.get("only"), where),
                                     resolve_material_names(spec.get("prefer"), where), unknown,
                                     resolve_categories(spec.get("except"), section, where),
                                     int(spec["min_share"]) if spec.get("min_share") else None))
    blocks = []
    for n, b in enumerate(settings.get("skip_brand_categories") or [], 1):
        where = f"settings → skip_brand_categories[{n}]"
        if not isinstance(b, dict):
            raise ConfigError(f"{where}: очікую {{brands: [id], categories: [...]}}")
        _check_keys(b, {"brands", "categories", "note"}, where)
        ids, cats = _int_list(b.get("brands"), where), resolve_categories(b.get("categories"), section, where)
        if not ids or not cats:
            raise ConfigError(f"{where}: потрібні і brands, і categories")
        names = sorted({all_brands.get(i, str(i)) for i in ids})
        blocks.append({"brands": set(ids), "categories": cats,
                       "label": f"{' / '.join(names)}: {', '.join(map(str, _as_list(b.get('categories'))))}"})
    settings = {**settings, "skip_brand_categories": blocks}
    meas = raw.get("measurements") or {}
    _check_keys(meas, {"waist_half_min", "length_min", "length_soft", "inseam_min", "insole"}, "measurements")
    if meas.get("insole") and (not isinstance(meas["insole"], list) or len(meas["insole"]) != 2):
        raise ConfigError("measurements.insole: потрібно [від, до], напр. [28.5, 30]")
    return Config(rules, settings, cms, meas)


_TRANS = str.maketrans({"ø": "o", "Ø": "o", "æ": "ae", "Æ": "ae", "ß": "ss", "œ": "oe", "đ": "d", "ł": "l"})


def norm(s: str) -> str:
    """Назва бренду для порівняння: без регістру, діакритики й розділових знаків («Fjällräven» = «fjallraven»)."""
    s = unicodedata.normalize("NFKD", str(s).translate(_TRANS))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = s.replace("&", " and ").replace("+", " plus ")
    return re.sub(r"[^0-9a-zа-яіїєґ]+", "", s)


# ---------------------------------------------------------------------------------------------
# Локальні фільтри

def _age_hours(created_at: str | None) -> float | None:
    if not created_at:
        return None
    try:
        t = dt.datetime.fromisoformat(created_at.replace(" ", "T"))
    except ValueError:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=dt.timezone.utc)
    return (dt.datetime.now(dt.timezone.utc) - t).total_seconds() / 3600


def category_ok(slug: str | None, patterns: list[str]) -> bool:
    if not patterns:
        return True
    if not slug:
        return False
    for p in patterns:
        if p.endswith("/*"):
            if slug.startswith(p[:-1]):
                return True
        elif slug == p:
            return True
    return False


def quick_check(item: dict, rule: Rule) -> str | None:
    """Фільтри за даними зі списку. Повертає причину відсіву або None."""
    # вік першим (12.11.2026): інакше старі «підняті» речі в лозі виглядали як відсіяні категорією
    if rule.max_age_hours is not None:
        age = _age_hours(item.get("createdAt"))
        if age is not None and age > float(rule.max_age_hours):
            return f"старе оголошення ({age:.0f} год)"
    if not category_ok(item.get("catalogSlug"), rule.categories):
        return f"категорія {item.get('catalogSlug')}"
    bad = size_mismatch(item, rule)
    if bad:
        return bad
    if rule.title_include and not rule.title_in_description \
            and not re.search(rule.title_include, item.get("name") or "", re.I):
        return "немає потрібної фрази в назві"
    if rule.reseller_filter and RESELLER_RX.search(item.get("name") or ""):
        return "схоже на перекупника/репліку"
    if rule.keywords_exclude and re.search(rule.keywords_exclude, item.get("name") or "", re.I):
        return "виключене слово в назві"
    if (item.get("statusTitle") or "AVAILABLE") != "AVAILABLE":
        return f"статус {item.get('statusTitle')}"
    return None


def size_mismatch(item: dict, rule: Rule) -> str | None:
    """«розмір M, L» при профілі L, XL — відсів. Річ без літерних розмірів (W34, 45, 48) не чіпає."""
    if not rule.size_letters:
        return None
    names = [s.get("name") for s in item.get("sizes") or [] if isinstance(s, dict) and s.get("name")]
    extra = [t for t in letter_sizes(names) if t not in rule.size_letters]
    if extra:
        return f"розмір {', '.join(names)} (є {', '.join(extra)}, а треба лише {', '.join(sorted(rule.size_letters, key=len))})"
    return None


def blocked_brand_category(item: dict, blocks) -> str | None:
    """settings.skip_brand_categories: бренд × категорія, які не надсилаються ніким (Levi's сорочки)."""
    bid = (item.get("brand") or {}).get("id")
    for b in blocks or []:
        if bid in b["brands"] and category_ok(item.get("catalogSlug"), b["categories"]):
            return f"{b['label']} не надсилаємо"
    return None


def blocked_seller(item: dict, blocked) -> str | None:
    """Чорний список продавців (settings.blocked_sellers: логін або id). Продавець є вже в списку товарів."""
    seller = item.get("seller") or {}
    names = {str(b).strip().lower().lstrip("@") for b in blocked or []}
    if names and ((seller.get("username") or "").lower() in names or str(seller.get("id")) in names):
        return f"продавець {seller.get('username') or seller.get('id')} у чорному списку"
    return None


def title_priority(item: dict, details: dict | None, rule: Rule) -> bool | None:
    """title_prefer: збіг у назві чи описі — ⭐ і звук (True), інакше тихо (False); без поля — None."""
    if not rule.title_prefer:
        return None
    hay = (item.get("name") or "") + "\n" + ((details or {}).get("description") or "")
    return bool(re.search(rule.title_prefer, hay, re.I))


def material_text(details: dict | None, item: dict) -> str:
    parts = [item.get("name") or ""]
    if details:
        parts.append(details.get("description") or "")
        parts += materials_of(details)
    return "\n".join(parts)


def materials_of(details: dict | None) -> list[str]:
    if not details:
        return []
    for ch in details.get("characteristics") or []:
        if (ch.get("title") or "").lower().startswith("матеріал"):
            return [c.get("title") for c in ch.get("choices") or [] if c.get("title")]
    return []


def detail_check(item: dict, details: dict | None, rule: Rule) -> str | None:
    """Фільтри, яким потрібна картка товару (матеріал за описом і характеристиками; фраза саб-лейбла в описі)."""
    if rule.title_include and rule.title_in_description:
        hay = (item.get("name") or "") + "\n" + ((details or {}).get("description") or "")
        if not re.search(rule.title_include, hay, re.I):
            return "немає потрібної фрази в назві й описі"
    if rule.genuine_only and faux_leather((item.get("name") or "") + "\n" + ((details or {}).get("description") or "")):
        return "штучна шкіра/замша за описом"
    if not (rule.materials_include or rule.materials_exclude):
        return None
    text = material_text(details, item)
    if rule.materials_include and not re.search(rule.materials_include, text, re.I):
        return "немає потрібного матеріалу"
    if rule.materials_exclude and re.search(rule.materials_exclude, text, re.I):
        return "виключений матеріал"
    return None


# ---------------------------------------------------------------------------------------------
# Мірки з опису (продавці часто пишуть «пояс 46 см», «довжина 108», «устілка 29 см»).
# Немає мірок — річ проходить; є і не підходять — відсіюємо.
_NUM = r"(\d{2,3}(?:[.,]\d)?)"
_WAIST = re.compile(r"(?:\bпояс\w*|\bталі[яїю]|\bталия|\bпот\b|напівобхват\w*\s+талії|обхват\w*\s+талії|\bwaist)"
                    r"\D{0,20}?" + _NUM, re.I)
_INSEAM = re.compile(r"(?:внутрішн\w*\s+(?:шв\w*|довжин\w*)|по\s+внутр\w*(?:\s+шв\w*)?|довжин\w*\s+(?:по\s+)?(?:кроку|внутр\w*)"
                     r"|\bкрок\w*|\binseam|по\s+шагу)\D{0,20}?" + _NUM, re.I)
_LENGTH = re.compile(r"(?:\bдовжин\w*|\bдлин\w*|\blength|загальн\w*\s+довжин\w*)(?!\s+(?:по\s+)?(?:кроку|внутр|шагу))"
                     r"\D{0,20}?" + _NUM, re.I)
_L_INCH = re.compile(r"\b[wW]\s?\d{2}\s*[/xх×\s]\s*[lL]\s?(\d{2})\b")
_RANGE_TO = re.compile(r"\s*(?:см)?\s*(?:до|[-–—])\s*(\d{2,3}(?:[.,]\d)?)", re.I)
_INSOLE = re.compile(r"(?:устілк\w*|устiлк\w*|стельк\w*|\binsole|по\s+устілці)\D{0,15}?(\d{2}(?:[.,]\d)?)", re.I)
_CM = re.compile(r"\b(2[2-9]|3[0-3])(?:[.,](\d))?\s*см\b", re.I)


def _f(x: str) -> float:
    return float(x.replace(",", "."))


def measure_check(item: dict, details: dict | None, m: dict | None) -> str | None:
    if not m:
        return None
    slug = item.get("catalogSlug") or ""
    text = (item.get("name") or "") + "\n" + ((details or {}).get("description") or "")
    if slug.startswith("shtany-i-shorty/") or slug.startswith("sport-i-otdyh/sportivnyye-shtany"):
        wmin = m.get("waist_half_min")
        if wmin:
            for mw in _WAIST.finditer(text):
                g = mw.group(1)
                # діапазон «пояс від 42 до 48 см», «пояс 42–48» (регульований) — береться більше число (12.11.2026)
                rng = _RANGE_TO.match(text, mw.end())
                if rng and _f(rng.group(1)) > _f(g):
                    g = rng.group(1)
                v = _f(g)
                half = v / 2 if v >= 70 else v                 # 88 см — повний обхват, 44 — напівобхват
                if 30 <= half <= 70 and half < float(wmin) - 0.5:
                    return f"пояс {g} см" + (f" (≈{half:g} напівобхват)" if v >= 70 else "") + f", треба від {wmin}"
                if 30 <= half <= 70:
                    break
        if not slug.endswith("/shorty") and not slug.endswith("/bridzhi"):
            lmin, imin = m.get("length_min"), m.get("inseam_min")
            soft = float(m.get("length_soft") or 0)        # допуск: трохи коротші приходять тихо (measure_quiet)
            for g in (_LENGTH.findall(text) if lmin else []):
                v = _f(g)
                if 80 <= v <= 130:
                    if v < float(lmin) - 1 - soft:
                        return f"довжина {g} см (треба від {lmin})"
                    break
            if imin:
                for g in _INSEAM.findall(text):
                    v = _f(g)
                    if 60 <= v <= 100:
                        if v < float(imin) - 1:
                            return f"довжина по внутрішньому шву {g} см (треба від {imin})"
                        break
                inch = _L_INCH.search(text)
                if inch and 26 <= int(inch.group(1)) <= 38 and int(inch.group(1)) * 2.54 < float(imin) - 1:
                    return f"L{inch.group(1)} ≈ {int(inch.group(1)) * 2.54:.0f} см по внутрішньому шву (треба від {imin})"
    if slug.startswith("obuv/") and m.get("insole"):
        lo, hi = (float(x) for x in m["insole"])
        # усі згадані мірки (і «устілка 29», і «45р 29см»): суперечать одна одній — річ проходить
        vals = [_f(g) for g in _INSOLE.findall(text)] + [_f(a + ("." + b if b else "")) for a, b in _CM.findall(text)]
        vals = [v for v in vals if 22 <= v <= 33]
        if vals and not any(lo <= v <= hi for v in vals):
            return f"устілка {vals[0]:g} см (треба {lo:g}–{hi:g})"
    return None


def measure_quiet(item: dict, details: dict | None, m: dict | None) -> bool:
    """Штани трохи коротші за length_min, але в межах length_soft (12.11.2026: 107–109 см при 110) — тихо."""
    if not m or not m.get("length_min") or not m.get("length_soft"):
        return False
    slug = item.get("catalogSlug") or ""
    if not (slug.startswith("shtany-i-shorty/") or slug.startswith("sport-i-otdyh/sportivnyye-shtany")) \
            or slug.endswith("/shorty") or slug.endswith("/bridzhi"):
        return False
    text = (item.get("name") or "") + "\n" + ((details or {}).get("description") or "")
    lmin = float(m["length_min"])
    for g in _LENGTH.findall(text):
        v = _f(g)
        if 80 <= v <= 130:
            return v < lmin - 1
    return False
