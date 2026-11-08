"""Shafa Watcher: один прохід перевірки. Запускається за розкладом (GitHub Actions / cron)."""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import os
import sys
import time
from zoneinfo import ZoneInfo

from . import rules
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


def build_caption(item: dict, d: dict | None, rule: rules.BrandRule) -> tuple[str, list[str], str]:
    url = absolute_url(item.get("url") or (d or {}).get("url") or f"/uk/item/{item['id']}")
    name = (d or {}).get("name") or item.get("name") or "Нова річ"
    brand = ((d or {}).get("brand") or item.get("brand") or {}).get("name") or rule.name
    sizes = [s.get("name") for s in ((d or {}).get("sizes") or item.get("sizes") or []) if s.get("name")]
    cond = ((d or {}).get("condition") or {}).get("name") or rules.CONDITIONS.get(item.get("condition"), "")
    price = (d or {}).get("price") or item.get("price")
    old = (d or {}).get("oldPrice") or item.get("oldPrice")
    disc = (d or {}).get("discountPercent") or item.get("discountPercent")
    mats = rules.materials_of(d)

    price_line = f"💰 <b>{fmt_price(price)} грн</b>"
    if old and float(old) > float(price or 0):
        price_line += f"  <s>{fmt_price(old)} грн</s>"
        if disc:
            price_line += f" (−{int(disc)}%)"
    lines = [f"🆕 <b>{esc(name)}</b>", f"🏷 {esc(brand)}" + (f" · розмір {esc(', '.join(sizes))}" if sizes else "")]
    if cond:
        lines.append(f"✨ Стан: {esc(cond)}")
    lines.append(price_line)
    if mats:
        lines.append(f"🧵 {esc(', '.join(mats))}")
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

    def heartbeat(self, hour: int, n_brands: int, n_groups: int) -> None:
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
                f"Брендів: {n_brands}, запитів за прохід: {n_groups}."
                + (f"\nНайбільша пауза між запусками: {gap:.0f} хв." if gap else ""))
        try:
            self.tg.text(text)
            self.h["heartbeat_date"] = today
            self.stats.clear()
        except Exception as e:  # noqa: BLE001
            log.error("heartbeat не надіслано: %s", e)


