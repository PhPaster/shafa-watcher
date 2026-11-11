"""Клієнт прихованого GraphQL API shafa.ua (перевірено 9.11.2026).

Ендпоінт: POST https://shafa.ua/api/v3/graphiql, без авторизації.
Мова відповіді задається cookie `language=uk` (без неї назви й описи автоперекладені російською).
"""
from __future__ import annotations

import html
import logging
import random
import time

import requests

log = logging.getLogger(__name__)

ENDPOINT = "https://shafa.ua/api/v3/graphiql"
SITE = "https://shafa.ua"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
    ),
    "Content-Type": "application/json",
    "Accept": "application/json",
    "Origin": SITE,
    "Referer": SITE + "/uk/",
    "x-app-platform": "web",
}
COOKIES = {"language": "uk"}

# Список товарів: та сама операція, що й на сторінці каталогу (orderBy "4" = за датою додавання).
PRODUCTS_QUERY = """
query WEB_CatalogProducts($first: Int!, $pageNum: Int!, $catalogSlug: String, $brands: [Int],
  $orderBy: String, $sizes: [Int!], $conditions: [Int], $priceTo: Int, $priceFrom: Int,
  $characteristics: [Int!]) {
  products(first: $first, pageNum: $pageNum, orderBy: $orderBy, sizes: $sizes, condition: $conditions,
    priceTo: $priceTo, priceFrom: $priceFrom, catalogSlug: $catalogSlug, brands: $brands,
    characteristics: $characteristics) {
    edges { node {
      id url name thumbnail price oldPrice discountPercent statusTitle condition createdAt isNew
      catalogSlug brand { id name } sizes { id name } seller { id username }
    } }
    pageInfo { hasNextPage total }
  }
}
"""

NODE_FIELDS = """id url name thumbnail price oldPrice discountPercent statusTitle condition createdAt isNew
      catalogSlug brand { id name } sizes { id name } seller { id username }"""

# Картка товару: опис, усі фото, стан текстом, характеристики (зокрема «Матеріал»).
DETAILS_QUERY = """
query WEB_ProductDetailsPageProduct($productId: Int!) {
  productDetails(productId: $productId) {
    id name description url price oldPrice discountPercent statusTitle createdAt
    brand { id name }
    condition { id name }
    sizes { id name primarySizeName secondarySizeName }
    colors { id name }
    photos { idStr thumbnailUrl originalUrl }
    characteristics { id title choices { id title } }
    category { id name }
    seller { id username }
  }
}
"""


def clean(node: dict | None) -> dict | None:
    """Shafa віддає назви й описи з HTML-кодами («made &amp; crafted», «&#39;»): розкодувати,
    інакше фрази з «&» не знаходяться, а в Telegram видно «&amp;» (11.11.2026)."""
    if node:
        for k in ("name", "description"):
            if isinstance(node.get(k), str) and "&" in node[k]:
                node[k] = html.unescape(node[k])
    return node


class ShafaError(RuntimeError):
    def __init__(self, msg: str, status: int | None = None):
        super().__init__(msg)
        self.status = status


