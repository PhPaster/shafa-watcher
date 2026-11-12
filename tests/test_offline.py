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


def item(pid, brand, slug, hours_ago=1, name=None):
    return {"id": pid, "url": f"/uk/item/{pid}", "name": name or f"річ {pid}", "price": 1000, "condition": 2,
            "createdAt": (NOW - dt.timedelta(hours=hours_ago)).isoformat(), "statusTitle": "AVAILABLE",
            "catalogSlug": slug, "brand": {"id": brand, "name": f"B{brand}"} if brand else None, "sizes": []}


class FakeShafa:
    catalog: list[dict] = []

    def __init__(self, *a, **k):
        self.requests_made = 0

    def products(self, *, brands, catalog, conditions=None, **k):
        out = [i for i in self.catalog
               if (not brands or (i["brand"] or {}).get("id") in brands)
               and (catalog in (None, "men") or i["catalogSlug"].startswith(catalog))
               and (not conditions or i["condition"] in conditions)]
        return sorted(out, key=lambda i: i["createdAt"], reverse=True), False

    def products_multi(self, variants, *, brands, catalog, **k):
        return self.products_batch([dict(variants=variants, brands=brands, catalog=catalog)])[0]

    def products_batch(self, queries):
        self.requests_made += 1          # один HTTP-запит на всі запити й варіанти (аліаси)
        self.batches = getattr(self, "batches", []) + [len(queries)]
        self.variants_seen = queries[-1]["variants"]
        return [[self.products(brands=q["brands"], catalog=q["catalog"], conditions=c) for c, _ in q["variants"]]
                for q in queries]

    def details(self, pid):
        self.requests_made += 1
        return {"description": "100% вовна" if pid % 2 else "бавовна", "characteristics": []}