def run(args) -> int:
    cfg = rules.load(args.config)
    state = State(args.state)
    tg = Telegram(os.getenv("TG_TOKEN"), os.getenv("TG_CHAT"), dry_run=args.dry_run)
    if tg.dry_run:
        log.warning("TG_TOKEN/TG_CHAT не задані або --dry-run: повідомлення лише в лог")
    st = cfg.settings
    shafa = Shafa(min_delay=float(st.get("request_delay_sec", 1.5)))
    health = Health(state, tg)
    by_id = cfg.by_id()
    groups = cfg.groups()
    per_page = int(st.get("items_per_query", 100))
    max_pages = int(st.get("max_pages", 3))
    photos_n = int(st.get("photos", 3))

    # пауза між запусками (GitHub cron може запізнюватися)
    last_run = state.health.get("last_run")
    if last_run:
        gap = (time.time() - last_run) / 60
        state.stats["max_gap_min"] = max(state.stats.get("max_gap_min", 0), gap)
    health.count("runs")

    failed = 0
    notified = 0
    demo_left = args.demo
    for g in groups:
        ready = state.group_ready(g.key, g.brand_ids) and not args.demo
        r = g.rule
        items: list[dict] = []
        try:
            for page in range(1, max_pages + 1):
                batch, has_next = shafa.products(
                    brands=g.brand_ids, catalog=r.section, sizes=r.sizes, conditions=r.conditions,
                    price_to=r.max_price, price_from=r.min_price, characteristics=r.materials,
                    first=per_page, page=page)
                items += batch
                # Далі гортаємо лише якщо вся сторінка нова (великий потік між запусками).
                if not (ready and has_next and batch and all(not state.is_seen(i["id"]) for i in batch)):
                    break
        except ShafaError as e:
            failed += 1
            health.count("errors")
            fails = state.health.setdefault("group_fails", {})
            fails[g.key] = fails.get(g.key, 0) + 1
            log.error("група %s: %s", g.key, e)
            if e.status in (403, 429):
                health.alert("blocked", f"Shafa відповідає {e.status}. Можливе блокування IP раннера. "
                                        "Див. README → «Якщо Shafa блокує».")
            elif fails[g.key] >= 3:
                health.alert(f"group:{g.key}", f"запит для брендів {g.brand_ids} падає {fails[g.key]} рази поспіль: {e}")
            continue
        state.health.setdefault("group_fails", {})[g.key] = 0
        health.resolve(f"group:{g.key}", f"запит для брендів {g.brand_ids} знову працює")

        empties = state.health.setdefault("group_empty", {})
        if not items:
            empties[g.key] = empties.get(g.key, 0) + 1
            if empties[g.key] >= int(st.get("empty_runs_alert", 12)):
                health.alert(f"empty:{g.key}", f"для брендів {g.brand_ids} Shafa повертає 0 товарів "
                                               f"{empties[g.key]} запусків поспіль. Перевір id і фільтри.")
        else:
            empties[g.key] = 0

        new = [i for i in items if not state.is_seen(i["id"])]
        health.count("new_ids", len(new) if ready else 0)
        log.info("група %s (%d брендів): отримано %d, нових %d%s", g.key, len(g.brand_ids), len(items),
                 len(new), "" if ready or args.demo else " — перший прохід, лише запам'ятовую")
        if not ready and not args.demo:
            for i in items:
                state.mark(i["id"])
            state.set_group_ready(g.key, g.brand_ids)
            continue

        for item in (items if args.demo else reversed(new)):  # від старших до новіших
            rule = by_id.get((item.get("brand") or {}).get("id"))
            if not rule:
                state.mark(item["id"])
                continue
            reason = rules.quick_check(item, rule)
            d = None
            if not reason:
                try:
                    d = shafa.details(item["id"])
                except ShafaError as e:
                    log.warning("картка %s недоступна: %s", item["id"], e)
                reason = rules.detail_check(item, d, rule)
            if reason:
                log.info("  пропуск %s «%s»: %s", item["id"], item.get("name"), reason)
                if not args.demo:
                    state.mark(item["id"])
                continue
            caption, photos, url = build_caption(item, d, rule)
            try:
                tg.listing(caption, photos[:photos_n], url)
            except Exception as e:  # noqa: BLE001
                # Не позначаємо як бачене — спробуємо наступного запуску.
                log.error("Telegram: %s", e)
                health.alert("telegram", f"не вдалося надіслати повідомлення: {e}")
                continue
            notified += 1
            if args.demo:
                demo_left -= 1
                if demo_left <= 0:
                    break
            else:
                state.mark(item["id"])
        if args.demo and demo_left <= 0:
            break

    health.count("notified", notified)
    health.count("requests", shafa.requests_made)
    if groups and failed == len(groups):
        health.alert("all_failed", "усі запити до Shafa впали в цьому запуску")
    elif failed == 0:
        health.resolve("all_failed", "запити до Shafa знову працюють")
        health.resolve("blocked", "Shafa знову відповідає нормально")

    if not args.demo:
        state.health["last_run"] = time.time()
        health.heartbeat(int(st.get("heartbeat_hour_kyiv", 9)), len(cfg.enabled), len(groups))
        state.prune({g.key for g in groups})
        state.save()
    log.info("готово: груп %d, помилок %d, надіслано %d, запитів до Shafa %d",
             len(groups), failed, notified, shafa.requests_made)
    return 1 if groups and failed == len(groups) else 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Shafa Watcher")
    p.add_argument("--config", default="brands.yaml")
    p.add_argument("--state", default="state.json")
    p.add_argument("--dry-run", action="store_true", help="не слати в Telegram, лише лог")
    p.add_argument("--demo", type=int, default=0,
                   help="надіслати N найсвіжіших відповідних товарів, ігноруючи стан (для перевірки вигляду)")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
