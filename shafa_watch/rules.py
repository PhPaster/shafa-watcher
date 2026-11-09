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
SIZE_GROUP_ALIASES = {"одяг": "одяг", "clothes": "одяг", "штани": "штани", "pants": "штани",
                      "взуття": "взуття", "shoes": "взуття"}

# ---------------------------------------------------------------------------------------------
# Категорії чоловічого розділу: людська назва → slug-и `catalogSlug` товару (усі перевірено на живому API 9.11.2026).
# `x/*` = усе всередині x. Увага: частина «Кофт» має префікс `kofty/` (а `kofty` як розділ — жіночий!).
CATEGORIES: dict[str, dict[str, list[str]]] = {
    "men": {
        "джинси": ["shtany-i-shorty/dzhinsy"],
        "штани": ["shtany-i-shorty/bryuki", "shtany-i-shorty/dzhinsy"],
        "брюки": ["shtany-i-shorty/bryuki"],
        "шорти": ["shtany-i-shorty/shorty", "shtany-i-shorty/bridzhi"],
        "штани й шорти": ["shtany-i-shorty/*"],
        "футболки": ["futbolki-i-maiki/futbolki", "futbolki-i-maiki/polo"],
        "поло": ["futbolki-i-maiki/polo"],
        "майки": ["futbolki-i-maiki/maiki"],
        "сорочки": ["rubashki/rubashki"],
        "теніски": ["rubashki/tenniski"],
        "вишиванки": ["rubashki/vyshivanki"],
        "светри": ["kofti/svitery", "kofti/dzhempery", "kofti/pulovery", "kofti/kardigany"],
        "кардигани": ["kofti/kardigany"],
        "худі": ["kofti/hudi", "kofti/svitshoty", "kofty/tolstovki"],
        "світшоти": ["kofti/hudi", "kofti/svitshoty", "kofty/tolstovki"],
        "лонгсліви": ["kofty/longsliv"],
        "гольфи": ["kofty/golfy"],
        "кофти": ["kofti/*", "kofty/*"],
        "верхній одяг": ["verkhniaia-odezhda/*"],
        "куртки": ["verkhniaia-odezhda/kurtki", "verkhniaia-odezhda/vetrovki"],
        "пуховики": ["verkhniaia-odezhda/pukhoviki"],
        "пальто": ["verkhniaia-odezhda/palto"],
        "парки": ["verkhniaia-odezhda/parki"],
        "жилетки": ["verkhniaia-odezhda/zhiletki"],
        "дублянки": ["verkhniaia-odezhda/dublenki-i-shuby"],
        "піджаки": ["pidzhaki-i-kostiumy/pidzhaki", "pidzhaki-i-kostiumy/zhakety"],
        "костюми": ["pidzhaki-i-kostiumy/delovye-kostiumy"],
        "взуття": ["obuv/*"],
        "кросівки": ["obuv/krossovki", "obuv/kedy"],
        "кеди": ["obuv/kedy"],
        "черевики": ["obuv/botinki", "obuv/sapogi"],
        "туфлі": ["obuv/tufli"],
        "мокасини": ["obuv/mokasiny"],
        "сандалі": ["obuv/sandali"],
        "спорт": ["sport-i-otdyh/*"],
    },
}
# Верхній рівень slug-а, який можна передати в запит як catalogSlug (лише чоловічі, перевірено за URL товарів).
# `kofty/*` у чоловічому розділі лежать під `kofti`; сам `kofty` — жіночий розділ, у запит його не передаємо.
MEN_SERVER_PARENTS = {"kofti": "kofti", "kofty": "kofti", "obuv": "obuv", "futbolki-i-maiki": "futbolki-i-maiki",
                      "rubashki": "rubashki", "shtany-i-shorty": "shtany-i-shorty",
                      "verkhniaia-odezhda": "verkhniaia-odezhda", "pidzhaki-i-kostiumy": "pidzhaki-i-kostiumy",
                      "sport-i-otdyh": "sport-i-otdyh"}

