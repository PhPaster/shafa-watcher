"""Shafa Watcher: один прохід перевірки. Запускається за розкладом (GitHub Actions / cron)."""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import os
import sys
import time
from zoneinfo import ZoneInfo

from pathlib import Path

from . import rules
from .bot import Bot
from .shafa import Shafa, ShafaError, absolute_url
from .state import State
from .telegram import Telegram, esc

log = logging.getLogger("shafa_watch")
KYIV = ZoneInfo("Europe/Kyiv")
ALERT_COOLDOWN = 6 * 3600


def fmt_price(v) -> str:
    if v is None:
        return ""
    v = float(v)
    return f"{v:,.0f}".replace(",", " ")


def build_caption(item: dict, d: dict | None, rule: rules.Rule, priority: bool | None = None,
                  found_materials: list[str] | None = None) -> tuple[str, list[str], str]:
    url = absolute_url(item.get("url") or (d or {}).get("url") or f"/uk/item/{item['id']}")
    name = (d or {}).get("name") or item.get("name") or "Нова річ"
    brand = ((d or {}).get("brand") or item.get("brand") or {}).get("name") or next(iter(rule.brands.values()), "")
    sizes = [s.get("name") for s in ((d or {}).get("sizes") or item.get("sizes") or []) if s.get("name")]
    cond = ((d or {}).get("condition") or {}).get("name") or rules.CONDITIONS.get(item.get("condition"), "")
    price = (d or {}).get("price") or item.get("price")
    old = (d or {}).get("oldPrice") or item.get("oldPrice")
    disc = (d or {}).get("discountPercent") or item.get("discountPercent")
    mats = rules.materials_of(d) or [m.capitalize() for m in (found_materials or [])]

    price_line = f"💰 <b>{fmt_price(price)} грн</b>"
    if old and float(old) > float(price or 0):
        price_line += f"  <s>{fmt_price(old)} грн</s>"
        if disc:
            price_line += f" (−{int(disc)}%)"
    tag = " · ".join(x for x in (esc(brand), f"розмір {esc(', '.join(sizes))}" if sizes else "") if x)
    lines = [f"{'⭐' if priority else '🆕'} <b>{esc(name)}</b>"] + ([f"🏷 {tag}"] if tag else [])
    if cond:
        lines.append(f"✨ Стан: {esc(cond)}")
    lines.append(price_line)
    if mats:
        lines.append(f"🧵 {esc(', '.join(mats))}")
    if rule.brandless:
        lines.append(f"🔎 {esc(rule.label)}")
    lines.append(f'🔗 <a href="{esc(url)}">{esc(url)}</a>')
    caption = "\n".join(lines)[:1024]

    photos = [p.get("originalUrl") or p.get("thumbnailUrl") for p in ((d or {}).get("photos") or [])]
    photos = [p for p in photos if p]
    if not photos and item.get("thumbnail"):
        photos = [item["thumbnail"]]
    return caption, photos, url


