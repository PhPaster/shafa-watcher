"""Довідник id для brands.yaml.

  python tools/lookup.py brand "massimo"        # id бренду за назвою
  python tools/lookup.py sizes men              # id фільтра розмірів для розділу
  python tools/lookup.py materials kofti        # id матеріалів (характеристика «Матеріал») для підкатегорії
  python tools/lookup.py categories             # словник категорій (людська назва → slug-и)
  python tools/lookup.py fill                   # підставити id брендам без id у brands.yaml
"""
from __future__ import annotations

import argparse
import collections
import re
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from shafa_watch import rules  # noqa: E402
from shafa_watch.shafa import COOKIES, HEADERS, Shafa  # noqa: E402

V5 = "https://shafa.ua/api/v5/graphql"


def v5(query: str, variables: dict) -> dict:
    r = requests.post(V5, headers=HEADERS, cookies=COOKIES, json={"query": query, "variables": variables}, timeout=30)
    r.raise_for_status()
    j = r.json()
    if j.get("errors") and not j.get("data"):
        raise SystemExit(f"GraphQL: {j['errors']}")
    return j["data"]


def find_brands(name: str) -> dict[int, str]:
    """Кандидати: топ-бренди фільтра + бренди з результатів текстового пошуку товарів."""
    needle = name.lower()
    found: dict[int, str] = {}
    top = v5("query B { filterTopBrands { brands { id name } } }", {})["filterTopBrands"]["brands"]
    for b in top:
        if needle in b["name"].lower():
            found[b["id"]] = b["name"]
    r = requests.post("https://shafa.ua/api/v3/graphiql", headers=HEADERS, cookies=COOKIES, json={
        "query": "query S($t: String) { products(first: 200, pageNum: 1, searchText: $t) { edges { node { brand { id name } } } } }",
        "variables": {"t": name}}, timeout=30)
    r.raise_for_status()
    cnt = collections.Counter()
    for e in r.json()["data"]["products"]["edges"]:
        b = e["node"].get("brand")
        if b and needle in b["name"].lower():
            cnt[(b["id"], b["name"])] += 1
    for (bid, bname), _ in cnt.most_common():
        found.setdefault(bid, bname)
    return found


def brand(name: str) -> None:
    found = find_brands(name)
    if not found:
        print("Не знайдено. Відкрий shafa.ua, вибери бренд у фільтрі й візьми число з brands= в адресі.")
    for bid, bname in found.items():
        print(f"{bid:>8}  {bname}")


def _norm(n: str) -> str:
    return re.sub(r"[^0-9a-zа-яіїєґ]+", "", n.lower())


def fill(path: str) -> None:
    """Брендам без id підставляє id, якщо назва збігається однозначно (без урахування регістру й розділових
    знаків). Неоднозначні випадки лише друкує — їх вирішує людина. Коментарі у файлі зберігаються."""
    import yaml
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    raw = yaml.safe_load(text) or {}
    lines = text.splitlines(keepends=True)
    todo = [b for b in raw.get("brands") or [] if isinstance(b, dict) and b.get("name") and b.get("id") is None]
    if not todo:
        print("Усі бренди вже мають id.")
        return
    filled = 0
    for b in todo:
        name = str(b["name"])
        found = find_brands(name)
        time.sleep(1.5)
        exact = sorted(bid for bid, bn in found.items() if _norm(bn) == _norm(name))
        if len(exact) != 1:
            print(f"? {name}: " + (", ".join(f"{bid} {bn}" for bid, bn in found.items()) or "не знайдено")
                  + ("  ← кілька точних збігів, вибери вручну" if len(exact) > 1 else ""))
            continue
        bid = exact[0]
        pat = re.compile(r"^(\s*)-\s+name:\s*[\"']?" + re.escape(name) + r"[\"']?\s*(#.*)?$")
        for i, line in enumerate(lines):
            m = pat.match(line.rstrip("\n"))
            if m:
                indent = m.group(1) + "  "
                lines.insert(i + 1, f"{indent}id: {bid}\n")
                filled += 1
                print(f"✓ {name}: {bid} ({found[bid]})")
                break
        else:
            print(f"? {name}: id {bid}, але рядок «- name: {name}» не знайдено — впиши вручну")
    p.write_text("".join(lines), encoding="utf-8")
    print(f"Підставлено: {filled} з {len(todo)}")


def categories(section: str) -> None:
    for name, slugs in rules.CATEGORIES.get(section, {}).items():
        print(f"{name:<16} {', '.join(slugs)}")


def sizes(section: str) -> None:
    q = "query S($c: String) { filterSizes(catalogSlug: $c) { id primarySizeName secondarySizeName } }"
    for s in v5(q, {"c": section})["filterSizes"]:
        print(f"{s['id']:>6}  {s['primarySizeName']}  {s['secondarySizeName'] or ''}")


def materials(section: str) -> None:
    q = ("query M($c: String) { catalog(catalogSlug: $c) { characteristics { id title "
         "choices { id title } } } }")
    try:
        data = Shafa()._post("M", q, {"c": section.strip("/").split("/")[-1]})
    except Exception as e:  # noqa: BLE001
        raise SystemExit(f"Помилка: {e}")
    chars = (data.get("catalog") or {}).get("characteristics") or []
    mats = [c for c in chars if c["title"].lower().startswith("матеріал")]
    if not mats:
        print("Для цього розділу фільтра матеріалу немає. Вкажи підкатегорію, напр. kofti або verkhniaia-odezhda. "
              "Id матеріалу однаковий у всіх підкатегоріях і працює як серверний фільтр навіть для section: men.")
    for c in mats:
        for ch in c["choices"]:
            print(f"{ch['id']:>6}  {ch['title']}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("what", choices=["brand", "sizes", "materials", "categories", "fill"])
    p.add_argument("arg", nargs="?", help="назва бренду / розділ / шлях до brands.yaml (для fill)")
    a = p.parse_args()
    default = {"fill": "brands.yaml", "categories": "men"}
    arg = a.arg or default.get(a.what)
    if not arg:
        p.error("потрібен аргумент")
    {"brand": brand, "sizes": sizes, "materials": materials, "categories": categories, "fill": fill}[a.what](arg)


if __name__ == "__main__":
    main()
