#!/usr/bin/env python3
"""Amazon Creators API からセール中のKindle本を取得して data/sales.json に保存する。

2026年、Amazonは旧PA-API v5 (AWS Signature V4認証) を廃止し、
OAuth2認証のCreators APIに全面移行した。認証情報バージョン3.3
(Far East: JP/IN/AU) 向けのLwA(Login with Amazon)フローを使う。

必要な環境変数:
  CREATORSAPI_CREDENTIAL_ID     : Creators APIの認証情報ID
  CREATORSAPI_CREDENTIAL_SECRET : Creators APIの認証情報シークレット
  CREATORSAPI_PARTNER_TAG       : アソシエイトタグ (例: xxxx-22)
"""

from __future__ import annotations

import datetime
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

TOKEN_URL = "https://api.amazon.co.jp/auth/o2/token"
API_URL = "https://creatorsapi.amazon/catalog/v1/searchItems"
SCOPE = "creatorsapi::default"
MARKETPLACE = "www.amazon.co.jp"

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"
OUTPUT_PATH = ROOT / "data" / "sales.json"

RESOURCES = [
    "itemInfo.title",
    "itemInfo.byLineInfo",
    "itemInfo.classifications",
    "images.primary.medium",
    "offersV2.listings.price",
    "offersV2.listings.loyaltyPoints",
]


def pick(d: dict, *keys):
    """複数の想定キー名から最初に見つかった値を返す(レスポンスの大文字小文字ゆれ対策)。"""
    for key in keys:
        if key in d:
            return d[key]
    return None


def get_access_token(credential_id: str, credential_secret: str) -> str:
    body = json.dumps(
        {
            "grant_type": "client_credentials",
            "client_id": credential_id,
            "client_secret": credential_secret,
            "scope": SCOPE,
        }
    )
    req = urllib.request.Request(
        TOKEN_URL,
        data=body.encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as res:
        payload = json.loads(res.read().decode("utf-8"))
    return payload["access_token"]


def search_items(
    access_token: str,
    partner_tag: str,
    *,
    browse_node_id: str | None,
    min_saving_percent: int,
    item_page: int,
) -> dict:
    body = {
        "partnerTag": partner_tag,
        "partnerType": "Associates",
        "marketplace": MARKETPLACE,
        "searchIndex": "KindleStore",
        "minSavingPercent": min_saving_percent,
        "itemPage": item_page,
        "itemCount": 10,
        "sortBy": "Featured",
        "resources": RESOURCES,
    }
    if browse_node_id:
        body["browseNodeId"] = browse_node_id

    payload = json.dumps(body)
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "x-marketplace": MARKETPLACE,
    }
    req = urllib.request.Request(
        API_URL, data=payload.encode("utf-8"), headers=headers, method="POST"
    )
    with urllib.request.urlopen(req, timeout=30) as res:
        return json.loads(res.read().decode("utf-8"))


def parse_items(response: dict, partner_tag: str) -> list[dict]:
    items = []
    search_result = pick(response, "searchResult", "SearchResult") or {}
    for item in pick(search_result, "items", "Items") or []:
        asin = pick(item, "asin", "ASIN")
        item_info = pick(item, "itemInfo", "ItemInfo") or {}
        title = pick(pick(item_info, "title", "Title") or {}, "displayValue", "DisplayValue")
        offers = pick(item, "offersV2", "OffersV2") or {}
        listings = pick(offers, "listings", "Listings") or []
        if not asin or not title or not listings:
            continue

        # searchIndex=KindleStoreだけでは物理商品が紛れ込むため、
        # productGroupに"Ebook"を含むものだけに絞り込む。
        # bindingは"Kindle版"(雑誌)や"コミック"(コミック)などジャンルにより
        # 表記が割れて信頼できないが、productGroupは実データで
        # "Ebook" / "Digital Ebook Purchase" のように一貫していた
        classifications = pick(item_info, "classifications", "Classifications") or {}
        product_group = pick(classifications, "productGroup", "ProductGroup") or {}
        product_group_value = pick(product_group, "displayValue", "DisplayValue") or ""
        if "ebook" not in product_group_value.lower():
            continue

        listing = listings[0]
        price_block = pick(listing, "price", "Price") or {}
        money = pick(price_block, "money", "Money") or {}
        price = pick(money, "amount", "Amount")
        if price is None:
            continue
        # 金額は浮動小数点数(例: 499.0)で返る。円は整数なので丸める
        price = int(round(price))

        basis_block = pick(price_block, "savingBasis", "SavingBasis") or {}
        basis_money = pick(basis_block, "money", "Money") or {}
        basis = pick(basis_money, "amount", "Amount")
        basis = int(round(basis)) if basis is not None else None

        savings = pick(price_block, "savings", "Savings") or {}
        percent_off = pick(savings, "percentage", "Percentage")
        if percent_off is None and basis and basis > price:
            percent_off = round((basis - price) / basis * 100)

        loyalty = pick(listing, "loyaltyPoints", "LoyaltyPoints") or {}
        points = pick(loyalty, "points", "Points")
        # ポイント数のみが返るため、還元率は価格から自前で算出する
        points_percent = (
            round(points / price * 100) if points and price else None
        )

        contributors = pick(
            pick(item_info, "byLineInfo", "ByLineInfo") or {},
            "contributors",
            "Contributors",
        ) or []
        author = ", ".join(
            n for c in contributors if (n := pick(c, "name", "Name"))
        ) or None

        images = pick(item, "images", "Images") or {}
        medium = pick(pick(images, "primary", "Primary") or {}, "medium", "Medium") or {}
        image = pick(medium, "url", "URL")

        url = pick(item, "detailPageURL", "DetailPageURL") or (
            f"https://www.amazon.co.jp/dp/{asin}?tag={partner_tag}"
        )

        items.append(
            {
                "asin": asin,
                "title": title,
                "author": author,
                "price": price,
                "list_price": basis,
                "percent_off": percent_off,
                "points": points,
                "points_percent": points_percent,
                "image": image,
                "url": url,
            }
        )
    return items