class Health:
    """Сповіщення про збої з охолодженням і щоденний heartbeat."""

    def __init__(self, state: State, tg: Telegram):
        self.h = state.health
        self.stats = state.stats
        self.tg = tg

    def alert(self, kind: str, text: str) -> None:
        last = self.h.setdefault("alerts", {}).get(kind, 0)
        if time.time() - last < ALERT_COOLDOWN:
            return
        self.h["alerts"][kind] = time.time()
        try:
            self.tg.text(f"⚠️ <b>Shafa Watcher</b>: {esc(text)}")
        except Exception as e:  # noqa: BLE001
            log.error("не вдалося надіслати алерт: %s", e)

    def resolve(self, kind: str, text: str) -> None:
        if self.h.get("alerts", {}).pop(kind, None):
            try:
                self.tg.text(f"✅ <b>Shafa Watcher</b>: {esc(text)}")
            except Exception as e:  # noqa: BLE001
                log.error("не вдалося надіслати відновлення: %s", e)

    def count(self, key: str, n: int = 1) -> None:
        self.stats[key] = self.stats.get(key, 0) + n

    def heartbeat(self, hour: int, n_brands: int, n_rules: int, n_groups: int) -> None:
        now = dt.datetime.now(KYIV)
        today = now.date().isoformat()
        if now.hour < hour or self.h.get("heartbeat_date") == today:
            return
        s = self.stats
        gap = s.get("max_gap_min")
        text = (f"💓 <b>Shafa Watcher працює</b>\n"
                f"За добу: запусків {s.get('runs', 0)}, нових сповіщень {s.get('notified', 0)}, "
                f"переглянуто нових id {s.get('new_ids', 0)}, запитів до Shafa {s.get('requests', 0)}, "
                f"помилок {s.get('errors', 0)}.\n"
                f"Брендів: {n_brands}, правил: {n_rules}, запитів за прохід: {n_groups}."
                + (f"\nНайбільша пауза між запусками: {gap:.0f} хв." if gap else ""))
        try:
            self.tg.text(text)
            self.h["heartbeat_date"] = today
            self.stats.clear()
        except Exception as e:  # noqa: BLE001
            log.error("heartbeat не надіслано: %s", e)


def young_share(batch: list[dict], hours: float) -> float:
    ages = [rules._age_hours(x.get("createdAt")) for x in batch]
    return sum(1 for a in ages if a is not None and a <= hours) / max(len(ages), 1)


def fetch_group(shafa: Shafa, g: rules.Group, state: State, st: dict, demo: bool,
                backfill_h: float = 0, force_backfill: bool = False) -> list[dict]:
    """backfill_h > 0: для групи в першому проході (або force_backfill) гортати, поки на сторінці
    більшість речей молодші за backfill_h годин (до settings.backfill_max_pages сторінок)."""
    r = g.server
    per_page = int(st.get("items_per_query", 100))
    ready = state.any_ready(g.key, g.brand_ids) and not demo
    bf = bool(backfill_h) and not demo and (force_backfill or not ready)
    max_pages = int(st.get("backfill_max_pages", 5)) if bf else int(st.get("max_pages", 3))
    variants = r.variants()            # напр. «вживані від усіх» + «нові від приватних» — один HTTP-запит
    active = list(range(len(variants)))
    items: list[dict] = []
    seen_ids: set[int] = set()
    for page in range(1, max_pages + 1):
        res = shafa.products_multi(
            [variants[i] for i in active], brands=g.brand_ids or None, catalog=r.catalog, sizes=r.sizes,
            price_to=r.max_price, price_from=r.min_price, first=per_page, page=page, search_text=r.text)
        nxt = []
        for i, (batch, has_next) in zip(active, res):
            items += [x for x in batch if x["id"] not in seen_ids]
            seen_ids.update(x["id"] for x in batch)
            # Далі гортаємо лише якщо вся сторінка нова (великий потік між запусками),
            # а при довантаженні — поки більшість речей на сторінці молодші за backfill_h.
            if has_next and batch and (
                    (bf and young_share(batch, backfill_h) >= 0.5)
                    or (ready and not bf and all(not state.is_seen(x["id"]) for x in batch))):
                nxt.append(i)
        active = nxt
        if not active:
            break
    return items


def demo_order(ids: list[int], found: dict, sources: dict) -> list[int]:
    """Для демо — по черзі з кожного правила (найсвіжіші першими), щоб показати різні приклади."""
    by_label: dict[str, list[int]] = {}
    for pid in ids:
        item = found[pid]
        rule = next((r for g in sources[pid] for r in g.rules
                     if r.matches_brand(item) and not rules.quick_check(item, r)), None)
        if rule:
            by_label.setdefault(rule.label, []).append(pid)
    out: list[int] = []
    queues = list(by_label.values())
    while any(queues):
        for q in queues:
            if q:
                out.append(q.pop(0))
    return out


