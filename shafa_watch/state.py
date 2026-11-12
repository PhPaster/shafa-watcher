"""Стан між запусками: бачені id, ініціалізовані групи, лічильники здоров'я."""
from __future__ import annotations

import json
import time
from pathlib import Path

SEEN_TTL_DAYS = 21
SENT_TTL_DAYS = 30
EVAL_TTL_DAYS = 3


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
        self.titles: dict[str, float] = data.get("titles", {})     # назва+ціна надісланих (антиповтор)
        self.sent: dict[str, float] = data.get("sent", {})         # id надісланих: ніколи не надсилати вдруге
        # id відсіяної речі → ключі груп, правила яких її вже оцінили (12.11.2026). Якщо річ пізніше поверне
        # інша група (продавець дописав матеріал — і її знайшов пошук без бренду), вона оцінюється ще раз.
        self.evaluated: dict[str, list] = data.get("evaluated", {})  # pid → [ts, [ключі груп]]

    # --- дедуплікація ---
    def is_seen(self, pid) -> bool:
        return str(pid) in self.seen

    def mark(self, pid, group_keys=None) -> None:
        self.seen[str(pid)] = time.time()
        if group_keys:
            prev = self.evaluated.get(str(pid), [0, []])[1]
            self.evaluated[str(pid)] = [time.time(), sorted(set(prev) | set(group_keys))]

    def unevaluated(self, pid, group_keys) -> set[str]:
        """Ключі груп, які цю (вже бачену) річ ще не оцінювали. Для старих записів без історії — порожньо."""
        e = self.evaluated.get(str(pid))
        if not e:
            return set()
        return set(group_keys) - set(e[1])

    def was_sent(self, pid) -> bool:
        return str(pid) in self.sent

    def mark_sent(self, pid) -> None:
        self.sent[str(pid)] = time.time()
        self.evaluated.pop(str(pid), None)

    def seed_sent(self, path: str | Path) -> int:
        """Разово додати id надісланого з логів Actions (data/sent_seed.json: {"ids": [...]}) — захист від
        дублів у довантаженні, навіть якщо назва чи ціна змінились."""
        p = Path(path)
        if self.health.get("sent_seeded") or not p.exists():
            return 0
        ids = json.loads(p.read_text(encoding="utf-8")).get("ids", [])
        now = time.time()
        for i in ids:
            self.sent.setdefault(str(i), now)
        self.health["sent_seeded"] = now
        return len(ids)

    def title_seen(self, key: str, days: float = 7) -> bool:
        return time.time() - self.titles.get(key, 0) < days * 86400

    def mark_title(self, key: str) -> None:
        self.titles[key] = time.time()

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
        self.titles = {k: v for k, v in self.titles.items() if v >= time.time() - 7 * 86400}
        self.sent = {k: v for k, v in self.sent.items() if v >= time.time() - SENT_TTL_DAYS * 86400}
        self.evaluated = {k: v for k, v in self.evaluated.items() if v[0] >= time.time() - EVAL_TTL_DAYS * 86400}
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
                                   "stats": self.stats, "titles": self.titles,
                                   "sent": self.sent, "evaluated": self.evaluated}, ensure_ascii=False, separators=(",", ":")),
                       encoding="utf-8")
        tmp.replace(self.path)