class FakeTelegram:
    sent: list[str] = []

    def __init__(self, *a, **k):
        self.dry_run = False
        self.chat_id = "1"

    def listing(self, caption, photos, url, silent=False):
        FakeTelegram.sent.append(url.replace("https://shafa.ua", ""))

    def text(self, t):
        pass

    def call(self, method, payload, with_chat=True):
        return {"ok": True, "result": []}


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

    def test_groups_batched_in_one_request(self):
        body = BASE.format(extra="  - name: B\n    id: 2\n    package: інший\n    categories: [джинси]").replace(
            "my_sizes:", "settings:\n  packages: {звичайні: 10, інший: 10}\nmy_sizes:")
        cfg = write(self.tmp, body)
        # 3 групи (A, B, пошук «Вовна») × 2 варіанти продавця… тут seller any → 3 аліаси — один HTTP-запит
        fs = FakeShafa()
        due = rules.load(cfg).groups()
        res = main.prefetch_first_pages(fs, due, {"aliases_per_request": 10})
        self.assertEqual(fs.requests_made, 1)
        self.assertEqual(set(res), {g.id for g in due})
        fs2 = FakeShafa()
        main.prefetch_first_pages(fs2, due, {"aliases_per_request": 2})
        self.assertEqual(fs2.batches, [2], "пачка до 2 аліасів; група-одиначка йде звичайним запитом")

    def test_also_categories_and_all_brands_search(self):
        cfg = rules.loads("""
defaults: {also_categories: [худі]}
brands:
  - {name: A, id: 1, categories: [джинси]}
  - {name: B, id: 2}
  - {name: C, id: 3, categories: [джинси], also_categories: []}
  - {name: D, id: 4, enabled: false}
searches:
  - {name: Лляні, categories: [сорочки]}
  - {name: Шапки, brands: all, section: holovni-ubory/shapky, sizes: [320, 327], materials: [1602],
     characteristics: [2418]}
  - {name: Піжами, brands: [1, 734], section: odezhda-dlia-doma-i-sna/pizhamy, sizes: [150, 151]}
""")
        by = {r.label: r for r in cfg.rules}
        self.assertIn("kofti/hudi", by["A"].categories)
        self.assertEqual(by["B"].categories, [], "без категорій — і так усе")
        self.assertNotIn("kofti/hudi", by["C"].categories)
        self.assertEqual(by["Лляні"].categories, ["rubashki/rubashki"], "пошуки без бренду — без also")
        self.assertEqual(sorted(by["Піжами"].brands), [1, 734])
        self.assertEqual(by["Піжами"].variants(), [([], [])])
        self.assertEqual(by["Шапки"].variants(), [([], [1602, 2418])], "матеріал І стать")
        hats = by["Шапки"]
        self.assertEqual(sorted(hats.brands), [1, 2, 3, 4], "усі бренди зі списку, і вимкнені теж")
        self.assertEqual(hats.catalog, "holovni-ubory/shapky")
        self.assertEqual(hats.sizes, [320, 327])

    def test_title_in_description(self):
        r = rules.loads("""
brands:
  - name: U
    id: 1
    searches: [{name: U, title_include: 'uniqlo\\s*u\\b', title_in_description: true}]
""").rules[0]
        it = item(1, 1, "kofti/hudi", name="Худі")
        self.assertIsNone(rules.quick_check(it, r), "назва не обовʼязкова — перевірка в картці")
        self.assertIsNone(rules.detail_check(it, {"description": "Колекція Uniqlo U"}, r))
        self.assertIn("опис", rules.detail_check(it, {"description": "базове"}, r))

    def test_first_pass_backfill_sends_last_hours(self):
        body = BASE.format(extra="").replace("my_sizes:", "settings:\n  backfill_hours: 72\nmy_sizes:")
        cfg = write(self.tmp, body)
        FakeShafa.catalog.append(item(12, 1, "shtany-i-shorty/dzhinsy", 80))   # старше 72 год — ні
        self.run_once(cfg)
        self.assertEqual(sorted(FakeTelegram.sent), ["/uk/item/10", "/uk/item/11"])
        self.run_once(cfg)
        self.assertEqual(len(FakeTelegram.sent), 2, "другий прохід не дублює")

    def test_manual_backfill_resends_nothing_twice(self):
        cfg = write(self.tmp, BASE.format(extra=""))
        self.run_once(cfg)
        self.assertEqual(FakeTelegram.sent, [], "без backfill_hours перший прохід тихий")
        args = argparse.Namespace(config=str(cfg), state=str(self.tmp / "state.json"), dry_run=False, demo=0,
                                  backfill=72)
        main.run(args)
        self.assertEqual(sorted(FakeTelegram.sent), ["/uk/item/10", "/uk/item/11"])
        main.run(args)
        self.assertEqual(len(FakeTelegram.sent), 2, "повторне довантаження не дублює надіслане")

    def test_manual_backfill_longer_than_max_age(self):
        cfg = write(self.tmp, BASE.format(extra=""))
        FakeShafa.catalog.append(item(40, 1, "shtany-i-shorty/dzhinsy", 90, name="джинси 90 год"))
        self.run_once(cfg)
        args = argparse.Namespace(config=str(cfg), state=str(self.tmp / "state.json"), dry_run=False, demo=0,
                                  backfill=96)
        main.run(args)
        self.assertIn("/uk/item/40", FakeTelegram.sent, "96 год > max_age_hours 72 — не «старе»")

    def test_same_title_and_price_sent_once(self):
        cfg = write(self.tmp, BASE.format(extra=""))
        self.run_once(cfg)
        FakeShafa.catalog += [item(41, 1, "shtany-i-shorty/dzhinsy", name="Джинси x"),
                              item(42, 1, "shtany-i-shorty/dzhinsy", name="Джинси X")]
        self.run_once(cfg)
        self.assertEqual(len(FakeTelegram.sent), 1)

    def test_slow_package_runs_by_interval(self):
        body = BASE.format(extra="  - name: R\n    id: 5\n    package: рідкісні").replace(
            "my_sizes:", "settings:\n  packages: {звичайні: 10, рідкісні: 30}\nmy_sizes:")
        cfg = write(self.tmp, body)
        from shafa_watch import state as st_mod
        c = rules.load(cfg)
        s = st_mod.State(self.tmp / "s.json")
        self.assertEqual(len(main.select_due(c.groups(), c, s)), len(c.groups()))
        slow = [g for g in c.groups() if g.package == "рідкісні"][0]
        s.health["group_last"] = {slow.id: __import__("time").time()}
        self.assertNotIn(slow, main.select_due(c.groups(), c, s))

    def test_reseller_and_title_include(self):
        r = rules.loads("brands: [{name: X, id: 1, title_include: 'rrl|double rl'}]").rules[0]
        base = item(1, 1, "rubashki/rubashki")
        self.assertIsNone(rules.quick_check({**base, "name": "Сорочка RRL"}, r))
        self.assertIn("фрази", rules.quick_check({**base, "name": "Сорочка Polo"}, r))
        r2 = rules.loads("brands: [{name: X, id: 1}]").rules[0]
        self.assertIn("перекуп", rules.quick_check({**base, "name": "Світшот нові s-xl"}, r2))

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


