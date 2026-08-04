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
# 企画ごとの初検出日。セール終了日はAPIから取得できない(dealDetailsは
# 企画セールでは常に空)ため、「いつから掲載しているか」を自前で記録する。
# CIがこのファイルをコミットして毎時実行をまたいで永続化する
STATE_PATH = ROOT / "data" / "campaign_state.json"
# 検出されなくなった企画の状態を保持する日数。検出条件を一時的に
# 満たさなくなっただけで初検出日がリセットされるのを防ぐ猶予期間
STATE_GRACE_DAYS = 14

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
    response: dict, partner_tag: str, min_saving: int,
    dropped_rates: list | None = None
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
            if dropped_rates is not None:
                dropped_rates.append((percent_off or 0) + (points_percent or 0))
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
    campaign_max_pages = config.get("campaign_max_pages", 5)
    campaign_scan_limit = config.get("campaign_scan_limit", 15)
    items_per_campaign = config.get("items_per_campaign", 12)

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
    # 候補に挙がったのに採用しなかった企画を残す。新しい企画が載らないとき、
    # そもそも候補に出ていないのか、セール品が足りず落ちたのかを切り分ける
    skipped = []
    # しきい値を設ける意味があるか判断するため、落とした本の割引率を集める
    all_dropped_rates: list = []
    if candidates:
        print(
            f"企画候補: {len(candidates)}件 "
            f"(うち上位{min(campaign_scan_limit, len(candidates))}件をスキャン)"
        )
    for cand in candidates[:campaign_scan_limit]:
        if len(campaigns) >= max_campaigns:
            break
        items: list[dict] = []
        seen: set[str] = set()
        total = None
        # 不採用のとき、検索が商品を返していないのか、返ってきたが
        # 割引が足りないのかを区別できるようにする
        fetched = 0
        dropped = 0
        campaign_rates: list = []
        for page in range(1, campaign_max_pages + 1):
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
            fetched += len(
                pick(res.get("searchResult") or {}, "items", "Items") or []
            )
            parsed_items, no_disc = parse_items(
                res, partner_tag, min_saving, campaign_rates
            )
            dropped += no_disc
            for parsed in parsed_items:
                if parsed["asin"] not in seen:
                    seen.add(parsed["asin"])
                    items.append(parsed)
            time.sleep(1.2)
            # 商品が1件も返らない企画は開催前か終了済みとみなし深追いしない。
            # 以前は「1ページ目でセール品3冊未満」で打ち切っていたが、
            # 検索順は割引率と無関係なため、対象1000冊の企画でも先頭10件が
            # たまたま値引きの小さい本だと丸ごと捨てられていた
            if page == 1 and not fetched:
                break
            # 掲載枠+シリーズ重複で削られる分が集まったら打ち切る
            if len(items) >= items_per_campaign + 3:
                break
        all_dropped_rates.extend(campaign_rates)
        items.sort(key=sort_key, reverse=True)
        deduped = dedupe_series(items)
        if len(deduped) >= 3:
            campaigns.append(
                {
                    "node_id": cand["id"],
                    "name": cand["name"],
                    "url": (
                        f"https://www.amazon.co.jp/b?node={cand['id']}"
                        f"&tag={partner_tag}"
                    ),
                    "total": total,
                    "items": deduped[:items_per_campaign],
                }
            )
            print(
                f"企画「{cand['name']}」: "
                f"{len(deduped[:items_per_campaign])}冊 (対象約{total}冊)"
            )
        else:
            skipped.append(
                f"{cand['name']}(採用{len(deduped)}/取得{fetched}"
                f"・割引不足{dropped}・対象{total})"
            )

    if skipped:
        print(f"セール品が足りず不採用: {' / '.join(skipped)}")
    if all_dropped_rates:
        buckets = {"0%": 0, "1-9%": 0, "10-14%": 0, "15-19%": 0}
        for r in all_dropped_rates:
            if r <= 0:
                buckets["0%"] += 1
            elif r < 10:
                buckets["1-9%"] += 1
            elif r < 15:
                buckets["10-14%"] += 1
            else:
                buckets["15-19%"] += 1
        total_dropped = len(all_dropped_rates)
        dist = " ".join(
            f"{k}:{v}({round(v / total_dropped * 100)}%)" for k, v in buckets.items()
        )
        print(f"企画内で割引不足として落とした{total_dropped}冊の内訳: {dist}")

    # 企画の初検出日を状態ファイルで管理し、掲載開始日として表示する
    state = {}
    try:
        raw = STATE_PATH.read_text(encoding="utf-8")
        # gitのコンフリクトマーカーが混入したまま
        # コミットされた事故が姉妹サイトで実際に起きたため明示的に検出する
        if "<<<<<<<" in raw or ">>>>>>>" in raw:
            print(
                f"[warn] {STATE_PATH.name} にコンフリクトマーカーが混入しています。"
                "全企画の初検出日がリセットされます",
                file=sys.stderr,
            )
        else:
            state = json.loads(raw)
    except FileNotFoundError:
        pass  # 初回実行時は状態ファイルが無くて当然
    except json.JSONDecodeError as e:
        print(
            f"[warn] {STATE_PATH.name} が壊れています ({e})。"
            "全企画の初検出日がリセットされます",
            file=sys.stderr,
        )
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
    today_dt = now.date()
    today = today_dt.isoformat()
    now_iso = now.isoformat(timespec="seconds")
    new_state = {}
    for c in campaigns:
        entry = state.get(c["node_id"]) or {}
        first_seen = entry.get("first_seen") or today
        # 日付だけではRSSのpubDateに使えないため実時刻も残す。
        # 時刻を持たない既存エントリは、前日夜と紛れないよう正午とみなす
        first_seen_at = entry.get("first_seen_at") or (
            now_iso if not entry.get("first_seen") else f"{first_seen}T12:00:00+09:00"
        )
        c["since"] = first_seen
        c["since_at"] = first_seen_at
        new_state[c["node_id"]] = {
            "first_seen": first_seen,
            "first_seen_at": first_seen_at,
            "last_seen": today,
            "name": c["name"],
        }

    # 今回検出されなかった企画も猶予期間内は状態を保持する。
    # 開催中でも掲載条件(1ページ目にセール品3冊以上)を一時的に満たさず
    # 検出から外れることがあり、即座に削除すると復活時に掲載開始日が
    # 今日にリセットされてしまう
    kept = 0
    for node_id, entry in state.items():
        if node_id in new_state:
            continue
        last_seen = entry.get("last_seen") or entry.get("first_seen")
        try:
            elapsed = (today_dt - datetime.date.fromisoformat(last_seen)).days
        except (TypeError, ValueError):
            continue  # 日付が壊れているエントリは破棄する
        if elapsed <= STATE_GRACE_DAYS:
            new_state[node_id] = entry
            kept += 1
    if kept:
        print(f"(一時的に検出されなかった{kept}企画は掲載開始日を保持)")

    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(new_state, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    # 新しく始まった企画が上に来るよう、掲載開始日の降順で並べる
    campaigns.sort(
        key=lambda c: (c["since"], int(c["node_id"])), reverse=True
    )

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

        genres.append({"name": genre["name"], "items": items})
        print(f"{genre['name']}スキャン: セール品{len(items)}冊 (割引不足で{dropped}冊除外)")

    # ジャンル横断スキャンの結果は「その他のセール本」に統合する。
    # 企画セクションに既に載っている本は除き、掘り出し物だけを見せる
    campaign_asins = {b["asin"] for c in campaigns for b in c["items"]}
    pool: dict[str, dict] = {}
    for genre in genres:
        for b in genre["items"]:
            if b["asin"] not in campaign_asins:
                pool.setdefault(b["asin"], b)
    others = sorted(pool.values(), key=sort_key, reverse=True)
    others = dedupe_series(others)[:24]
    print(f"その他のセール本: {len(others)}冊")

    if len(others) + sum(len(c["items"]) for c in campaigns) == 0:
        # 全企画・その他とも0冊はAPI障害・キー失効の可能性が高い。
        # 空サイトで前回のデプロイを上書きしないよう失敗させる
        print("[error] 全企画・その他とも0冊のため中止します", file=sys.stderr)
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
                "others": others,
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
