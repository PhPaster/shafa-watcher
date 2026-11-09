"""Офлайн-тести логіки (без мережі): python -m unittest discover -s tests -v"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from shafa_watch import main, rules  # noqa: E402

NOW = dt.datetime.now(dt.timezone.utc)


def item(pid, brand, slug, hours_ago=1, name="річ"):
    return {"id": pid, "url": f"/uk/item/{pid}", "name": name, "price": 1000, "condition": 2,
            "createdAt": (NOW - dt.timedelta(hours=hours_ago)).isoformat(), "statusTitle": "AVAILABLE",
            "catalogSlug": slug, "brand": {"id": brand, "name": f"B{brand}"} if brand else None, "sizes": []}


class FakeShafa:
    catalog: list[dict] = []

    def __init__(self, *a, **k):
        self.requests_made = 0

    def products(self, *, brands, catalog, **k):
        self.requests_made += 1
        out = [i for i in self.catalog
               if (not brands or (i["brand"] or {}).get("id") in brands)
               and (catalog in (None, "men") or i["catalogSlug"].startswith(catalog))]
        return sorted(out, key=lambda i: i["createdAt"], reverse=True), False

    def details(self, pid):
        self.requests_made += 1
        return {"description": "100% вовна" if pid % 2 else "бавовна", "characteristics": []}


class FakeTelegram:
    sent: list[str] = []

    def __init__(self, *a, **k):
        self.dry_run = False

    def listing(self, caption, photos, url):
        FakeTelegram.sent.append(url.replace("https://shafa.ua", ""))

    def text(self, t):
        pass


def write(tmp: Path, body: str) -> Path:
    p = tmp / "brands.yaml"
    p.write_text(textwrap.dedent(body), encoding="utf-8")
    return p


BASE = """
my_sizes:
  одяг: [L, XL]
  штани: [W32]
defaults:
  min_condition: 3
  max_age_hours: 72
brands:
  - name: A
    id: 1
    categories: [джинси]
{extra}
searches:
  - name: Вовна
    categories: [светри]
    materials_include: "(?<!ба)вовн"