class Shafa:
    def __init__(self, min_delay: float = 1.5, timeout: int = 30):
        self.s = requests.Session()
        self.s.headers.update(HEADERS)
        self.s.cookies.update(COOKIES)
        self.min_delay = min_delay
        self.timeout = timeout
        self._last = 0.0
        self.requests_made = 0

    def _post(self, op: str, query: str, variables: dict) -> dict:
        last_err: Exception | None = None
        for attempt in range(3):
            wait = self.min_delay - (time.time() - self._last)
            if wait > 0:
                time.sleep(wait + random.uniform(0, 0.5))
            self._last = time.time()
            self.requests_made += 1
            try:
                r = self.s.post(
                    ENDPOINT,
                    json={"operationName": op, "query": query, "variables": variables},
                    timeout=self.timeout,
                )
            except requests.RequestException as e:
                last_err = ShafaError(f"мережа: {e}")
                time.sleep(3 * (attempt + 1))
                continue
            if r.status_code in (403, 429):
                # Не обходимо блокування: одразу віддаємо помилку нагору, health-модуль сповістить.
                raise ShafaError(f"HTTP {r.status_code} (можливе блокування/ліміт)", r.status_code)
            if r.status_code >= 500:
                last_err = ShafaError(f"HTTP {r.status_code}", r.status_code)
                time.sleep(3 * (attempt + 1))
                continue
            if r.status_code != 200:
                raise ShafaError(f"HTTP {r.status_code}: {r.text[:200]}", r.status_code)
            try:
                j = r.json()
            except ValueError:
                raise ShafaError(f"не JSON: {r.text[:200]}", r.status_code)
            if j.get("errors") and not j.get("data"):
                raise ShafaError(f"GraphQL: {j['errors'][:1]}")
            return j["data"]
        raise last_err or ShafaError("невідома помилка")

    def products(self, *, brands: list[int] | None, catalog: str | None = None, sizes: list[int] | None = None,
                 conditions: list[int] | None = None, price_to: int | None = None,
                 price_from: int | None = None, characteristics: list[int] | None = None,
                 first: int = 100, page: int = 1, search_text: str | None = None) -> tuple[list[dict], bool]:
        v = {"first": first, "pageNum": page, "orderBy": "4"}
        if brands:
            v["brands"] = brands
        if catalog:
            v["catalogSlug"] = catalog
        if sizes:
            v["sizes"] = sizes
        if conditions:
            v["conditions"] = conditions
        if price_to:
            v["priceTo"] = int(price_to)
        if price_from:
            v["priceFrom"] = int(price_from)
        if characteristics:
            v["characteristics"] = characteristics
        query = PRODUCTS_QUERY
        if search_text:
            v["searchText"] = search_text
            query = PRODUCTS_QUERY.replace("$characteristics: [Int!]) {", "$characteristics: [Int!], $searchText: String) {") \
                .replace("characteristics: $characteristics) {", "characteristics: $characteristics, searchText: $searchText) {")
        data = self._post("WEB_CatalogProducts", query, v)
        p = data["products"]
        return [clean(e["node"]) for e in p["edges"]], bool(p["pageInfo"]["hasNextPage"])

    def products_multi(self, variants: list[tuple[list[int], list[int]]], *, brands: list[int] | None,
                       catalog: str | None = None, sizes: list[int] | None = None, price_to: int | None = None,
                       price_from: int | None = None, first: int = 100, page: int = 1,
                       search_text: str | None = None) -> list[tuple[list[dict], bool]]:
        """Кілька варіантів (стани, характеристики) з однаковими рештою фільтрів — одним HTTP-запитом
        через аліаси GraphQL. Повертає [(товари, є_ще_сторінка)] у порядку variants."""
        return self.products_batch([dict(variants=variants, brands=brands, catalog=catalog, sizes=sizes,
                                         price_to=price_to, price_from=price_from, first=first, page=page,
                                         search_text=search_text)])[0]

    def products_batch(self, queries: list[dict]) -> list[list[tuple[list[dict], bool]]]:
        """Кілька запитів каталогу (кожен — зі своїми варіантами) одним HTTP-запитом через аліаси GraphQL
        (перевірено до 15 аліасів, 9.11.2026). queries: [{variants, brands, catalog, sizes, price_to, price_from,
        first, page, search_text}] → для кожного запиту [(товари, є_ще_сторінка)] у порядку його variants."""
        v: dict = {"orderBy": "4"}
        decl = ["$orderBy: String"]
        parts, aliases = [], []
        for qi, q in enumerate(queries):
            p = f"q{qi}"
            v[f"{p}first"], v[f"{p}page"] = int(q.get("first") or 100), int(q.get("page") or 1)
            decl += [f"${p}first: Int!", f"${p}page: Int!"]
            args = [f"first: ${p}first", f"pageNum: ${p}page", "orderBy: $orderBy"]
            for key, gql, typ in (("brands", "brands", "[Int]"), ("catalog", "catalogSlug", "String"),
                                  ("sizes", "sizes", "[Int!]"), ("price_to", "priceTo", "Int"),
                                  ("price_from", "priceFrom", "Int"), ("search_text", "searchText", "String")):
                val = q.get(key)
                if val:
                    v[f"{p}{gql}"] = int(val) if typ == "Int" else val
                    decl.append(f"${p}{gql}: {typ}")
                    args.append(f"{gql}: ${p}{gql}")
            for vi, (conds, chars) in enumerate(q["variants"]):
                a = f"{p}v{vi}"
                decl += [f"${a}c: [Int]", f"${a}ch: [Int!]"]
                if conds:
                    v[f"{a}c"] = conds
                if chars:
                    v[f"{a}ch"] = chars
                parts.append(f"{a}: products({', '.join(args)}, condition: ${a}c, characteristics: ${a}ch) {{\n"
                             f"    edges {{ node {{\n      {NODE_FIELDS}\n    }} }}\n    pageInfo {{ hasNextPage total }}\n  }}")
                aliases.append((qi, a))
        query = f"query WEB_CatalogProducts({', '.join(decl)}) {{\n  " + "\n  ".join(parts) + "\n}"
        data = self._post("WEB_CatalogProducts", query, v)
        out: list[list[tuple[list[dict], bool]]] = [[] for _ in queries]
        for qi, a in aliases:
            p = data.get(a)
            if p is None:
                raise ShafaError(f"GraphQL: немає відповіді для {a}")
            out[qi].append(([clean(e["node"]) for e in p["edges"]], bool(p["pageInfo"]["hasNextPage"])))
        return out

    def find_brands(self, name: str, first: int = 20) -> list[dict]:
        """Пошук бренду за підрядком назви (запит фільтра брендів сайту, без урахування діакритики).
        Увага: знаходить не всі бренди — частину видно лише в товарах (див. docs/brand_survey.md)."""
        data = self._post("SearchBrands", "query SearchBrands($n: String) { filterBrand(name: $n, first: %d) "
                                          "{ id name } }" % int(first), {"n": name})
        return data.get("filterBrand") or []

    def details(self, product_id: int) -> dict | None:
        data = self._post("WEB_ProductDetailsPageProduct", DETAILS_QUERY, {"productId": int(product_id)})
        return clean(data.get("productDetails"))


def absolute_url(url: str) -> str:
    if url.startswith("http"):
        return url
    return SITE + url
