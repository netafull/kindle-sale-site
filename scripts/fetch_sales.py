#!/usr/bin/env python3
"""Amazon PA-API v5 (Creators API) からセール中のKindle本を取得して data/sales.json に保存する。

必要な環境変数:
  PAAPI_ACCESS_KEY  : PA-APIのアクセスキー
  PAAPI_SECRET_KEY  : PA-APIのシークレットキー
  PAAPI_PARTNER_TAG : アソシエイトタグ (例: xxxx-22)
"""

from __future__ import annotations

import datetime
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HOST = "webservices.amazon.co.jp"
REGION = "us-west-2"
SERVICE = "ProductAdvertisingAPI"
URI_PATH = "/paapi5/searchitems"
TARGET = "com.amazon.paapi5.v1.ProductAdvertisingAPIv1.SearchItems"

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"
OUTPUT_PATH = ROOT / "data" / "sales.json"

RESOURCES = [
    "ItemInfo.Title",
    "ItemInfo.ByLineInfo",
    "Images.Primary.Medium",
    "Offers.Listings.Price",
    "Offers.Listings.SavingBasis",
    "Offers.Listings.LoyaltyPoints",
]


def sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def build_headers(payload: str, access_key: str, secret_key: str) -> dict:
    """AWS Signature Version 4 でリクエストヘッダーを作る。"""
    now = datetime.datetime.now(datetime.timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")

    canonical_headers = (
        f"content-encoding:amz-1.0\n"
        f"host:{HOST}\n"
        f"x-amz-date:{amz_date}\n"
        f"x-amz-target:{TARGET}\n"
    )
    signed_headers = "content-encoding;host;x-amz-date;x-amz-target"
    payload_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    canonical_request = (
        f"POST\n{URI_PATH}\n\n{canonical_headers}\n{signed_headers}\n{payload_hash}"
    )

    scope = f"{date_stamp}/{REGION}/{SERVICE}/aws4_request"
    string_to_sign = (
        f"AWS4-HMAC-SHA256\n{amz_date}\n{scope}\n"
        + hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()
    )

    k_date = sign(("AWS4" + secret_key).encode("utf-8"), date_stamp)
    k_region = sign(k_date, REGION)
    k_service = sign(k_region, SERVICE)
    k_signing = sign(k_service, "aws4_request")
    signature = hmac.new(
        k_signing, string_to_sign.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    return {
        "Content-Encoding": "amz-1.0",
        "Content-Type": "application/json; charset=utf-8",
        "X-Amz-Date": amz_date,
        "X-Amz-Target": TARGET,
        "Authorization": (
            f"AWS4-HMAC-SHA256 Credential={access_key}/{scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        ),
    }


def search_items(
    access_key: str,
    secret_key: str,
    partner_tag: str,
    *,
    browse_node_id: str | None,
    min_saving_percent: int,
    item_page: int,
) -> dict:
    body = {
        "PartnerTag": partner_tag,
        "PartnerType": "Associates",
        "Marketplace": "www.amazon.co.jp",
        "SearchIndex": "KindleStore",
        "MinSavingPercent": min_saving_percent,
        "ItemPage": item_page,
        "ItemCount": 10,
        "SortBy": "Featured",
        "Resources": RESOURCES,
    }
    if browse_node_id:
        body["BrowseNodeId"] = browse_node_id

    payload = json.dumps(body)
    headers = build_headers(payload, access_key, secret_key)
    req = urllib.request.Request(
        f"https://{HOST}{URI_PATH}",
        data=payload.encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as res:
        return json.loads(res.read().decode("utf-8"))


def parse_items(response: dict, partner_tag: str) -> list[dict]:
    items = []
    for item in response.get("SearchResult", {}).get("Items", []):
        asin = item.get("ASIN")
        title = (
            item.get("ItemInfo", {}).get("Title", {}).get("DisplayValue")
        )
        listings = item.get("Offers", {}).get("Listings", [])
        if not asin or not title or not listings:
            continue
        listing = listings[0]
        price = listing.get("Price", {}).get("Amount")
        basis = listing.get("SavingBasis", {}).get("Amount")
        if price is None:
            continue
        # PA-APIのAmountは浮動小数点数(例: 499.0)で返る。円は整数なので丸める
        price = int(round(price))
        basis = int(round(basis)) if basis is not None else None
        percent_off = None
        if basis and basis > price:
            percent_off = round((basis - price) / basis * 100)

        loyalty = listing.get("LoyaltyPoints") or {}
        points = loyalty.get("Points")
        # LoyaltyPointsにはポイント数しか含まれないため、還元率は価格から算出する
        points_percent = (
            round(points / price * 100) if points and price else None
        )

        contributors = (
            item.get("ItemInfo", {})
            .get("ByLineInfo", {})
            .get("Contributors", [])
        )
        author = ", ".join(
            c["Name"] for c in contributors if c.get("Name")
        ) or None

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
                "image": item.get("Images", {})
                .get("Primary", {})
                .get("Medium", {})
                .get("URL"),
                "url": f"https://www.amazon.co.jp/dp/{asin}?tag={partner_tag}",
            }
        )
    return items


def main() -> int:
    access_key = os.environ.get("PAAPI_ACCESS_KEY")
    secret_key = os.environ.get("PAAPI_SECRET_KEY")
    partner_tag = os.environ.get("PAAPI_PARTNER_TAG")
    if not all([access_key, secret_key, partner_tag]):
        print(
            "環境変数 PAAPI_ACCESS_KEY / PAAPI_SECRET_KEY / PAAPI_PARTNER_TAG "
            "を設定してください",
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
                        access_key,
                        secret_key,
                        partner_tag,
                        browse_node_id=genre.get("browse_node_id"),
                        min_saving_percent=min_saving,
                        item_page=page,
                    )
                    break
                except urllib.error.HTTPError as e:
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
            time.sleep(1.2)  # PA-APIの基本レートは1リクエスト/秒

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
