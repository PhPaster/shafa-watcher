"""Стан між запусками: бачені id, ініціалізовані групи, лічильники здоров'я."""
from __future__ import annotations

import json
import time
from pathlib import Path

SEEN_TTL_DAYS = 21


class State:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        data = {}
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding="utf-8") or "{}")
        self.seen: dict[str, float] = data.get("seen", {})
        self.groups: dict[str, dict] = data.get("groups", {})      # base key -> {"brands": [готові id], "since": ts}
        self.health: dict = data.get("health", {})
        self.stats: dict = data.get("stats", {})

    # --- дедуплікація ---
    def is_seen(self, pid) -> bool:
        return str(pid) in self.seen

    def mark(self, pid) -> None:
        self.seen[str(pid)] = time.time()

    def ready(self, key: str, brand_id: int | None) -> bool:
        """Чи група вже ініціалізована для цього бренду (None = пошук без бренду).
        Новий бренд або змінені серверні фільтри → перший прохід лише запам'ятовує товари (без спаму),
        а решта брендів групи працює як звичайно."""
        g = self.groups.get(key)
        if not g:
            return False
        return brand_id is None or brand_id in set(g.get("brands", []))

    def any_ready(self, key: str, brand_ids: list[int]) -> bool:
        g = self.groups.get(key)
        return bool(g) and (not brand_ids or bool(set(g.get("brands", [])) & set(brand_ids)))

    def set_ready(self, key: str, brand_ids: list[int]) -> None:
        g = self.groups.setdefault(key, {"brands": [], "since": time.time()})
        g["brands"] = sorted(set(g["brands"]) | set(brand_ids))

    def prune(self, active_keys: set[str]) -> None:
        cutoff = time.time() - SEEN_TTL_DAYS * 86400
        self.seen = {k: v for k, v in self.seen.items() if v >= cutoff}
        self.groups = {k: v for k, v in self.groups.items() if k in active_keys}

    def prune_brands(self, active: dict[str, set[int]]) -> None:
        """Прибрати з готовності бренди, яких більше немає в групі: якщо бренд повернуть, він знову
        пройде тихий перший прохід."""
        for k, brands in active.items():
            if k in self.groups:
                self.groups[k]["brands"] = sorted(set(self.groups[k]["brands"]) & brands)

    def save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"seen": self.seen, "groups": self.groups, "health": self.health,
                                   "stats": self.stats}, ensure_ascii=False, separators=(",", ":")),
                       encoding="utf-8")
        tmp.replace(self.path)
