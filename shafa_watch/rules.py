"""Завантаження brands.yaml, групування брендів у запити й локальні фільтри."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

# Стани на Shafa (id з filterConditions): 1 Новий, 2 Ідеальний, 3 Дуже хороший, 4 Хороший, 5 Задовільний.
CONDITIONS = {1: "Новий", 2: "Ідеальний", 3: "Дуже хороший", 4: "Хороший", 5: "Задовільний"}

RULE_KEYS = ("section", "sizes", "min_condition", "max_price", "min_price", "materials",
             "materials_include", "materials_exclude", "keywords_exclude", "max_age_hours")


@dataclass
class BrandRule:
    name: str
    id: int
    enabled: bool = True
    section: str | None = None          # catalogSlug: men, women, kids, men/kofti ... None = усі розділи
    sizes: list[int] = field(default_factory=list)       # id фільтра розмірів (див. README)
    min_condition: int | None = None    # 3 = «Дуже хороший» і краще
    max_price: int | None = None
    min_price: int | None = None
    materials: list[int] = field(default_factory=list)   # id матеріалів (характеристика 11), серверний фільтр
    materials_include: str | None = None  # regex по назві+опису+характеристиках
    materials_exclude: str | None = None
    keywords_exclude: str | None = None   # regex по назві (наприклад, "дитяч|kids")
    max_age_hours: float | None = None    # ігнорувати «підняті» старі оголошення

    def query_key(self) -> str:
        """Однакові серверні фільтри → один запит для кількох брендів."""
        k = {"section": self.section, "sizes": sorted(self.sizes), "cond": self.min_condition,
             "max_price": self.max_price, "min_price": self.min_price, "materials": sorted(self.materials)}
        return hashlib.sha1(json.dumps(k, sort_keys=True).encode()).hexdigest()[:12]

    @property
    def conditions(self) -> list[int]:
        if not self.min_condition:
            return []
        return [c for c in CONDITIONS if c <= int(self.min_condition)]


@dataclass
class Group:
    key: str
    rule: BrandRule          # серверні фільтри беруться з першого бренду (вони однакові для групи)
    brand_ids: list[int]


@dataclass
class Config:
    brands: list[BrandRule]
    settings: dict

    @property
    def enabled(self) -> list[BrandRule]:
        return [b for b in self.brands if b.enabled]

    def by_id(self) -> dict[int, BrandRule]:
        return {b.id: b for b in self.enabled}

    def groups(self) -> list[Group]:
        groups: dict[str, Group] = {}
        for b in self.enabled:
            k = b.query_key()
            g = groups.setdefault(k, Group(k, b, []))
            g.brand_ids.append(b.id)
        max_brands = int(self.settings.get("max_brands_per_query", 50))
        out = []
        for g in groups.values():
            ids = sorted(set(g.brand_ids))
            for i in range(0, len(ids), max_brands):
                chunk = ids[i:i + max_brands]
                out.append(Group(f"{g.key}:{i // max_brands}", g.rule, chunk))
        return out


def load(path: str | Path) -> Config:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    defaults = raw.get("defaults") or {}
    settings = raw.get("settings") or {}
    brands = []
    seen_ids = set()
    for b in raw.get("brands") or []:
        merged = {**{k: v for k, v in defaults.items() if k in RULE_KEYS}, **b}
        if "id" not in merged or "name" not in merged:
            raise ValueError(f"У бренду немає name/id: {b}")
        if merged["id"] in seen_ids:
            raise ValueError(f"Бренд з id {merged['id']} указано двічі")
        seen_ids.add(merged["id"])
        unknown = set(merged) - set(RULE_KEYS) - {"name", "id", "enabled"}
        if unknown:
            raise ValueError(f"Невідомі поля в бренді {merged['name']}: {sorted(unknown)}")
        merged["sizes"] = [int(s) for s in merged.get("sizes") or []]
        merged["materials"] = [int(s) for s in merged.get("materials") or []]
        brands.append(BrandRule(**merged))
    return Config(brands, settings)


def _age_hours(created_at: str | None) -> float | None:
    if not created_at:
        return None
    try:
        t = dt.datetime.fromisoformat(created_at.replace(" ", "T"))
    except ValueError:
        return None
    return (dt.datetime.now(dt.timezone.utc) - t).total_seconds() / 3600


def quick_check(item: dict, rule: BrandRule) -> str | None:
    """Фільтри за даними зі списку. Повертає причину відсіву або None."""
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
        for ch in details.get("characteristics") or []:
            if (ch.get("title") or "").lower().startswith("матеріал"):
                parts += [c.get("title") or "" for c in ch.get("choices") or []]
    return "\n".join(parts)


def materials_of(details: dict | None) -> list[str]:
    if not details:
        return []
    for ch in details.get("characteristics") or []:
        if (ch.get("title") or "").lower().startswith("матеріал"):
            return [c.get("title") for c in ch.get("choices") or [] if c.get("title")]
    return []


def detail_check(item: dict, details: dict | None, rule: BrandRule) -> str | None:
    """Фільтри, яким потрібна картка товару (матеріал за описом і характеристиками)."""
    text = material_text(details, item)
    if rule.materials_include and not re.search(rule.materials_include, text, re.I):
        return "немає потрібного матеріалу"
    if rule.materials_exclude and re.search(rule.materials_exclude, text, re.I):
        return "виключений матеріал"
    return None
