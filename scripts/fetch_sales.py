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
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

TOKEN_URL = "https://api.amazon.co.jp/auth/o2/token"
API_URL = "https://creatorsapi.amazon/catalog/v1/searchItems"
NODES_URL = "https://creatorsapi.amazon/catalog/v1/getBrowseNodes"
SCOPE = "creatorsapi::default"
MARKETPLACE = "www.amazon.co.jp"

# 「Kindle Events」ノード。開催中のセール企画が子ノードとしてぶら下がる
EVENTS_NODE_ID = "204336703051"

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"
OUTPUT_PATH = ROOT / "data" / "sales.json"

RESOURCES = [
    "itemInfo.title",
    "itemInfo.byLineInfo",
    "itemInfo.classifications",
    "images.primary.medium",
    # savingBasis(定価)とsavings(割引)はpriceリソースに内包されて返る
    "offersV2.listings.price",
    "offersV2.listings.isBuyBoxWinner",
    "offersV2.listings.loyaltyPoints",
]


def series_key(title: str) -> str:
    """同一シリーズの巻違いをまとめるための正規化キーを作る。

    括弧内(巻数・レーベル名)と数字・空白を取り除く。巻違いの表記ゆれ
    (タイトルの繰り返し等)があるため、比較はis_same_seriesの前方一致で行う。
    """
    t = re.sub(r"[（(【\[].*?[）)】\]]", "", title)
    t = re.sub(r"[0-9０-９]+", "", t)
    t = re.sub(r"第.{1,3}巻", "", t)
    return re.sub(r"\s+", "", t) or title


def is_same_series(key: str, seen_keys: set[str]) -> bool:
    """前方一致でシリーズの同一性を判定する。

    「モブサイコ」と「モブサイコモブサイコ」(巻によってタイトル表記が
    繰り返されるゆれ)を同一視するため。誤結合を避けるため、短い方が
    4文字未満の場合は完全一致のみ許す。
    """
    for s in seen_keys:
        short, long_ = (key, s) if len(key) <= len(s) else (s, key)
        if short == long_:
            return True
        if len(short) >= 4 and long_.startswith(short):
            return True
    return False


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


# セール本の発見効率を上げるため複数のソート順で検索する。
# Featuredだけだと割引本の遭遇率が低く、安い順はセール本(99円〜)が
# 上位に集まりやすい
SORT_ORDERS = ["Featured", "Price:LowToHigh"]