class SellerTest(unittest.TestCase):
    def rule(self, seller, cond=3, mats=()):
        return rules.Rule(label="x", brands={1: "B"}, seller=seller, min_condition=cond, materials=list(mats))

    def test_variants(self):
        self.assertEqual(self.rule("any").variants(), [([1, 2, 3], [])])
        self.assertEqual(self.rule("private").variants(), [([1, 2, 3], [rules.SELLER_PRIVATE])])
        self.assertEqual(self.rule("private_new", mats=[1712]).variants(),
                         [([2, 3], [1712]), ([1], [1712, rules.SELLER_PRIVATE])])
        self.assertEqual(self.rule("private_new", cond=None).variants(),
                         [([2, 3, 4, 5], []), ([1], [rules.SELLER_PRIVATE])])
        self.assertEqual(self.rule("private_new", cond=1).variants(), [([1], [rules.SELLER_PRIVATE])])

    def test_key_and_config(self):
        self.assertEqual(self.rule("any").query_key(), rules.Rule(label="x", brands={1: "B"}, min_condition=3).query_key())
        self.assertNotEqual(self.rule("any").query_key(), self.rule("private_new").query_key())
        cfg = rules.loads("defaults: {seller: нові}\nbrands:\n  - {name: COS, id: 1}\n  - {name: A, id: 2, seller: any}\n")
        by = {r.label: r for r in cfg.rules}
        self.assertEqual((by["COS"].seller, by["A"].seller), ("private_new", "any"))
        with self.assertRaises(rules.ConfigError):
            rules.loads("defaults: {seller: дехто}\nbrands:\n  - {name: COS, id: 1}\n")



