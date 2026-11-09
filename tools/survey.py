"""Опитування Shafa для довгого списку брендів: id брендів і частота появи речей.

  python tools/survey.py resolve brands_src.json out.json     # етап 1: кандидати id через filterBrand
  python tools/survey.py measure out.json                     # етап 2: скільки речей (усі / men / мої розміри / 30 днів)
  python tools/survey.py text out.json [--terms t.json]       # етап 3: текстовий пошук для брендів без id і саб-лейблів

Вхід brands_src.json: [{"name": "...", ...}, ...]. Результати дописуються в out.json (кеш: повторний запуск
не повторює вже зроблені запити). Батчинг аліасами GraphQL: 10–15 брендів за один HTTP-запит, пауза 2 с.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import time
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from shafa_watch.shafa import Shafa  # noqa: E402

DELAY = 2.0
_TRANS = str.maketrans({"ø": "o", "Ø": "o", "æ": "ae", "Æ": "ae", "ß": "ss", "œ": "oe", "đ": "d", "ł": "l"})


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.translate(_TRANS))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = s.replace("&", " and ").replace("+", " plus ")
    return re.sub(r"[^0-9a-z]+", "", s)


def gql_str(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


def search_terms(name: str) -> list[str]:
    """Повна назва; без діакритики; найдовше слово (для варіантів написання на сайті)."""
    plain = unicodedata.normalize("NFKD", name.translate(_TRANS))
    plain = "".join(c for c in plain if not unicodedata.combining(c))
    words = [w for w in re.split(r"[^\w']+", plain) if len(w) >= 4 and not w.isdigit()]
    terms = [name]
    if plain != name:
        terms.append(plain)
    if words:
        longest = max(words, key=len)
        if longest.lower() != name.lower():
            terms.append(longest)
    return list(dict.fromkeys(terms))


def resolve(src: Path, out: Path, batch: int = 15) -> None:
    shafa = Shafa(min_delay=DELAY)
    data = json.loads(out.read_text()) if out.exists() else {}
    cache: dict[str, list] = data.setdefault("search_cache", {})
    brands = json.loads(src.read_text())
    todo = [t for b in brands for t in search_terms(b["name"]) if t not in cache]
    todo = list(dict.fromkeys(todo))
    print(f"пошукових термінів: {len(todo)} → ~{(len(todo) + batch - 1) // batch} запитів")
    for i in range(0, len(todo), batch):
        chunk = todo[i:i + batch]
        q = "query S { " + " ".join(f"a{j}: filterBrand(name: {gql_str(t)}, first: 20) {{ id name }}"
                                     for j, t in enumerate(chunk)) + " }"
        res = shafa._post("S", q, {})
        for j, t in enumerate(chunk):
            cache[t] = res.get(f"a{j}") or []
        out.write_text(json.dumps(data, ensure_ascii=False, indent=1))
        print(f"  {i + len(chunk)}/{len(todo)}", flush=True)
    rows = []
    for b in brands:
        cands = {}
        for t in search_terms(b["name"]):
            for c in cache.get(t, []):
                cands[c["id"]] = c["name"]
        exact = [i for i, n in cands.items() if norm(n) == norm(b["name"])]
        rows.append({**b, "candidates": cands, "exact": exact})
    data["brands"] = rows
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    print(f"точних збігів: {sum(1 for r in rows if r['exact'])} з {len(rows)}")


PROFILE = [150, 151, 165, 166, 167, 180, 245, 181]   # L, XL · W34, W36, W38 · 45, 45.5, 46


def measure(out: Path, batch: int = 8) -> None:
    """Для кожного запису з полем `ids`: усього / у men / у men+мої розміри / нових за 30 днів (men+розміри)."""
    shafa = Shafa(min_delay=DELAY)
    data = json.loads(out.read_text())
    stats: dict[str, dict] = data.setdefault("stats", {})
    rows = [r for r in data["brands"] if r.get("ids") and r["name"] not in stats]
    print(f"брендів до заміру: {len(rows)} → ~{(len(rows) + batch - 1) // batch} запитів")
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=30)
    for i in range(0, len(rows), batch):
        chunk = rows[i:i + batch]
        parts = []
        for j, r in enumerate(chunk):
            ids = json.dumps(r["ids"])
            parts.append(f'all{j}: products(first: 1, pageNum: 1, brands: {ids}) {{ pageInfo {{ total }} }}')
            parts.append(f'men{j}: products(first: 1, pageNum: 1, catalogSlug: "men", brands: {ids}) '
                         f'{{ pageInfo {{ total }} }}')
            parts.append(f'mine{j}: products(first: 100, pageNum: 1, orderBy: "4", catalogSlug: "men", '
                         f'brands: {ids}, sizes: {json.dumps(PROFILE)}) '
                         f'{{ edges {{ node {{ createdAt catalogSlug }} }} pageInfo {{ total }} }}')
        res = shafa._post("M", "query M { " + " ".join(parts) + " }", {})
        for j, r in enumerate(chunk):
            mine = res[f"mine{j}"]
            recent = 0
            cats: dict[str, int] = {}
            for e in mine["edges"]:
                n = e["node"]
                try:
                    if dt.datetime.fromisoformat(n["createdAt"]) >= since:
                        recent += 1
                except (TypeError, ValueError):
                    pass
                top = (n.get("catalogSlug") or "?").split("/")[0]
                cats[top] = cats.get(top, 0) + 1
            stats[r["name"]] = {"all": res[f"all{j}"]["pageInfo"]["total"],
                                "men": res[f"men{j}"]["pageInfo"]["total"],
                                "mine": mine["pageInfo"]["total"], "mine_30d": recent,
                                "mine_30d_capped": len(mine["edges"]) == 100 and recent == 100,
                                "mine_cats": cats}
        out.write_text(json.dumps(data, ensure_ascii=False, indent=1))
        print(f"  {i + len(chunk)}/{len(rows)}", flush=True)


def measure_text(out: Path, batch: int = 8, terms: dict[str, str] | None = None) -> None:
    """Текстовий пошук (searchText) для записів без id і для саб-лейблів (батьківський id + фраза):
    скільки речей згадують назву в men+мої розміри і загалом, плюс 3 приклади назв для перевірки на шум."""
    shafa = Shafa(min_delay=DELAY)
    data = json.loads(out.read_text())
    stats: dict[str, dict] = data.setdefault("text_stats", {})
    terms = terms or {}
    rows = [r for r in data["brands"] if r.get("kind") in ("absent", "text", "subline") and r["name"] not in stats]
    print(f"текстових замірів: {len(rows)} → ~{(len(rows) + batch - 1) // batch} запитів")
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=30)
    for i in range(0, len(rows), batch):
        chunk = rows[i:i + batch]
        parts = []
        for j, r in enumerate(chunk):
            term = terms.get(r["name"], r["name"])
            br = f", brands: {json.dumps(r['ids'])}" if r.get("kind") == "subline" and r.get("ids") else ""
            parts.append(f'all{j}: products(first: 1, pageNum: 1, searchText: {gql_str(term)}{br}) '
                         f'{{ pageInfo {{ total }} }}')
            parts.append(f'mine{j}: products(first: 100, pageNum: 1, orderBy: "4", catalogSlug: "men", '
                         f'searchText: {gql_str(term)}{br}, sizes: {json.dumps(PROFILE)}) '
                         f'{{ edges {{ node {{ name createdAt brand {{ name }} }} }} pageInfo {{ total }} }}')
        res = shafa._post("T", "query T { " + " ".join(parts) + " }", {})
        for j, r in enumerate(chunk):
            mine = res[f"mine{j}"]
            recent = sum(1 for e in mine["edges"]
                          if e["node"].get("createdAt") and dt.datetime.fromisoformat(e["node"]["createdAt"]) >= since)
            stats[r["name"]] = {"term": terms.get(r["name"], r["name"]), "all": res[f"all{j}"]["pageInfo"]["total"],
                                "mine": mine["pageInfo"]["total"], "mine_30d": recent,
                                "samples": [f"{e['node']['name']} [{(e['node'].get('brand') or {}).get('name')}]"
                                            for e in mine["edges"][:3]]}
        out.write_text(json.dumps(data, ensure_ascii=False, indent=1))
        print(f"  {i + len(chunk)}/{len(rows)}", flush=True)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("resolve")
    a.add_argument("src", type=Path)
    a.add_argument("out", type=Path)
    b = sub.add_parser("measure")
    b.add_argument("out", type=Path)
    t = sub.add_parser("text")
    t.add_argument("out", type=Path)
    t.add_argument("--terms", type=Path, help="JSON {назва: пошукова фраза}")
    args = p.parse_args()
    if args.cmd == "resolve":
        resolve(args.src, args.out)
    elif args.cmd == "text":
        measure_text(args.out, terms=json.loads(args.terms.read_text()) if args.terms else None)
    else:
        measure(args.out)


if __name__ == "__main__":
    main()