def main() -> int:
    credential_id = os.environ.get("CREATORSAPI_CREDENTIAL_ID")
    credential_secret = os.environ.get("CREATORSAPI_CREDENTIAL_SECRET")
    partner_tag = os.environ.get("CREATORSAPI_PARTNER_TAG")
    if not all([credential_id, credential_secret, partner_tag]):
        print(
            "環境変数 CREATORSAPI_CREDENTIAL_ID / CREATORSAPI_CREDENTIAL_SECRET / "
            "CREATORSAPI_PARTNER_TAG を設定してください",
            file=sys.stderr,
        )
        return 1

    try:
        access_token = get_access_token(credential_id, credential_secret)
    except urllib.error.HTTPError as e:
        print(
            f"[error] トークン取得に失敗: HTTP {e.code} "
            f"{e.read().decode('utf-8', 'replace')[:300]}",
            file=sys.stderr,
        )
        return 1

    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    min_saving = config.get("min_saving_percent", 20)
    pages = config.get("pages_per_genre", 3)

    genres = []
    for genre in config["genres"]:
        seen: set[str] = set()
        items: list[dict] = []
        for page in range(1, pages + 1):
            for attempt in range(3):
                try:
                    res = search_items(
                        access_token,
                        partner_tag,
                        browse_node_id=genre.get("browse_node_id"),
                        min_saving_percent=min_saving,
                        item_page=page,
                    )
                    break
                except urllib.error.HTTPError as e:
                    if e.code == 401 and attempt < 2:
                        # トークン切れ。再取得して1回だけ再試行する
                        access_token = get_access_token(credential_id, credential_secret)
                        continue
                    if e.code == 429 and attempt < 2:
                        time.sleep(5 * (attempt + 1))
                        continue
                    print(
                        f"[warn] {genre['name']} page {page}: HTTP {e.code} "
                        f"{e.read().decode('utf-8', 'replace')[:300]}",
                        file=sys.stderr,
                    )
                    res = {}
                    break
                except (urllib.error.URLError, TimeoutError, OSError) as e:
                    if attempt < 2:
                        time.sleep(5 * (attempt + 1))
                        continue
                    print(
                        f"[warn] {genre['name']} page {page}: {e}",
                        file=sys.stderr,
                    )
                    res = {}
                    break
            for parsed in parse_items(res, partner_tag):
                if parsed["asin"] not in seen:
                    seen.add(parsed["asin"])
                    items.append(parsed)
            time.sleep(1.2)

        # 値引き率とポイント還元率を合算した「実質お得度」で並べ替える
        items.sort(
            key=lambda x: (x["percent_off"] or 0) + (x["points_percent"] or 0),
            reverse=True,
        )
        genres.append({"name": genre["name"], "items": items})
        print(f"{genre['name']}: {len(items)}冊")

    if sum(len(g["items"]) for g in genres) == 0:
        # 全ジャンル0冊はAPI障害・キー失効の可能性が高い。
        # 空サイトで前回のデプロイを上書きしないよう失敗させる
        print("[error] 全ジャンルで0冊のため中止します", file=sys.stderr)
        return 1

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(
            {
                "fetched_at": datetime.datetime.now(
                    datetime.timezone.utc
                ).isoformat(),
                "min_saving_percent": min_saving,
                "genres": genres,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"saved: {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