class Review1111Test(unittest.TestCase):
    """Правки за розбором 11.11.2026."""

    def test_html_unescape(self):
        from shafa_watch import shafa
        n = shafa.clean({"name": "Levi's made &amp; crafted 502", "description": "Marc O&#39;Polo"})
        self.assertEqual(n["name"], "Levi's made & crafted 502")
        self.assertEqual(n["description"], "Marc O'Polo")
        self.assertRegex(n["name"], r"made\s*(&|and)\s*crafted")

    def test_blocked_seller(self):
        it = item(1, 5, "kofti/svitery")
        it["seller"] = {"id": 1502008, "username": "ivan.vusik"}
        self.assertIsNotNone(rules.blocked_seller(it, ["ivan.vusik"]))
        self.assertIsNotNone(rules.blocked_seller(it, [1502008]))
        self.assertIsNotNone(rules.blocked_seller(it, ["@Ivan.Vusik"]))
        self.assertIsNone(rules.blocked_seller(it, ["someone"]))
        self.assertIsNone(rules.blocked_seller(item(2, 5, "obuv"), ["ivan.vusik"]))   # продавця немає в даних

    def test_tactical_categories(self):
        cfg = rules.loads("brands:\n  - {name: Lowa, id: 1, categories: [взуття]}\n"
                          "  - {name: Fjallraven, id: 2, categories: [брюки]}\n"
                          "searches:\n  - {name: Лляні брюки, categories: [брюки], materials: [1967]}\n")
        by = {r.label: r for r in cfg.rules}
        self.assertIsNone(rules.quick_check(item(1, 1, "takticheskaya-odezhda/obuv"), by["Lowa"]))
        self.assertIsNone(rules.quick_check(item(2, 2, "takticheskaya-odezhda/shtany"), by["Fjallraven"]))
        # серверний catalogSlug пошуку без бренду не розширюється тактичним розділом
        self.assertEqual(by["Лляні брюки"].catalog, "shtany-i-shorty/bryuki")

    def cfg(self):
        return rules.loads(textwrap.dedent("""\
            category_materials:
              светри: {only: [вовна, кашемір], except: [худі, олімпійки], if_unknown: send}
            brands:
              - {name: Lacoste, id: 84, categories: [светри]}
            searches:
              - {name: Вовна, categories: [светри], materials: [вовна], title_prefer: "merino|made in scotland"}
            """))

    def test_olympics_and_unknown_material(self):
        cfg = self.cfg()
        lac = cfg.rules[0]
        # олімпійка — будь-яка тканина
        self.assertEqual(rules.material_check(item(1, 84, "kofty/olimpiiki", name="Олімпійка lacoste поліестер"),
                                              {"description": ""}, cfg.category_materials, lac)[0], None)
        # светр без матеріалу — проходить тихо
        reason, prio, _ = rules.material_check(item(2, 84, "kofti/svitery", name="Светр lacoste"),
                                               {"description": ""}, cfg.category_materials, lac)
        self.assertEqual((reason, prio), (None, False))
        # бавовна — як і раніше відсіюється
        self.assertIsNotNone(rules.material_check(item(3, 84, "kofti/svitery", name="Светр lacoste бавовна"),
                                                  {"description": ""}, cfg.category_materials, lac)[0])

    def test_title_prefer(self):
        r = self.cfg().rules[1]
        self.assertTrue(rules.title_priority(item(1, None, "kofti/svitery", name="Merino pullover"), None, r))
        self.assertTrue(rules.title_priority(item(2, None, "kofti/svitery", name="Светр"),
                                             {"description": "Made in Scotland"}, r))
        self.assertFalse(rules.title_priority(item(3, None, "kofti/svitery", name="Светр шерсть"), None, r))
        self.assertIsNone(rules.title_priority(item(4, 84, "kofti/svitery"), None, self.cfg().rules[0]))

    def test_wool_share(self):
        cases = {"джемпер 76% бавовна 7 % вовна": 7, "светр вовна 60%": 60, "вовняний (60%) пуловер": 60,
                 "30% wool 70% acrylic": 30, "кашемір 15%, вовна 85%": 100, "80% cotton 20% nylon": 0,
                 "Склад: вовна - 40%, акрил - 60%": 40, "Вовна + бавовна джемпер": None, "Lambswool 100%": 100}
        for text, want in cases.items():
            self.assertEqual(rules.wool_share(text), want, text)

    def test_min_share_and_hats(self):
        cfg = rules.loads(textwrap.dedent("""\
            category_materials:
              светри: {only: [вовна, кашемір], if_unknown: send, min_share: 50}
              holovni-ubory/shapky: {only: [вовна, кашемір], min_share: 50}
            searches:
              - {name: Вовна, categories: [светри], materials: [вовна, кашемір, альпака, ангора]}
              - {name: Шапки, section: holovni-ubory/shapky, materials: [1602]}
            """))
        sw, hat = cfg.rules
        self.assertEqual(sw.materials, [1225, 1245, 2252, 2266])          # 4 матеріали — дозволено
        bad = item(1, None, "kofti/svitery", name="Джемпер 76% бавовна 7% вовна")
        self.assertIn("в складі 7%", rules.material_check(bad, None, cfg.category_materials, sw)[0])
        ok = item(2, None, "kofti/svitery", name="Светр вовна 60%")
        self.assertIsNone(rules.material_check(ok, None, cfg.category_materials, sw)[0])
        h = item(3, None, "holovni-ubory/shapky", name="Шапка 30% вовна 70% акрил")
        self.assertIsNotNone(rules.material_check(h, None, cfg.category_materials, hat)[0])

    def test_rule_min_share_natural(self):
        cfg = rules.loads("searches:\n  - {name: Брюки, categories: [брюки], materials: [1980], min_share: 50}\n")
        r = cfg.rules[0]
        self.assertEqual(r.min_share, 50)
        cut = item(1, None, "shtany-i-shorty/bryuki", name="Брюки 30% вовна, 70% поліестер")
        self.assertIn("натуральних волокон у складі 30%", rules.material_check(cut, None, cfg.category_materials, r)[0])
        for name in ("Брюки 100% льон", "Брюки вовна 55%, поліестер 45%", "Вовняні брюки"):
            self.assertIsNone(rules.material_check(item(2, None, "shtany-i-shorty/bryuki", name=name), None,
                                                   cfg.category_materials, r)[0], name)