"""


class RunTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        main.Shafa = FakeShafa
        main.Telegram = FakeTelegram
        FakeTelegram.sent = []
        FakeShafa.catalog = [item(10, 1, "shtany-i-shorty/dzhinsy", 5), item(11, 1, "kofti/svitery", 5)]

    def run_once(self, cfg: Path, demo=0):
        args = argparse.Namespace(config=str(cfg), state=str(self.tmp / "state.json"), dry_run=False, demo=demo)
        return main.run(args)

    def test_first_run_silent_then_dedup_across_rules(self):
        cfg = write(self.tmp, BASE.format(extra=""))
        self.run_once(cfg)
        self.assertEqual(FakeTelegram.sent, [], "перший прохід нічого не надсилає")
        # 21: светр бренду A з вовною — A його відкидає (не джинси), але пошук «Вовна» бере. Має прийти 1 раз.
        # 22: джинси A. 24: светр з бавовною (парний id у фейку) — нікому. 25: старий «піднятий» — відсіяти.
        FakeShafa.catalog += [item(21, 1, "kofti/svitery"), item(22, 1, "shtany-i-shorty/dzhinsy"),
                              item(24, 7, "kofti/svitery"), item(25, 1, "shtany-i-shorty/dzhinsy", 100)]
        self.run_once(cfg)
        self.assertEqual(sorted(FakeTelegram.sent), ["/uk/item/21", "/uk/item/22"])
        self.run_once(cfg)
        self.assertEqual(len(FakeTelegram.sent), 2, "повторний запуск не дублює")

    def test_new_brand_in_existing_group_is_silent_but_old_brand_works(self):
        cfg = write(self.tmp, BASE.format(extra=""))
        FakeShafa.catalog.append(item(30, 2, "shtany-i-shorty/dzhinsy", 3))
        self.run_once(cfg)
        cfg = write(self.tmp, BASE.format(extra="  - name: B\n    id: 2\n    categories: [джинси]"))
        FakeShafa.catalog += [item(32, 1, "shtany-i-shorty/dzhinsy"), item(33, 2, "shtany-i-shorty/dzhinsy")]
        self.run_once(cfg)
        self.assertEqual(FakeTelegram.sent, ["/uk/item/32"], "старий бренд шле, новий — тихий перший прохід")
        FakeShafa.catalog.append(item(34, 2, "shtany-i-shorty/dzhinsy", 0.5))
        self.run_once(cfg)
        self.assertEqual(FakeTelegram.sent, ["/uk/item/32", "/uk/item/34"])

    def test_demo_does_not_touch_state(self):
        cfg = write(self.tmp, BASE.format(extra=""))
        self.run_once(cfg, demo=2)
        self.assertEqual(len(FakeTelegram.sent), 2)
        self.assertFalse((self.tmp / "state.json").exists())


class ConfigTest(unittest.TestCase):
    def load(self, body):
        tmp = Path(tempfile.mkdtemp())
        return rules.load(write(tmp, body))

    def test_sizes_and_categories(self):
        cfg = self.load("""
        my_sizes: {одяг: [L, XL/50], штани: [32, W33], взуття: [43, "42,5"]}
        brands:
          - {name: X, id: 5, categories: [кофти, взуття]}
        """)
        r = cfg.rules[0]
        self.assertEqual(r.sizes, [150, 151, 163, 164, 178, 242])
        self.assertIn("kofty/*", r.categories)
        self.assertTrue(rules.category_ok("kofty/longsliv", r.categories))
        self.assertTrue(rules.category_ok("obuv/krossovki", r.categories))
        self.assertFalse(rules.category_ok("shtany-i-shorty/dzhinsy", r.categories))

    def test_search_overrides_only_given_size_group(self):
        cfg = self.load("""
        my_sizes: {одяг: [L], взуття: [43]}
        brands:
          - name: V
            id: 9
            searches:
              - {categories: [взуття], sizes: {взуття: [42.5]}}
              - {categories: [сорочки]}
        """)
        self.assertEqual(cfg.rules[0].sizes, [150, 242])
        self.assertEqual(cfg.rules[1].sizes, [150, 178])
        self.assertEqual(len(cfg.groups()), 2)

    def test_categories_do_not_split_groups(self):
        cfg = self.load("""
        my_sizes: {одяг: [L]}
        brands:
          - {name: A, id: 1, categories: [джинси]}
          - {name: B, id: 2, categories: [светри]}
          - {name: C, id: 3}
        """)
        self.assertEqual(len(cfg.groups()), 1)
        self.assertEqual(cfg.groups()[0].brand_ids, [1, 2, 3])

    def test_brandless_catalog_narrowing(self):
        cfg = self.load("""
        searches:
          - {name: s1, categories: [светри]}
          - {name: s2, categories: [джинси]}
          - {name: s3, categories: [лонгсліви]}
          - {name: s4, categories: [джинси, светри]}
        """)
        self.assertEqual([r.catalog for r in cfg.rules], ["kofti", "shtany-i-shorty/dzhinsy", "kofti", "men"])

    def test_errors(self):
        for body, msg in [
            ("brands: [{name: X}]", "lookup.py fill"),
            ("brands: [{name: X, id: 1, categories: [шкарпетки]}]", "невідома категорія"),
            ("my_sizes: {одяг: [XXS]}\nbrands: [{name: X, id: 1}]", "невідомий розмір"),
            ("brands: [{name: X, id: 1, colour: red}]", "невідомі поля"),
            ("brands: [{name: X, id: 1}, {name: Y, id: 1}]", "двічі"),
            ("searches: [{name: all}]", "увесь сайт"),
        ]:
            with self.assertRaises(rules.ConfigError, msg=body) as cm:
                self.load(body)
            self.assertIn(msg, str(cm.exception))


if __name__ == "__main__":
    unittest.main()
