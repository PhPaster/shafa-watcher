"""Довідник id для brands.yaml.

  python tools/lookup.py brand "massimo"        # id бренду за назвою
  python tools/lookup.py sizes men              # id фільтра розмірів для розділу
  python tools/lookup.py materials men/kofti    # id матеріалів (характеристика «Матеріал») для підкатегорії
"""
from __future__ import annotations

import argparse
import collections
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from shafa_watch.shafa import COOKIES, HEADERS, Shafa  # noqa: E402

V5 = "https://shafa.ua/api/v5/graphql"


def v5(query: str, variables: dict) -> dict:
    r = requests.post(V5, headers=HEADERS, cookies=COOKIES, json={"query": query, "variables": variables}, timeout=30)
    r.raise_for_status()
    j = r.json()
    if j.get("errors") and not j.get("data"):
        raise SystemExit(f"GraphQL: {j['errors']}")
    return j["data"]


def brand(name: str) -> None:
    needle = name.lower()
    found = {}
    top = v5("query B { filterTopBrands { brands { id name } } }", {})["filterTopBrands"]["brands"]
    for b in top:
        if needle in b["name"].lower():
            found[b["id"]] = b["name"]
    # Запасний шлях: пошук товарів за текстом і бренди з результатів.
    r = requests.post("https://shafa.ua/api/v3/graphiql", headers=HEADERS, cookies=COOKIES, json={
        "query": "query S($t: String) { products(first: 200, pageNum: 1, searchText: $t) { edges { node { brand { id name } } } } }",
        "variables": {"t": name}}, timeout=30)
    cnt = collections.Counter()
    for e in r.json()["data"]["products"]["edges"]:
        b = e["node"].get("brand")
        if b and needle in b["name"].lower():
            cnt[(b["id"], b["name"])] += 1
    for (bid, bname), _ in cnt.most_common():
        found.setdefault(bid, bname)
    if not found:
        print("Не знайдено. Відкрий shafa.ua, вибери бренд у фільтрі й візьми число з brands= в адресі.")
    for bid, bname in found.items():
        print(f"{bid:>8}  {bname}")


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
    p.add_argument("what", choices=["brand", "sizes", "materials"])
    p.add_argument("arg")
    a = p.parse_args()
    {"brand": brand, "sizes": sizes, "materials": materials}[a.what](a.arg)


if __name__ == "__main__":
    main()