class Review1211Test(unittest.TestCase):
    """Розбір 12.11.2026: дробові відсотки, шовк у светрах, жилети, порядок фільтрів, повторна перевірка, дублі."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        main.Shafa = FakeShafa
        main.Telegram = FakeTelegram
        FakeTelegram.sent = []
        FakeShafa.catalog = []

    def run_once(self, cfg: Path, **kw):
        args = argparse.Namespace(config=str(cfg), state=str(self.tmp / "state.json"), dry_run=False, demo=0, **kw)
        return main.run(args)

    def test_decimal_percent(self):
        self.assertEqual(rules.wool_share("Високий вміст вовни — 67.9% Wool (з віскозою)"), 68)
        self.assertEqual(rules.wool_share("вовна 45,5%, поліестер 54,5%"), 46)

    def test_silk_counts_in_knit(self):
        cfg = rules.loads("category_materials:\n  светри: {only: [вовна, кашемір], min_share: 50}\n"
                          "searches:\n  - {name: С, categories: [светри], materials: [вовна]}\n")
        r = cfg.rules[0]
        for name in ("Светр 55% шовк 45% кашемір", "Светр 65% шовк, 35% кашемір"):
            self.assertIsNone(rules.material_check(item(1, None, "kofti/svitery", name=name), None,
                                                   cfg.category_materials, r)[0], name)
        self.assertIsNotNone(rules.material_check(item(2, None, "kofti/svitery", name="Светр 80% бавовна 20% кашемір"),
                                                  None, cfg.category_materials, r)[0])

    def test_vests_tuxedo_and_sport_categories(self):
        r = rules.loads("searches:\n  - {name: П, categories: [піджаки, костюми], materials: [1426]}\n").rules[0]
        self.assertIsNone(rules.quick_check(item(1, None, "pidzhaki-i-kostiumy/zhiletki"), r))
        self.assertIsNone(rules.quick_check(item(2, None, "pidzhaki-i-kostiumy/smokingi"), r))
        self.assertEqual(r.catalog, "pidzhaki-i-kostiumy")
        b = rules.loads("brands: [{name: M, id: 1, categories: [кофти, штани]}]").rules[0]
        self.assertIsNone(rules.quick_check(item(3, 1, "sport-i-otdyh/sportivnyye-kofty"), b))
        self.assertIsNone(rules.quick_check(item(4, 1, "sport-i-otdyh/sportivnyye-shtany"), b))
        # пошуки без бренду: спорт-слаги не розширюють серверний catalogSlug
        s = rules.loads("searches:\n  - {name: Б, categories: [штани], materials: [1980]}\n").rules[0]
        self.assertEqual(s.catalog, "shtany-i-shorty")

    def test_age_reported_before_category(self):
        r = rules.loads("brands: [{name: X, id: 1, categories: [джинси], max_age_hours: 72}]").rules[0]
        self.assertIn("старе", rules.quick_check(item(1, 1, "kofti/svitery", hours_ago=500), r))

    def test_faux_leather(self):
        r = rules.loads("searches:\n  - {name: Ш, categories: [куртки], materials: [2050], genuine_only: true}\n").rules[0]
        it = item(1, None, "verkhniaia-odezhda/kurtki", name="Сорочка-куртка zara")
        self.assertIn("штучна", rules.detail_check(it, {"description": "з матеріалу під замшу"}, r))
        self.assertIsNone(rules.detail_check(it, {"description": "натуральна шкіра, підкладка штучна шкіра"}, r))
        self.assertIsNone(rules.detail_check(it, {"description": "Шкіра, підошва PU"}, r))

    def test_women_exclude_default(self):
        rx = ("^(?!.*(чоловіч|мужск|унісекс|унисекс|unisex)).*(жіноч|женск|для дівч|для жінок|women)")
        r = rules.loads(f"defaults: {{keywords_exclude: '{rx}'}}\nbrands: [{{name: X, id: 1}}]").rules[0]
        self.assertIsNotNone(rules.quick_check(item(1, 1, "kofti/svitery", name="Жіночий светр 100% кашемір"), r))
        self.assertIsNone(rules.quick_check(item(2, 1, "kofti/hudi", name="Худі чоловіча/жіноча"), r))

    def test_length_soft_is_quiet(self):
        m = {"length_min": 110, "length_soft": 3}
        it = item(1, None, "shtany-i-shorty/bryuki", name="Брюки")
        self.assertIsNone(rules.measure_check(it, {"description": "Довжина 108 см"}, m))
        self.assertTrue(rules.measure_quiet(it, {"description": "Довжина 108 см"}, m))
        self.assertIsNotNone(rules.measure_check(it, {"description": "Довжина 105 см"}, m))
        self.assertFalse(rules.measure_quiet(it, {"description": "Довжина 112 см"}, m))

    def test_nb_990v3(self):
        cfg = rules.load(Path(__file__).resolve().parent.parent / "brands.yaml")
        r = next(x for x in cfg.rules if x.label == "New Balance · New Balance Made in USA")
        self.assertIsNone(rules.quick_check(item(1, 385, "obuv/krossovki", name="Продам кросівки new balance 990v3"), r))

    def test_recheck_by_new_search_and_no_resend(self):
        body = BASE.format(extra="").replace("my_sizes:", "settings:\n  backfill_hours: 72\nmy_sizes:")
        no_search = body.split("searches:")[0]
        cfg = write(self.tmp, no_search)
        self.run_once(cfg)                                     # перший прохід бренду A
        FakeShafa.catalog.append(item(51, 1, "kofti/svitery"))   # светр A (id непарний → «100% вовна»)
        self.run_once(cfg)
        self.assertEqual(FakeTelegram.sent, [], "бренд A светри не бере")
        cfg = write(self.tmp, body)                            # з'явився пошук «Вовна» — річ уже бачена
        self.run_once(cfg)
        self.assertEqual(FakeTelegram.sent, ["/uk/item/51"], "новий пошук оцінює вже бачену відсіяну річ")
        args = argparse.Namespace(config=str(cfg), state=str(self.tmp / "state.json"), dry_run=False, demo=0,
                                  backfill=168)
        FakeShafa.catalog[-1]["name"] = "Інша назва"            # змінено назву — антиповтор назви не спрацює
        main.run(args)
        self.assertEqual(FakeTelegram.sent, ["/uk/item/51"], "надіслане за id не повторюється")

    def test_sent_seed(self):
        from shafa_watch import state as st_mod
        (self.tmp / "data").mkdir()
        (self.tmp / "data" / "sent_seed.json").write_text('{"ids": [77]}', encoding="utf-8")
        cfg = write(self.tmp, BASE.format(extra=""))
        FakeShafa.catalog = [item(77, 1, "shtany-i-shorty/dzhinsy", 5)]
        self.run_once(cfg, backfill=72)
        self.assertEqual(FakeTelegram.sent, [])
        self.assertTrue(st_mod.State(self.tmp / "state.json").was_sent(77))

    def test_shafa_down_fails_fast(self):
        class Down(FakeShafa):
            calls = 0

            def products_batch(self, queries):
                Down.calls += 1
                raise main.ShafaError("HTTP 522", 522)
        main.Shafa = Down
        body = BASE.format(extra="  - name: B\n    id: 2\n    package: інший\n    categories: [джинси]\n"
                                 "  - name: C\n    id: 3\n    package: третій\n    categories: [джинси]").replace(
            "my_sizes:", "settings:\n  aliases_per_request: 2\n  packages: {звичайні: 10, інший: 10, третій: 10}\n"
                         "my_sizes:")
        cfg = write(self.tmp, body)
        self.assertEqual(self.run_once(cfg), 1)
        self.assertEqual(Down.calls, 2, "після двох пачок з 5xx прохід завершується, групи окремо не смикаються")
        self.assertTrue((self.tmp / "state.json").exists(), "стан збережено")

    def test_waist_range_takes_max(self):
        m = {"waist_half_min": 45}
        it = item(1, None, "sport-i-otdyh/sportivnyye-shtany", name="Штани gramicci")
        self.assertIsNone(rules.measure_check(it, {"description": "півобхват поясу від 42 до 48 см"}, m))
        self.assertIsNone(rules.measure_check(it, {"description": "пояс 42–48 см"}, m))
        self.assertIsNotNone(rules.measure_check(it, {"description": "пояс 42 см, довжина 104"}, m))



class Sizes1211Test(unittest.TestCase):
    """12.11.2026: «розмір M, L» не надсилаємо (лише L, L/XL, XL); сорочки Levi's — нікому."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        main.Shafa = FakeShafa
        main.Telegram = FakeTelegram
        FakeTelegram.sent = []
        FakeShafa.catalog = []

    def sized(self, pid, names, slug="kofti/svitery", brand=None):
        it = item(pid, brand, slug)
        it["sizes"] = [{"id": i, "name": n} for i, n in enumerate(names)]
        return it

    def test_letter_sizes(self):
        r = rules.loads("my_sizes: {одяг: [L, XL]}\nsearches:\n  - {name: С, categories: [светри], materials: [вовна]}\n").rules[0]
        self.assertEqual(r.size_letters, {"L", "XL"})
        for ok in (["L"], ["XL"], ["L", "XL"], ["L-XL"], ["40 / L / 48"], ["48"], ["W34"], []):
            self.assertIsNone(rules.quick_check(self.sized(1, ok), r), ok)
        for bad in (["M", "L"], ["M-L"], ["L", "M-L"], ["38 / M / 46", "40 / L / 48"], ["L", "XL", "XXL"],
                    ["S", "M", "L", "XL", "XXL"], ["XL", "XXL"]):
            self.assertIn("розмір", rules.quick_check(self.sized(1, bad), r) or "", bad)

    def test_no_letter_profile_no_check(self):
        r = rules.loads("searches:\n  - {name: Ш, section: holovni-ubory/shapky, sizes: [320, 321], text: x}\n").rules[0]
        self.assertFalse(r.size_letters)
        self.assertIsNone(rules.size_mismatch(self.sized(1, ["M", "L"]), r))

    def test_brand_category_block(self):
        cfg_text = (
            "settings:\n  skip_brand_categories:\n    - {brands: [82], categories: [сорочки]}\n"
            "brands:\n  - {name: \"Levi's\", id: 82}\n"
            "searches:\n  - {name: Лляні сорочки, categories: [сорочки], materials: [1712]}\n")
        cfg = Path(self.tmp / "b.yaml")
        cfg.write_text(cfg_text, encoding="utf-8")
        blocks = rules.loads(cfg_text).settings["skip_brand_categories"]
        self.assertIsNotNone(rules.blocked_brand_category(item(1, 82, "rubashki/rubashki"), blocks))
        self.assertIsNone(rules.blocked_brand_category(item(2, 82, "shtany-i-shorty/dzhinsy"), blocks))
        self.assertIsNone(rules.blocked_brand_category(item(3, 99, "rubashki/rubashki"), blocks))
        with self.assertRaises(rules.ConfigError):
            rules.loads("settings:\n  skip_brand_categories:\n    - {brands: [82]}\n")
