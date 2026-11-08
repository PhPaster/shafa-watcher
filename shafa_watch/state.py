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
        self.groups: dict[str, dict] = data.get("groups", {})      # key -> {"brands": [...], "since": ts}
        self.health: dict = data.get("health", {})
        self.stats: dict = data.get("stats", {})

    # --- дедуплікація ---
    def is_seen(self, pid) -> bool:
        return str(pid) in self.seen

    def mark(self, pid) -> None:
        self.seen[str(pid)] = time.time()

    def group_ready(self, key: str, brand_ids: list[int]) -> bool:
        """Група вважається ініціалізованою, лише якщо набір брендів у ній не змінився.
        Новий бренд → перший прохід групи лише запам'ятовує товари (без спаму)."""
        g = self.groups.get(key)
        return bool(g) and set(g.get("brands", [])) >= set(brand_ids)

    def set_group_ready(self, key: str, brand_ids: list[int]) -> None:
        self.groups[key] = {"brands": sorted(brand_ids), "since": time.time()}

    def prune(self, active_keys: set[str]) -> None:
        cutoff = time.time() - SEEN_TTL_DAYS * 86400
        self.seen = {k: v for k, v in self.seen.items() if v >= cutoff}
        self.groups = {k: v for k, v in self.groups.items() if k in active_keys}

    def save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"seen": self.seen, "groups": self.groups, "health": self.health,
                                   "stats": self.stats}, ensure_ascii=False, separators=(",", ":")),
                       encoding="utf-8")
        tmp.replace(self.path)