def search_items(
    access_token: str,
    partner_tag: str,
    *,
    browse_node_id: str | None,
    item_page: int,
    sort_by: str,
) -> dict:
    # 注意: minSavingPercentは絶対に送らないこと。Creators APIのバグで、
    # このパラメータを付けると検索結果が壊れる(件数が激減し、Kindle本
    # 以外の物理商品が混入し、savings情報も返らなくなる)ことを実データで
    # 確認済み。割引の絞り込みはparse_items側のクライアントフィルタで行う
    body = {
        "partnerTag": partner_tag,
        "partnerType": "Associates",
        "marketplace": MARKETPLACE,
        "searchIndex": "KindleStore",
        "itemPage": item_page,
        "itemCount": 10,
        "sortBy": sort_by,
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


def get_campaign_candidates(access_token: str, partner_tag: str) -> list[dict]:
    """Kindle Eventsノードの子から、セール企画の候補一覧を新しい順に返す。

    子ノードには内部コード名(MD_ST_KU_..等)やテスト・終了済み企画も
    混ざっているため、日本語名を持つものだけに絞る。実際に開催中か
    どうかは呼び出し側が商品検索で確認する。
    """
    body = {
        "partnerTag": partner_tag,
        "partnerType": "Associates",
        "marketplace": MARKETPLACE,
        "browseNodeIds": [EVENTS_NODE_ID],
        "resources": ["browseNodes.children"],
    }
    req = urllib.request.Request(
        NODES_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "x-marketplace": MARKETPLACE,
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as res:
        payload = json.loads(res.read().decode("utf-8"))

    candidates = []
    for node in (payload.get("browseNodesResult") or {}).get("browseNodes") or []:
        for child in node.get("children") or []:
            name = (child.get("displayName") or "").strip().strip('"').strip()
            child_id = child.get("id")
            if not child_id or not name:
                continue
            if not re.search(r"[ぁ-んァ-ヶ一-龯]", name):
                continue  # 内部コード名(英数字のみ)を除外
            if re.search(r"test", name, re.IGNORECASE):
                continue
            candidates.append({"id": child_id, "name": name})
    # ノードIDは作成順に増えるようなので、ID降順=新しい企画順とみなす
    candidates.sort(key=lambda c: int(c["id"]), reverse=True)
    return candidates


def search_with_retry(
    auth: dict,
    partner_tag: str,
    *,
    browse_node_id: str | None,
    item_page: int,
    sort_by: str,
    label: str,
) -> dict:
    """search_itemsを429/401/ネットワークエラーに耐性を持たせて呼ぶ。

    authは {"token", "id", "secret"} を持つdict。401時はtokenを再取得して
    差し替える(呼び出し側にも新tokenが見えるようdictで持ち回る)。
    """
    for attempt in range(3):
        try:
            return search_items(
                auth["token"],
                partner_tag,
                browse_node_id=browse_node_id,
                item_page=item_page,
                sort_by=sort_by,
            )
        except urllib.error.HTTPError as e:
            if e.code == 401 and attempt < 2:
                try:
                    auth["token"] = get_access_token(auth["id"], auth["secret"])
                except (urllib.error.URLError, TimeoutError, OSError):
                    pass
                continue
            if e.code == 429 and attempt < 2:
                time.sleep(5 * (attempt + 1))
                continue
            print(
                f"[warn] {label}: HTTP {e.code} "
                f"{e.read().decode('utf-8', 'replace')[:300]}",
                file=sys.stderr,
            )
            return {}
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            if attempt < 2:
                time.sleep(5 * (attempt + 1))
                continue
            print(f"[warn] {label}: {e}", file=sys.stderr)
            return {}
    return {}


def dedupe_series(items: list[dict]) -> list[dict]:
    """お得度順に並んだリストから、同一シリーズの巻違いを畳む。"""
    series_seen: set[str] = set()
    deduped = []
    for item in items:
        key = series_key(item["title"])
        if is_same_series(key, series_seen):
            continue
        series_seen.add(key)
        deduped.append(item)
    return deduped


def parse_items(
    response: dict, partner_tag: str, min_saving: int
) -> tuple[list[dict], int]:
    """(掲載対象のリスト, 割引不足で除外した件数) を返す。"""
    items = []
    no_discount = 0
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

        # 複数出品がある場合は購入ボックス(実際に買われる出品)を優先する
        listing = next(
            (
                l
                for l in listings
                if pick(l, "isBuyBoxWinner", "IsBuyBoxWinner")
            ),
            listings[0],
        )
        price_block = pick(listing, "price", "Price") or {}
        money = pick(price_block, "money", "Money") or {}
        price = pick(money, "amount", "Amount")
        if price is None:
            continue
        # 金額は浮動小数点数(例: 499.0)で返る。円は整数なので丸める
        price = int(round(price))
        # ¥0の本は除外する。青空文庫系の恒久無料本が「100%OFF」として
        # ランキング上位を占拠してしまい、セール情報としてはノイズになる
        if price == 0:
            no_discount += 1
            continue

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

        # minSavingPercentはAPI側で無視されることが実データで確認された
        # (割引なし商品が多数返ってくる)ため、割引の有無はここで判定する。
        # 割引率とポイント還元率の合算が閾値を下回る本は掲載しない
        if (percent_off or 0) + (points_percent or 0) < min_saving:
            no_discount += 1
            continue

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
    return items, no_discount


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
    max_campaigns = config.get("max_campaigns", 6)
    campaign_pages = config.get("campaign_pages", 2)
    campaign_scan_limit = config.get("campaign_scan_limit", 15)

    auth = {
        "token": access_token,
        "id": credential_id,
        "secret": credential_secret,
    }
    sort_key = lambda x: (x["percent_off"] or 0) + (x["points_percent"] or 0)  # noqa: E731

    # --- セール企画 (Kindle Eventsの子ノードから自動発見) ---
    campaigns = []
    try:
        candidates = get_campaign_candidates(auth["token"], partner_tag)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        print(f"[warn] 企画一覧の取得に失敗: {e}", file=sys.stderr)
        candidates = []
    for cand in candidates[:campaign_scan_limit]:
        if len(campaigns) >= max_campaigns:
            break
        items: list[dict] = []
        seen: set[str] = set()
        total = None
        for page in range(1, campaign_pages + 1):
            res = search_with_retry(
                auth,
                partner_tag,
                browse_node_id=cand["id"],
                item_page=page,
                sort_by="Featured",
                label=f"企画 {cand['name']} page {page}",
            )
            if total is None:
                total = (res.get("searchResult") or {}).get("totalResultCount")
            parsed_items, _ = parse_items(res, partner_tag, min_saving)
            for parsed in parsed_items:
                if parsed["asin"] not in seen:
                    seen.add(parsed["asin"])
                    items.append(parsed)
            time.sleep(1.2)
            # 1ページ目でセール品がほぼ無い企画は終了済みとみなし深追いしない
            if page == 1 and len(items) < 3:
                break
        items.sort(key=sort_key, reverse=True)
        deduped = dedupe_series(items)
        if len(deduped) >= 3:
            campaigns.append(
                {
                    "name": cand["name"],
                    "url": (
                        f"https://www.amazon.co.jp/b?node={cand['id']}"
                        f"&tag={partner_tag}"
                    ),
                    "total": total,
                    "items": deduped[:12],
                }
            )
            print(f"企画「{cand['name']}」: {len(deduped[:12])}冊 (対象約{total}冊)")

    # --- ジャンル別 ---
    genres = []
    for genre in config["genres"]:
        seen = set()
        items = []
        dropped = 0
        # 旧形式(browse_node_id: 単一)と新形式(browse_node_ids: 配列)の両対応
        node_ids = genre.get("browse_node_ids") or [genre.get("browse_node_id")]
        for node_id, sort_by, page in (
            (n, s, p)
            for n in node_ids
            for s in SORT_ORDERS
            for p in range(1, pages + 1)
        ):
            res = search_with_retry(
                auth,
                partner_tag,
                browse_node_id=node_id,
                item_page=page,
                sort_by=sort_by,
                label=f"{genre['name']} page {page}",
            )
            parsed_items, no_discount = parse_items(res, partner_tag, min_saving)
            dropped += no_discount
            for parsed in parsed_items:
                if parsed["asin"] not in seen:
                    seen.add(parsed["asin"])
                    items.append(parsed)
            time.sleep(1.2)

        # 値引き率とポイント還元率を合算した「実質お得度」で並べ替え、
        # 同一シリーズの巻違いは最もお得な1冊だけ残す
        items.sort(key=sort_key, reverse=True)
        deduped = dedupe_series(items)
        genres.append({"name": genre["name"], "items": deduped})
        print(
            f"{genre['name']}: {len(deduped)}冊 "
            f"(割引不足で{dropped}冊、シリーズ重複で{len(items) - len(deduped)}冊除外)"
        )

    if sum(len(g["items"]) for g in genres) + sum(
        len(c["items"]) for c in campaigns
    ) == 0:
        # 全ジャンル・全企画0冊はAPI障害・キー失効の可能性が高い。
        # 空サイトで前回のデプロイを上書きしないよう失敗させる
        print("[error] 全ジャンル・全企画で0冊のため中止します", file=sys.stderr)
        return 1

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(
            {
                "fetched_at": datetime.datetime.now(
                    datetime.timezone.utc
                ).isoformat(),
                "min_saving_percent": min_saving,
                "campaigns": campaigns,
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