def select_due(groups: list[rules.Group], cfg: rules.Config, state: State) -> list[rules.Group]:
    """Пакети з інтервалом ≤10 хв — щоразу. Повільніші — коли настав їхній час, але не більше
    settings.max_slow_requests_per_run за прохід (найбільш прострочені першими), щоб прохід лишався коротким."""
    now = time.time()
    last = state.health.setdefault("group_last", {})
    fast, slow = [], []
    for g in groups:
        interval = cfg.interval_min(g.package)
        if interval <= 10:
            fast.append(g)
            continue
        age_min = (now - last.get(g.id, 0)) / 60
        if age_min >= interval - 2:            # допуск на запізнення cron
            slow.append((age_min / interval, g))
    slow.sort(key=lambda x: -x[0])
    budget = int(cfg.settings.get("max_slow_requests_per_run", 6))
    return fast + [g for _, g in slow[:budget]]


def run(args) -> int:
    state = State(args.state)
    tg = Telegram(os.getenv("TG_TOKEN"), os.getenv("TG_CHAT"), dry_run=args.dry_run)
    if tg.dry_run:
        log.warning("TG_TOKEN/TG_CHAT не задані або --dry-run: повідомлення лише в лог")
    shafa = Shafa(min_delay=float((rules.load(args.config).settings or {}).get("request_delay_sec", 1.5)))

    # Команди з Telegram (/add, /remove, /condition, /sizes…) змінюють brands.yaml до запитів.
    if not args.demo:
        changes = Bot(tg, args.config, state, shafa).process()
        if changes:
            log.info("бот змінив brands.yaml: %s", "; ".join(changes))
            Path(args.config).with_name(".bot_changes").write_text("\n".join(changes), encoding="utf-8")
    cfg = rules.load(args.config)
    st = cfg.settings
    health = Health(state, tg)
    groups = cfg.groups()
    force_bf = float(getattr(args, "backfill", 0) or 0)               # разове довантаження всіх брендів за N годин
    backfill_h = force_bf or float(st.get("backfill_hours", 0) or 0)   # перший прохід нового бренду
    due = groups if force_bf else select_due(groups, cfg, state)
    if len(due) < len(groups):
        log.info("за розкладом пакетів: %d з %d груп", len(due), len(groups))
    photos_n = int(st.get("photos", 3))

    # пауза між запусками (GitHub cron може запізнюватися)
    last_run = state.health.get("last_run")
    if last_run and not args.demo:
        gap = (time.time() - last_run) / 60
        state.stats["max_gap_min"] = max(state.stats.get("max_gap_min", 0), gap)
    health.count("runs")

    # 1. Запити: кожна група — один запит (до 3 сторінок). Товар може прийти з кількох груп.
    found: dict[int, dict] = {}
    sources: dict[int, list[rules.Group]] = {}
    ok_groups: list[rules.Group] = []
    failed = 0
    for g in due:
        try:
            items = fetch_group(shafa, g, state, st, bool(args.demo), backfill_h, bool(force_bf))
        except ShafaError as e:
            failed += 1
            health.count("errors")
            fails = state.health.setdefault("group_fails", {})
            fails[g.id] = fails.get(g.id, 0) + 1
            log.error("група %s [%s]: %s", g.id, g.label(), e)
            if e.status in (403, 429):
                health.alert("blocked", f"Shafa відповідає {e.status}. Можливе блокування IP раннера. "
                                        "Див. README → «Якщо Shafa блокує».")
            elif fails[g.id] >= 3:
                health.alert(f"group:{g.id}", f"запит [{g.label()}] падає {fails[g.id]} рази поспіль: {e}")
            continue
        ok_groups.append(g)
        state.health.setdefault("group_last", {})[g.id] = time.time()
        state.health.setdefault("group_fails", {})[g.id] = 0
        health.resolve(f"group:{g.id}", f"запит [{g.label()}] знову працює")

        # «0 товарів N разів поспіль» підозріло лише для групи, яка раніше щось повертала:
        # у нішевого бренду в моїх розмірах порожня видача — норма.
        empties = state.health.setdefault("group_empty", {})
        nonempty = state.health.setdefault("group_nonempty", {})
        if not items:
            empties[g.id] = empties.get(g.id, 0) + 1
            if nonempty.get(g.id) and empties[g.id] >= int(st.get("empty_runs_alert", 12)):
                health.alert(f"empty:{g.id}", f"для [{g.label()}] Shafa повертає 0 товарів "
                                              f"{empties[g.id]} запусків поспіль. Перевір id і фільтри.")
        else:
            empties[g.id] = 0
            nonempty[g.id] = True
            health.resolve(f"empty:{g.id}", f"[{g.label()}] знову повертає товари")
        n_new = sum(1 for i in items if not state.is_seen(i["id"]))
        fresh = not state.any_ready(g.key, g.brand_ids)
        note = ""
        if force_bf:
            note = f" — довантаження за {force_bf:g} год"
        elif fresh and not args.demo:
            note = f" — перший прохід, надсилаю за останні {backfill_h:g} год" if backfill_h \
                else " — перший прохід, лише запам'ятовую"
        log.info("група %s [%s]: отримано %d, нових %d%s", g.id, g.label(), len(items), n_new, note)
        for i in items:
            found.setdefault(i["id"], i)
            sources.setdefault(i["id"], []).append(g)

    # 2. Нові товари → правила груп, що їх повернули → фільтри → Telegram. Одна річ = одне повідомлення.
    def young(pid) -> bool:
        a = rules._age_hours(found[pid].get("createdAt"))
        return bool(backfill_h) and a is not None and a <= backfill_h

    # Разове довантаження переглядає й уже бачені речі (надіслані відсіє антиповтор назви й ціни).
    ids = [pid for pid in found if args.demo or not state.is_seen(pid) or (force_bf and young(pid))]
    ids.sort(key=lambda pid: (found[pid].get("createdAt") or "", pid), reverse=bool(args.demo))
    if args.demo:
        ids = demo_order(ids, found, sources)
    notified = 0
    considered = 0
    for pid in ids:
        item = found[pid]
        bid = (item.get("brand") or {}).get("id")
        cands: list[rules.Rule] = []
        for g in sources[pid]:
            if args.demo or force_bf or state.ready(g.key, bid if g.brand_ids else None) or young(pid):
                cands += [r for r in g.rules if r.matches_brand(item) and r not in cands]
        if not cands:   # перший прохід для бренду/групи, річ старша за backfill_hours — лише запам'ятати
            if not args.demo:
                state.mark(pid)
            continue
        considered += 1
        passing, reasons = [], []
        for r in cands:
            reason = rules.quick_check(item, r)
            (reasons if reason else passing).append(reason or r)
        d = None
        if passing:
            try:
                d = shafa.details(pid)
            except ShafaError as e:
                log.warning("картка %s недоступна: %s", pid, e)
            ok = []
            for r in passing:
                reason = rules.detail_check(item, d, r)
                (reasons if reason else ok).append(reason or r)
            passing = ok
        priority, mats = None, []
        if passing:
            mreason, priority, mats = rules.material_check(item, d, cfg.category_materials)
            mreason = mreason or rules.measure_check(item, d, cfg.measurements)
            if mreason:
                reasons.append(mreason)
                passing = []
        if not passing:
            log.info("  пропуск %s «%s»: %s", pid, item.get("name"), "; ".join(dict.fromkeys(reasons)))
            if not args.demo:
                state.mark(pid)
            continue
        rule = passing[0]
        tkey = f"{rules.norm(item.get('name') or '')[:60]}|{int(float(item.get('price') or 0))}"
        if not args.demo and state.title_seen(tkey):
            log.info("  пропуск %s «%s»: повтор назви й ціни за 7 днів", pid, item.get("name"))
            state.mark(pid)
            continue
        caption, photos, url = build_caption(item, d, rule, priority=priority, found_materials=mats)
        try:
            tg.listing(caption, photos[:photos_n], url, silent=priority is False)
        except Exception as e:  # noqa: BLE001
            # Не позначаємо як бачене — спробуємо наступного запуску.
            log.error("Telegram: %s", e)
            health.alert("telegram", f"не вдалося надіслати повідомлення: {e}")
            continue
        notified += 1
        log.info("  ✉ %s «%s» [%s]", pid, item.get("name"), rule.label)
        if args.demo:
            if notified >= args.demo:
                break
        else:
            state.mark(pid)
            state.mark_title(tkey)
            health.resolve("telegram", "Telegram знову приймає повідомлення")

    if force_bf and not args.demo:
        try:
            tg.text(f"📦 <b>Довантаження за {force_bf:g} год</b> завершено: переглянуто {considered}, "
                    f"надіслано {notified}. Далі — лише нові речі кожні 10 хв.")
        except Exception as e:  # noqa: BLE001
            log.error("підсумок довантаження: %s", e)
    health.count("new_ids", considered)
    health.count("notified", notified)
    health.count("requests", shafa.requests_made)
    if due and failed == len(due):
        health.alert("all_failed", "усі запити до Shafa впали в цьому запуску")
    elif failed == 0:
        health.resolve("all_failed", "запити до Shafa знову працюють")
        health.resolve("blocked", "Shafa знову відповідає нормально")

    if not args.demo and os.getenv("GITHUB_EVENT_NAME") in ("schedule", "workflow_dispatch") and not state.health.get("schedule_started"):
        try:
            tg.text(f"🚀 <b>Shafa Watcher запущено</b> за розкладом (кожні 10 хв).\n"
                    f"Брендів: {cfg.brand_count}, правил: {len(cfg.enabled)}, запитів за прохід: {len(groups)}.\n"
                    f"Перший прохід для кожного бренду лише запам'ятовує поточні речі; далі приходитимуть нові. "
                    f"Звіт «я працюю» — щодня після {int(st.get('heartbeat_hour_kyiv', 9))}:00. /help — команди.")
            state.health["schedule_started"] = time.time()
        except Exception as e:  # noqa: BLE001
            log.error("стартове повідомлення: %s", e)

    if not args.demo:
        for g in ok_groups:
            state.set_ready(g.key, g.brand_ids)
        state.health["last_run"] = time.time()
        health.heartbeat(int(st.get("heartbeat_hour_kyiv", 9)), cfg.brand_count, len(cfg.enabled), len(groups))
        active: dict[str, set[int]] = {}
        for g in groups:
            active.setdefault(g.key, set()).update(g.brand_ids)
        state.prune(set(active))
        live = {g.id for g in groups}
        state.health["group_last"] = {k: v for k, v in state.health.get("group_last", {}).items() if k in live}
        state.prune_brands(active)
        state.save()
    log.info("готово: груп %d, помилок %d, розглянуто нових %d, надіслано %d, запитів до Shafa %d",
             len(groups), failed, considered, notified, shafa.requests_made)
    return 1 if due and failed == len(due) else 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Shafa Watcher")
    p.add_argument("--config", default="brands.yaml")
    p.add_argument("--state", default="state.json")
    p.add_argument("--dry-run", action="store_true", help="не слати в Telegram, лише лог")
    p.add_argument("--demo", type=int, default=0,
                   help="надіслати N найсвіжіших відповідних товарів, ігноруючи стан (для перевірки вигляду)")
    p.add_argument("--backfill", type=float, default=0,
                   help="разово: усі бренди, надіслати відповідні речі за останні N годин (надіслані раніше — ні)")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
