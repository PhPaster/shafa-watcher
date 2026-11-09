"""Керування з Telegram: команди бота змінюють brands.yaml.

Без вебхука й без окремого сервера: кожен прохід воркфлоу (раз на 10 хв) читає нові повідомлення через
getUpdates, застосовує команди, перевіряє, що конфіг валідний, записує brands.yaml (коментарі зберігаються)
і відповідає в чат. Воркфлоу потім комітить brands.yaml у репозиторій. Команди приймаються лише з TG_CHAT.

Команди: /help /status /brands [текст] /add /remove /off /on /condition /sizes /cancel
"""
from __future__ import annotations

import io
import logging
import re
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq

from . import rules
from .telegram import esc

log = logging.getLogger(__name__)

COMMANDS = [
    ("status", "Поточні налаштування: розміри, стан, кількість брендів"),
    ("brands", "Список брендів (або пошук: /brands cos)"),
    ("add", "Додати бренд: /add Our Legacy: сорочки, светри"),
    ("remove", "Прибрати бренд: /remove COS"),
    ("off", "Призупинити бренд: /off COS"),
    ("on", "Увімкнути бренд знову: /on COS"),
    ("condition", "Мінімальний стан: /condition 3 (або /condition COS 2)"),
    ("sizes", "Розміри: /sizes одяг L XL"),
    ("materials", "Матеріали категорії: /materials светри: вовна, кашемір"),
    ("prefer", "Пріоритетні матеріали: /prefer взуття: шкіра, замша"),
    ("help", "Довідка"),
]

HELP = """<b>Керування Shafa Watcher</b>
Команди виконуються на наступному проході (до ~10 хв), бот відповість, коли зміну збережено.

<b>Бренди</b>
/brands — список · /brands cos — пошук
/add Our Legacy — додати (усі категорії в моїх розмірах)
/add Our Legacy: сорочки, светри — додати з категоріями
/remove COS — прибрати зовсім
/off COS · /on COS — призупинити / увімкнути

<b>Стан</b> (1 Новий, 2 Ідеальний, 3 Дуже хороший, 4 Хороший, 5 Задовільний; «3» = 3 і краще)
/condition — показати кнопки
/condition 2 — для всіх брендів
/condition COS 1 — лише для бренду · /condition COS default — як у всіх

<b>Розміри</b> (для всіх брендів)
/sizes — показати
/sizes одяг L XL
/sizes штани W34 W36 W38
/sizes взуття 45 45.5 46
/sizes взуття - — не шукати взуття

<b>Матеріали за категоріями</b> (для всіх брендів; шукаю в назві, описі й полі «Матеріал»)
/materials — показати
/materials светри: вовна, кашемір, альпака, ангора — лише такі
/materials светри + мохер · /materials светри - кашемір
/materials светри невідомі так — надсилати й без вказаного матеріалу (за замовчуванням ні)
/materials светри off — прибрати обмеження
/prefer взуття: шкіра, замша — пріоритет: такі приходять зі ⭐ і звуком, решта — тихо
/prefer взуття + нубук · /prefer взуття - замша · /prefer взуття off

Матеріали: {mats}

Категорії: джинси, штани, брюки, шорти, футболки, поло, сорочки, светри, кардигани, худі, лонгсліви, кофти, верхній одяг, куртки, пуховики, пальто, піджаки, костюми, взуття, кросівки, черевики, туфлі…

Після зміни розмірів чи стану перший прохід лише запам'ятовує поточні товари (без спаму)."""


HELP = HELP.replace("{mats}", ", ".join(rules.MATERIALS))