FILTER_KEYS = ("section", "sizes", "categories", "min_condition", "max_price", "min_price", "materials",
               "materials_include", "materials_exclude", "keywords_exclude", "max_age_hours")
# Назви матеріалів → id (характеристика 11, перевірено `tools/lookup.py materials kofti`). Інші — числом.
MATERIAL_IDS = {"бавовна": 1243, "вовна": 1245, "кашемір": 1225, "льон": 1230, "шовк": 1244,
                "штучний шовк": 1224, "акрил": 1206, "альпака": 2252, "ангора": 2266}


# Матеріали для правил за категоріями: шукаються в назві, описі й полі «Матеріал» (uk / ru / en).
# (include, exclude): exclude скасовує збіг («штучна шкіра» — не шкіра), якщо поруч немає «натуральна».
MATERIALS: dict[str, tuple[str, str | None]] = {
    "вовна": (r"(?<!ба)вовн|шерст|\bwool|merino|мерино|lambswool|ламбсвул|shetland|шетланд", None),
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
              r"искусствен\w*\s+кож|faux\s+leather|\bpu\b|vegan\s+leather|кожвініл"),
    "замша": (r"замш|suede", r"штучн\w*\s+замш|еко\s*-?\s*замш|искусствен\w*\s+замш|faux\s+suede"),
    "нубук": (r"нубук|nubuck", None),
    "акрил": (r"акрил|acrylic", None),
    "поліестер": (r"поліест|полиэст|polyester", None),
}
_GENUINE = re.compile(r"натуральн\w*\s+(шкір|кож|замш)|genuine\s+leather|real\s+leather|full\s*grain", re.I)


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

CATEGORY_MATERIAL_KEYS = {"only", "prefer", "if_unknown"}


def material_check(item: dict, details: dict | None, cms: list[CategoryMaterials]) \
        -> tuple[str | None, bool | None, list[str]]:
    """→ (причина відсіву або None, пріоритет: True/False/None якщо правила prefer немає, знайдені матеріали)."""
    slug = item.get("catalogSlug")
    matched = [c for c in cms if category_ok(slug, c.patterns)]
    text = material_text(details, item)
    found = sorted(detect_materials(text))
    if not matched:
        return None, None, found
    only = {m for c in matched for m in c.only}
    prefer = {m for c in matched for m in c.prefer}
    if only and not (set(found) & only):
        if not found and all(c.if_unknown == "send" for c in matched if c.only):
            pass
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

    @property
    def brandless(self) -> bool:
        return not self.brands

    @property
    def catalog(self) -> str | None:
        """catalogSlug для запиту. Бренди: лише розділ (категорії — локально, щоб не дробити групу).
        Пошук без бренду: найвужчий спільний чоловічий батько категорій, інакше розділ."""
        if not self.brandless or self.section != "men" or not self.categories:
            return self.section
        parents = {MEN_SERVER_PARENTS.get(c.split("/")[0]) for c in self.categories}
        if len(parents) != 1 or None in parents:
            return self.section
        if len(self.categories) == 1 and not self.categories[0].endswith("*") \
                and not self.categories[0].startswith("kofty/"):
            return self.categories[0]
        return parents.pop()

    def query_key(self) -> str:
        """Однакові серверні фільтри → один запит. Категорії не входять (крім пошуків без бренду,
        де вони звужують catalogSlug)."""
        k = {"catalog": self.catalog, "sizes": sorted(self.sizes), "cond": self.min_condition,
             "max_price": self.max_price, "min_price": self.min_price, "materials": sorted(self.materials),
             "brandless": self.brandless}
        return hashlib.sha1(json.dumps(k, sort_keys=True).encode()).hexdigest()[:12]

    @property
    def conditions(self) -> list[int]:
        if not self.min_condition:
            return []
        return [c for c in CONDITIONS if c <= int(self.min_condition)]

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

    def label(self, limit: int = 4) -> str:
        names = list(dict.fromkeys(r.label for r in self.rules))
        return ", ".join(names[:limit]) + (f" +{len(names) - limit}" if len(names) > limit else "")


