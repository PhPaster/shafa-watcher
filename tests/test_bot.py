"""Офлайн-тести команд бота: python -m unittest discover -s tests -v"""
from __future__ import annotations

import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from shafa_watch import rules  # noqa: E402
from shafa_watch.bot import Bot  # noqa: E402
from shafa_watch.state import State  # noqa: E402

CHAT = "111"
YAML = """\
# коментар угорі має лишитися
my_sizes:
  одяг: [L, XL]   # мій розмір
  взуття: [43]

defaults:
  section: men
  min_condition: 3

brands:
  - name: COS
    id: 1956
    categories: [джинси]

  - name: ARKET   # усе
    id: 45928
"""


class FakeTG:
    def __init__(self, updates):
        self.updates = updates
        self.sent: list[dict] = []
        self.dry_run = False
        self.chat_id = CHAT

    def call(self, method, payload, with_chat=True):
        if method == "getUpdates":
            off = payload.get("offset", 0)
            return {"ok": True, "result": [u for u in self.updates if u["update_id"] >= off]}
        if method == "sendMessage":
            self.sent.append(payload)
        return {"ok": True}


class FakeShafa:
    def find_brands(self, name, first=20):
        db = {"our legacy": [{"id": 69235, "name": "Our Legacy"}, {"id": 47135, "name": "OUR HERITAGE"}],
              "ami": [{"id": 46858, "name": "AMI"}, {"id": 83899, "name": "Ami Medea"}],
              "amy": [{"id": 1, "name": "Amy One"}, {"id": 2, "name": "Amy Two"}]}
        return db.get(name.lower(), [])


def msg(i, text, chat=CHAT):
    return {"update_id": i, "message": {"chat": {"id": int(chat)}, "text": text}}


def cb(i, data):
    return {"update_id": i, "callback_query": {"id": f"c{i}", "data": data, "message": {"chat": {"id": int(CHAT)}}}}


class BotTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cfg = self.tmp / "brands.yaml"
        self.cfg.write_text(YAML, encoding="utf-8")
        self.state = State(self.tmp / "state.json")

    def run_bot(self, updates):
        tg = FakeTG(updates)
        changes = Bot(tg, self.cfg, self.state, FakeShafa()).process()
        return tg, changes, rules.load(self.cfg)

    def test_add_exact_with_categories_and_keep_comments(self):
        tg, changes, cfg = self.run_bot([msg(1, "/add Our Legacy: сорочки, светри")])
        self.assertEqual(changes, ["додано Our Legacy"])
        r = [r for r in cfg.rules if r.label == "Our Legacy"][0]
        self.assertEqual(list(r.brands), [69235])
        self.assertIn("rubashki/rubashki", r.categories)
        text = self.cfg.read_text()
        self.assertIn("# коментар угорі має лишитися", text)
        self.assertIn("# мій розмір", text)
        self.assertIn("categories: [сорочки, светри]", text)
        self.assertEqual(self.state.health["bot"]["offset"], 2)

    def test_add_ambiguous_then_pick_by_button(self):
        tg, changes, _ = self.run_bot([msg(1, "/add amy")])
        self.assertEqual(changes, [])
        self.assertIn("reply_markup", tg.sent[-1])
        tg, changes, cfg = self.run_bot([cb(2, "add:2")])
        self.assertEqual(changes, ["додано Amy Two"])
        self.assertIn(2, {b for r in cfg.rules for b in r.brands})

    def test_bad_category_rejected(self):
        tg, changes, _ = self.run_bot([msg(1, "/add Our Legacy: шкарпетки")])
        self.assertEqual(changes, [])
        self.assertIn("невідома категорія", tg.sent[-1]["text"])

    def test_remove_off_on(self):
        _, changes, cfg = self.run_bot([msg(1, "/off arket"), msg(2, "/remove COS")])
        self.assertEqual(changes, ["призупинено ARKET", "прибрано COS"])
        self.assertEqual([r.label for r in cfg.rules], ["ARKET"])
        self.assertFalse(cfg.rules[0].enabled)
        _, changes, cfg = self.run_bot([msg(3, "/on ARKET")])
        self.assertTrue(cfg.rules[0].enabled)

    def test_condition_global_brand_and_buttons(self):
        tg, _, cfg = self.run_bot([msg(1, "/condition 2"), msg(2, "/condition COS 1"), msg(3, "/condition")])
        by = {r.label: r for r in cfg.rules}
        self.assertEqual(by["COS"].min_condition, 1)
        self.assertEqual(by["ARKET"].min_condition, 2)
        self.assertIn("reply_markup", tg.sent[-1])
        _, _, cfg = self.run_bot([cb(4, "cond:any"), msg(5, "/condition COS default")])
        by = {r.label: r for r in cfg.rules}
        self.assertIsNone(by["COS"].min_condition)
        self.assertIsNone(by["ARKET"].min_condition)

    def test_sizes(self):
        _, changes, cfg = self.run_bot([msg(1, "/sizes взуття 45 45,5 46"), msg(2, "/sizes штани W34 W36"),
                                        msg(3, "/sizes одяг -")])
        self.assertEqual(len(changes), 3)
        self.assertEqual(cfg.rules[0].sizes, [165, 166, 180, 181, 245])

    def test_bad_size_rejected_and_foreign_chat_ignored(self):
        tg, changes, cfg = self.run_bot([msg(1, "/sizes взуття 99"), msg(2, "/remove COS", chat="999")])
        self.assertEqual(changes, [])
        self.assertIn("невідомий розмір", tg.sent[0]["text"])
        self.assertEqual(len(tg.sent), 1)
        self.assertEqual(len(cfg.rules), 2)

    def test_offset_not_reprocessed(self):
        self.run_bot([msg(1, "/remove COS")])
        _, changes, _ = self.run_bot([msg(1, "/remove COS")])
        self.assertEqual(changes, [])


    def test_materials_and_prefer_commands(self):
        tg, changes, cfg = self.run_bot([
            msg(1, "/materials светри: вовна, кашемір"), msg(2, "/materials светри + альпака, ангора"),
            msg(3, "/materials светри - кашемір"), msg(4, "/prefer взуття: шкіра, замша"),
            msg(5, "/materials верхній одяг: вовна"), msg(6, "/materials верхній одяг off"),
            msg(7, "/materials светри невідомі так")])
        self.assertEqual(len(changes), 7)
        cm = {c.category: c for c in cfg.category_materials}
        self.assertEqual(cm["светри"].only, ["вовна", "альпака", "ангора"])
        self.assertEqual(cm["светри"].if_unknown, "send")
        self.assertEqual(cm["взуття"].prefer, ["шкіра", "замша"])
        self.assertNotIn("верхній одяг", cm)
        self.assertIn("category_materials:", self.cfg.read_text())

    def test_materials_bad_input(self):
        tg, changes, _ = self.run_bot([msg(1, "/materials светри: пластик"), msg(2, "/materials шкарпетки: вовна")])
        self.assertEqual(changes, [])
        self.assertIn("невідомий матеріал", tg.sent[0]["text"])
        self.assertIn("невідома категорія", tg.sent[1]["text"])


class MaterialCheckTest(unittest.TestCase):
    def setUp(self):
        self.cms = rules.loads("""
category_materials:
  светри: {only: [вовна, кашемір, альпака, ангора]}
  взуття: {prefer: [шкіра, замша]}
""").category_materials

    def check(self, slug, name, desc=""):
        return rules.material_check({"catalogSlug": slug, "name": name}, {"description": desc}, self.cms)

    def test_only(self):
        self.assertIsNone(self.check("kofti/svitery", "Светр альпака")[0])
        self.assertIn("треба", self.check("kofti/svitery", "Светр", "100% бавовна")[0])
        self.assertIn("не вказано", self.check("kofti/svitery", "Светр зимовий")[0])
        self.assertIsNone(self.check("kofti/hudi", "Худі бавовна")[0], "інша категорія — без обмежень")

    def test_prefer(self):
        self.assertEqual(self.check("obuv/botinki", "Черевики", "натуральна шкіра")[:2], (None, True))
        self.assertEqual(self.check("obuv/krossovki", "Кросівки еко шкіра")[:2], (None, False))
        self.assertEqual(self.check("rubashki/rubashki", "Сорочка")[:2], (None, None))


if __name__ == "__main__":
    unittest.main()