class Bot:
    def __init__(self, tg, config_path: str | Path, state, shafa):
        self.tg = tg
        self.path = Path(config_path)
        self.state = state.health.setdefault("bot", {})
        self.shafa = shafa
        self.yaml = YAML()
        self.yaml.preserve_quotes = True
        self.yaml.width = 120
        self.yaml.indent(mapping=2, sequence=4, offset=2)
        self.doc = self.yaml.load(self.path.read_text(encoding="utf-8"))
        self.changes: list[str] = []

    # ------------------------------------------------------------------ цикл
    def process(self) -> list[str]:
        """Обробити нові повідомлення. Повертає список змін (для коміту), порожній — нічого не змінилося."""
        if self.tg.dry_run:
            return []
        self._ensure_commands()
        offset = self.state.get("offset")
        params = {"timeout": 0, "allowed_updates": ["message", "callback_query"]}
        if offset:
            params["offset"] = offset
        try:
            updates = self.tg.call("getUpdates", params, with_chat=False).get("result", [])
        except Exception as e:  # noqa: BLE001
            log.error("getUpdates: %s", e)
            return []
        if updates:
            log.info("бот: нових повідомлень %d", len(updates))
        for u in updates:
            self.state["offset"] = u["update_id"] + 1
            try:
                self._handle(u)
            except Exception as e:  # noqa: BLE001 — команда не повинна ламати моніторинг
                log.exception("команда бота")
                self._reply(f"⚠️ Не вдалося виконати: {esc(e)}")
        if self.changes:
            self.path.write_text(self._dump(), encoding="utf-8")
        return self.changes

    def _ensure_commands(self) -> None:
        sig = "|".join(c for c, _ in COMMANDS)
        if self.state.get("commands") == sig:
            return
        try:
            self.tg.call("setMyCommands", {"commands": [{"command": c, "description": d} for c, d in COMMANDS]},
                         with_chat=False)
            self.state["commands"] = sig
        except Exception as e:  # noqa: BLE001
            log.warning("setMyCommands: %s", e)

    def _handle(self, u: dict) -> None:
        if "callback_query" in u:
            cq = u["callback_query"]
            if str(cq.get("message", {}).get("chat", {}).get("id")) != str(self.tg.chat_id):
                return
            try:
                self.tg.call("answerCallbackQuery", {"callback_query_id": cq["id"]}, with_chat=False)
            except Exception:  # noqa: BLE001
                pass
            log.info("бот: кнопка %s", cq.get("data"))
            self._callback(cq.get("data") or "")
            return
        msg = u.get("message") or {}
        if str(msg.get("chat", {}).get("id")) != str(self.tg.chat_id):
            log.warning("повідомлення з чужого чату %s проігноровано", msg.get("chat", {}).get("id"))
            return
        text = (msg.get("text") or "").strip()
        if not text.startswith("/"):
            if text:
                self._reply("Я розумію лише команди. /help — список.")
            return
        cmd, _, arg = text.partition(" ")
        cmd = cmd[1:].split("@")[0].lower()
        log.info("бот: /%s %s", cmd, arg[:60])
        handler = getattr(self, f"cmd_{cmd}", None)
        if not handler:
            self._reply(f"Невідома команда /{esc(cmd)}. /help — список.")
            return
        handler(arg.strip())

    # ------------------------------------------------------------------ допоміжне
    def _reply(self, text: str, buttons: list[list[tuple[str, str]]] | None = None) -> None:
        payload = {"text": text[:4096], "parse_mode": "HTML", "disable_web_page_preview": True}
        if buttons:
            payload["reply_markup"] = {"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in row]
                                                           for row in buttons]}
        self.tg.call("sendMessage", payload)

    def _dump(self) -> str:
        buf = io.StringIO()
        self.yaml.dump(self.doc, buf)
        return buf.getvalue()

    def _commit(self, change: str) -> bool:
        """Перевірити, що конфіг після зміни валідний. Якщо ні — відкотити зміну в пам'яті."""
        text = self._dump()
        try:
            rules.loads(text)
        except rules.ConfigError as e:
            self.doc = self.yaml.load(self.path.read_text(encoding="utf-8")) if not self.changes \
                else self.yaml.load(self._last_good)
            self._reply(f"❌ Не зберіг: {esc(e)}")
            return False
        self._last_good = text
        self.changes.append(change)
        return True

    @property
    def brands(self) -> CommentedSeq:
        if self.doc.get("brands") is None:
            self.doc["brands"] = CommentedSeq()
        return self.doc["brands"]

    def _find(self, name: str) -> list[int]:
        n = rules.norm(name)
        exact = [i for i, b in enumerate(self.brands) if rules.norm(b.get("name", "")) == n]
        if exact:
            return exact
        return [i for i, b in enumerate(self.brands) if n and n in rules.norm(b.get("name", ""))]

    def _one(self, name: str, verb: str) -> int | None:
        found = self._find(name)
        if not found:
            self._reply(f"Бренду «{esc(name)}» у списку немає. /brands {esc(name[:10])} — пошук.")
            return None
        if len(found) > 1:
            names = ", ".join(self.brands[i]["name"] for i in found[:15])
            self._reply(f"Під «{esc(name)}» підходить кілька: {esc(names)}. Напиши точну назву: /{verb} …")
            return None
        return found[0]

    @staticmethod
    def _flow(items) -> CommentedSeq:
        s = CommentedSeq(items)
        s.fa.set_flow_style()
        return s

    def _brand_line(self, b) -> str:
        parts = [f"<b>{esc(b['name'])}</b>"]
        if b.get("enabled") is False:
            parts.append("⏸")
        if b.get("categories"):
            parts.append(esc(", ".join(map(str, b["categories"]))))
        if b.get("min_condition"):
            parts.append(f"стан ≤{b['min_condition']}")
        if b.get("max_price"):
            parts.append(f"до {b['max_price']} грн")
        if b.get("searches"):
            parts.append(f"{len(b['searches'])} пошуки")
        return " · ".join(parts)

    # ------------------------------------------------------------------ команди
    def cmd_start(self, arg: str) -> None:
        self.cmd_help(arg)

    def cmd_help(self, arg: str) -> None:
        self._reply(HELP)

    def cmd_cancel(self, arg: str) -> None:
        self.state.pop("pending", None)
        self._reply("Скасовано.")

    def cmd_status(self, arg: str) -> None:
        d = self.doc.get("defaults") or {}
        cond = d.get("min_condition")
        on = sum(1 for b in self.brands if b.get("enabled", True) is not False)
        lines = ["<b>Налаштування</b>",
                 f"Брендів: {len(self.brands)} (активних {on}), пошуків без бренду: {len(self.doc.get('searches') or [])}",
                 f"Стан: {self._cond_text(cond)}",
                 "Розміри:"] + [f"  {g}: {', '.join(map(str, v)) if v else '—'}" for g, v in self._sizes().items()]
        self._reply("\n".join(esc(x) if i else x for i, x in enumerate(lines)))

    @staticmethod
    def _cond_text(c) -> str:
        if not c:
            return "будь-який"
        return f"{rules.CONDITIONS[int(c)]} і краще ({c})"

    def cmd_brands(self, arg: str) -> None:
        items = list(self.brands)
        if arg:
            idx = self._find(arg)
            items = [self.brands[i] for i in idx]
            if not items:
                self._reply(f"Нічого не знайдено за «{esc(arg)}». Додати: /add {esc(arg)}")
                return
        if not items:
            self._reply("Список брендів порожній. /add Назва — додати.")
            return
        if len(items) <= 40:
            self._reply(f"<b>Бренди ({len(items)})</b>\n" + "\n".join(self._brand_line(b) for b in items))
            return
        # великий список — лише назви, кількома повідомленнями
        names = sorted((("⏸ " if b.get("enabled") is False else "") + str(b["name"]) for b in items), key=str.lower)
        chunk, size = [], 0
        head = f"<b>Бренди ({len(items)})</b>. Деталі: /brands назва\n"
        for n in names:
            if size + len(n) + 2 > 3500:
                self._reply(head + esc(", ".join(chunk)))
                head, chunk, size = "", [], 0
            chunk.append(n)
            size += len(n) + 2
        if chunk:
            self._reply(head + esc(", ".join(chunk)))

    def cmd_add(self, arg: str) -> None:
        name, _, cats_raw = arg.partition(":")
        name = name.strip()
        if not name:
            self._reply("Напиши назву: /add Our Legacy або /add Our Legacy: сорочки, светри")
            return
        cats = [c.strip() for c in re.split(r"[,;]", cats_raw) if c.strip()]
        if cats:
            try:
                rules.resolve_categories(cats, (self.doc.get("defaults") or {}).get("section", "men"), name)
            except rules.ConfigError as e:
                self._reply(f"❌ {esc(e)}")
                return
        if self._find(name) and rules.norm(self.brands[self._find(name)[0]]["name"]) == rules.norm(name):
            self._reply(f"«{esc(name)}» уже є: {self._brand_line(self.brands[self._find(name)[0]])}")
            return
        found = self.shafa.find_brands(name)
        exact = [b for b in found if rules.norm(b["name"]) == rules.norm(name)]
        if len(exact) == 1:
            self._add(exact[0]["name"], exact[0]["id"], cats)
            return
        options = exact or found[:8]
        if not options:
            self._reply(f"На Shafa немає бренду «{esc(name)}». Перевір написання або знайди бренд у фільтрі на сайті "
                        f"й надішли його точну назву.")
            return
        self.state["pending"] = {"cats": cats, "options": {str(b["id"]): b["name"] for b in options}}
        self._reply(f"Точного збігу для «{esc(name)}» немає. Який із цих?",
                    [[(b["name"][:40], f"add:{b['id']}")] for b in options] + [[("Жоден", "add:none")]])

    def _add(self, name: str, bid: int, cats: list[str]) -> None:
        if any(int(i) == int(bid) for b in self.brands for i in
               (b.get("id") if isinstance(b.get("id"), list) else [b.get("id")]) if i is not None):
            self._reply(f"Бренд з id {bid} уже є в списку.")
            return
        entry = CommentedMap()
        entry["name"] = name
        entry["id"] = int(bid)
        if cats:
            entry["categories"] = self._flow(cats)
        self.brands.append(entry)
        if self._commit(f"додано {name}"):
            self._reply(f"✅ Додано: {self._brand_line(entry)} (id {bid}).\n"
                        f"Перший прохід лише запам'ятає поточні речі бренду, далі приходитимуть нові.")

    def _callback(self, data: str) -> None:
        kind, _, val = data.partition(":")
        if kind == "add":
            pend = self.state.pop("pending", None)
            if val == "none" or not pend:
                self._reply("Гаразд, нічого не додаю." if pend else "Цей вибір уже неактуальний.")
                return
            name = pend["options"].get(val)
            if not name:
                self._reply("Цей вибір уже неактуальний. Повтори /add.")
                return
            self._add(name, int(val), pend.get("cats") or [])
        elif kind == "cond":
            self.cmd_condition(val)

    def cmd_remove(self, arg: str) -> None:
        i = self._one(arg, "remove")
        if i is None:
            return
        name = self.brands[i]["name"]
        del self.brands[i]
        if self._commit(f"прибрано {name}"):
            self._reply(f"🗑 Прибрано {esc(name)}. Повернути: /add {esc(name)}")

    def _toggle(self, arg: str, on: bool) -> None:
        i = self._one(arg, "on" if on else "off")
        if i is None:
            return
        b = self.brands[i]
        if on:
            b.pop("enabled", None)
        else:
            b["enabled"] = False
        if self._commit(f"{'увімкнено' if on else 'призупинено'} {b['name']}"):
            self._reply(f"{'▶️ Увімкнено' if on else '⏸ Призупинено'}: {esc(b['name'])}")

    def cmd_off(self, arg: str) -> None:
        self._toggle(arg, False)

    def cmd_on(self, arg: str) -> None:
        self._toggle(arg, True)

    def cmd_condition(self, arg: str) -> None:
        if not arg:
            cur = (self.doc.get("defaults") or {}).get("min_condition")
            self._reply(f"Зараз: {esc(self._cond_text(cur))}. Обери мінімальний стан для всіх брендів:",
                        [[(f"{k} {v}", f"cond:{k}")] for k, v in rules.CONDITIONS.items()]
                        + [[("Будь-який", "cond:any")]])
            return
        m = re.fullmatch(r"(?:(.+?)\s+)?([1-5]|any|будь-який|default|як у всіх)", arg.strip(), re.I)
        if not m:
            self._reply("Формат: /condition 3 · /condition COS 2 · /condition COS default")
            return
        who, val = m.group(1), m.group(2).lower()
        value = None if val in ("any", "будь-який", "default", "як у всіх") else int(val)
        if who:
            i = self._one(who, "condition")
            if i is None:
                return
            b = self.brands[i]
            if value is None:
                b.pop("min_condition", None)
            else:
                b["min_condition"] = value
            if self._commit(f"стан {b['name']} → {value or 'як у всіх'}"):
                self._reply(f"✅ {esc(b['name'])}: стан {esc(self._cond_text(value)) if value else 'як у всіх'}.")
            return
        d = self.doc.setdefault("defaults", CommentedMap())
        if value is None:
            d.pop("min_condition", None)
        else:
            d["min_condition"] = value
        if self._commit(f"стан для всіх → {value or 'будь-який'}"):
            self._reply(f"✅ Стан для всіх брендів: {esc(self._cond_text(value))}. "
                        f"Бренди з власним станом не змінено.")

    def _sizes(self) -> dict:
        prof = self.doc.get("my_sizes")
        if prof is None:
            prof = (self.doc.get("defaults") or {}).get("sizes") or {}
        return {g: list(prof.get(g) or []) for g in ("одяг", "штани", "взуття")} if isinstance(prof, dict) \
            else {"id": list(prof)}

    def cmd_sizes(self, arg: str) -> None:
        if not arg:
            cur = self._sizes()
            self._reply("<b>Мої розміри</b>\n" + "\n".join(f"{esc(g)}: {esc(', '.join(map(str, v))) or '—'}"
                                                           for g, v in cur.items())
                        + "\n\nЗмінити: /sizes одяг L XL · /sizes штани W34 W36 · /sizes взуття 45 45.5 · "
                          "/sizes взуття -")
            return
        parts = [x.strip(",") for x in re.split(r"[\s;]+|,(?=\D)", arg) if x.strip(",")]  # «45,5» — число
        group = rules.SIZE_GROUP_ALIASES.get(parts[0].lower())
        if not group:
            self._reply("Перше слово — група: одяг, штани або взуття. Напр. /sizes одяг L XL")
            return
        values = [] if parts[1:] in ([], ["-"]) else parts[1:]
        if values:
            try:
                rules.resolve_sizes({group: values}, (self.doc.get("defaults") or {}).get("section", "men"), "sizes")
            except rules.ConfigError as e:
                self._reply(f"❌ {esc(e)}")
                return
        if self.doc.get("my_sizes") is None:
            self.doc["my_sizes"] = CommentedMap()
        prof = self.doc["my_sizes"]
        norm_vals = [str(v).upper().replace(",", ".") if group != "взуття" else str(v).replace(",", ".")
                     for v in values]
        if norm_vals:
            prof[group] = self._flow(norm_vals)
        else:
            prof.pop(group, None)
        if self._commit(f"розміри {group} → {' '.join(norm_vals) or '—'}"):
            self._reply(f"✅ {esc(group)}: {esc(', '.join(norm_vals)) or 'не шукаю'}. "
                        f"Перший прохід з новими розмірами лише запам'ятає поточні речі.")

    # ------------------------------------------------------------------ матеріали за категоріями
    _MAT_RX = re.compile(r"^(?P<cat>.+?)\s*(?P<op>:|\+|-(?=\s|$)|\boff\b|\bвимк\w*|\bневідомі\b)\s*(?P<rest>.*)$",
                         re.I)

    def _materials_text(self) -> str:
        cm = self.doc.get("category_materials") or {}
        if not cm:
            return "Правил матеріалів немає."
        lines = []
        for cat, spec in cm.items():
            parts = []
            if spec.get("only"):
                unk = " (без вказаного матеріалу — теж)" if spec.get("if_unknown") == "send" else ""
                parts.append(f"лише {', '.join(map(str, spec['only']))}{unk}")
            if spec.get("prefer"):
                parts.append(f"⭐ {', '.join(map(str, spec['prefer']))}")
            lines.append(f"<b>{esc(cat)}</b>: {esc('; '.join(parts)) or '—'}")
        return "\n".join(lines)

    def cmd_materials(self, arg: str) -> None:
        self._category_materials(arg, "only", "materials")

    def cmd_prefer(self, arg: str) -> None:
        self._category_materials(arg, "prefer", "prefer")

    def _category_materials(self, arg: str, key: str, verb: str) -> None:
        if not arg:
            self._reply("<b>Матеріали за категоріями</b>\n" + self._materials_text()
                        + f"\n\nЗмінити: /{verb} светри: вовна, кашемір · /{verb} светри + альпака · "
                          f"/{verb} светри - кашемір · /{verb} светри off")
            return
        m = self._MAT_RX.match(arg.strip())
        if not m:
            self._reply(f"Формат: /{verb} категорія: матеріал, матеріал · /{verb} категорія + матеріал · "
                        f"/{verb} категорія - матеріал · /{verb} категорія off")
            return
        cat, op, rest = m.group("cat").strip().lower(), m.group("op").lower(), m.group("rest")
        section = (self.doc.get("defaults") or {}).get("section", "men")
        try:
            rules.resolve_categories([cat], section, cat)
        except rules.ConfigError as e:
            self._reply(f"❌ {esc(e)}")
            return
        cm = self.doc.get("category_materials")
        if cm is None:
            self.doc["category_materials"] = cm = CommentedMap()
        spec = cm.get(cat)
        if spec is None:
            spec = CommentedMap()
        cur = [str(x) for x in (spec.get(key) or [])]
        if op.startswith("невідомі"):
            if key != "only":
                self._reply("«невідомі» стосується лише /materials.")
                return
            yes = rest.strip().lower() in ("так", "yes", "send", "надсилати", "+")
            spec["if_unknown"] = "send" if yes else "skip"
            new = cur
        else:
            vals = [v.strip().lower() for v in re.split(r"[,;]", rest) if v.strip()]
            if op in (":", "+", "-") and not vals:
                self._reply("Вкажи матеріали через кому. Відомі: " + esc(", ".join(rules.MATERIALS)))
                return
            try:
                vals = rules.resolve_material_names(vals, cat)
            except rules.ConfigError as e:
                self._reply(f"❌ {esc(e)}")
                return
            if op == ":":
                new = vals
            elif op == "+":
                new = list(dict.fromkeys(cur + vals))
            elif op == "-":
                new = [x for x in cur if x not in vals]
            else:                                   # off / вимкнути
                new = []
        if new:
            spec[key] = self._flow(new)
        else:
            spec.pop(key, None)
            if key == "only":
                spec.pop("if_unknown", None)
        if spec:
            cm[cat] = spec
        else:
            cm.pop(cat, None)
        if not cm:
            self.doc.pop("category_materials", None)
        label = "лише" if key == "only" else "⭐ пріоритет"
        if self._commit(f"матеріали {cat}: {label} {', '.join(new) or '—'}"):
            self._reply(f"✅ {esc(cat)}: {label} — {esc(', '.join(new)) or 'без обмежень'}\n\n" + self._materials_text())