@dataclass
class Config:
    rules: list[Rule]
    settings: dict
    category_materials: list[CategoryMaterials] = field(default_factory=list)

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
    if len(ids) > 3:
        raise ConfigError(f"{where}: сайт приймає до 3 матеріалів у фільтрі")
    return sorted(set(ids))


def _check_keys(d: dict, allowed: set[str], where: str) -> None:
    unknown = set(d) - allowed
    if unknown:
        raise ConfigError(f"{where}: невідомі поля {sorted(unknown)}. Дозволені: {sorted(allowed)}")


def _build(fields: dict, label: str, brands: dict[int, str], enabled: bool) -> Rule:
    section = fields.get("section")
    where = label
    for rx in ("materials_include", "materials_exclude", "keywords_exclude"):
        if fields.get(rx):
            try:
                re.compile(fields[rx])
            except re.error as e:
                raise ConfigError(f"{where}: поганий regex у {rx}: {e}")
    return Rule(
        label=label, brands=brands, enabled=enabled, section=section,
        sizes=resolve_sizes(fields.get("sizes"), section, where),
        categories=resolve_categories(fields.get("categories"), section, where),
        min_condition=fields.get("min_condition"), max_price=fields.get("max_price"),
        min_price=fields.get("min_price"), materials=resolve_materials(fields.get("materials"), where),
        materials_include=fields.get("materials_include"), materials_exclude=fields.get("materials_exclude"),
        keywords_exclude=fields.get("keywords_exclude"), max_age_hours=fields.get("max_age_hours"),
    )


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
    _check_keys(raw, {"settings", "my_sizes", "defaults", "brands", "searches", "category_materials"}, "brands.yaml")
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

    for n, s in enumerate(raw.get("searches") or [], 1):
        label = str(s.get("name") or f"Пошук #{n}")
        _check_keys(s, search_keys, label)
        fields = {**defaults, **{k: v for k, v in s.items() if k in FILTER_KEYS}}
        fields["sizes"] = merge_size_specs(defaults.get("sizes"), s.get("sizes"))
        rule = _build(fields, label, {}, bool(s.get("enabled", True)))
        if not (rule.categories or rule.materials or rule.max_price):
            raise ConfigError(f"{label}: пошук без бренду без категорій, матеріалу й ціни — це увесь сайт. "
                              f"Звузь його.")
        rules.append(rule)
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
        cms.append(CategoryMaterials(str(cat), resolve_categories([cat], section, where),
                                     resolve_material_names(spec.get("only"), where),
                                     resolve_material_names(spec.get("prefer"), where), unknown))
    return Config(rules, settings, cms)


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
    if not category_ok(item.get("catalogSlug"), rule.categories):
        return f"категорія {item.get('catalogSlug')}"
    if rule.max_age_hours is not None:
        age = _age_hours(item.get("createdAt"))
        if age is not None and age > float(rule.max_age_hours):
            return f"старе оголошення ({age:.0f} год)"
    if rule.keywords_exclude and re.search(rule.keywords_exclude, item.get("name") or "", re.I):
        return "виключене слово в назві"
    if (item.get("statusTitle") or "AVAILABLE") != "AVAILABLE":
        return f"статус {item.get('statusTitle')}"
    return None


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
    """Фільтри, яким потрібна картка товару (матеріал за описом і характеристиками)."""
    if not (rule.materials_include or rule.materials_exclude):
        return None
    text = material_text(details, item)
    if rule.materials_include and not re.search(rule.materials_include, text, re.I):
        return "немає потрібного матеріалу"
    if rule.materials_exclude and re.search(rule.materials_exclude, text, re.I):
        return "виключений матеріал"
    return None
