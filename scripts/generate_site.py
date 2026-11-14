#!/usr/bin/env python3
"""data/sales.json から docs/index.html と docs/rss.xml を生成する。"""

from __future__ import annotations

import datetime
import html
import json
import re
from pathlib import Path

from fetch_sales import is_manga_campaign_name

ROOT = Path(__file__).resolve().parent.parent
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
DATA_PATH = ROOT / "data" / "sales.json"
DOCS = ROOT / "docs"

CSS = """
:root {
  --bg: #fafaf7; --card: #ffffff; --text: #1a1a1a; --muted: #6b6b6b;
  --accent: #e47911; --line: #e5e2dc; --badge-hi: #d0342c; --badge-mid: #e47911;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #14151a; --card: #1e2027; --text: #e8e8e6; --muted: #9a9a96;
    --line: #2c2e36;
  }
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  background: var(--bg); color: var(--text);
  font-family: "Hiragino Sans", "Noto Sans JP", sans-serif;
  line-height: 1.6;
}
header { padding: 28px 16px 12px; max-width: 960px; margin: 0 auto; }
header h1 { font-size: 24px; }
header h1 a { color: var(--text); text-decoration: none;
  display: inline-flex; align-items: center; gap: 8px; }
/* ロゴは文字とほぼ同じ高さに揃える(96px画像を縮小して表示) */
header h1 img { width: 44px; height: 44px; }
header p { color: var(--muted); font-size: 13px; margin-top: 4px; }
.sites { margin-top: 10px; display: flex; gap: 8px; flex-wrap: wrap;
  align-items: baseline; }
.sites .lbl { font-size: 12px; color: var(--muted); }
.sites a { font-size: 12px; padding: 3px 10px; border-radius: 999px;
  border: 1px solid var(--line); background: var(--card);
  color: var(--text); text-decoration: none; }
.sites a:hover { border-color: var(--accent); color: var(--accent); }
footer .sites { margin-top: 10px; }
main { max-width: 960px; margin: 0 auto; padding: 8px 16px 48px; }
h2 { font-size: 18px; margin: 0; padding-left: 10px;
  border-left: 4px solid var(--accent); display: inline; }
details { margin-top: 28px; }
summary { cursor: pointer; list-style: none; user-select: none; }
summary::-webkit-details-marker { display: none; }
summary::before { content: "▼"; font-size: 11px; color: var(--muted);
  margin-right: 8px; }
details:not([open]) summary::before { content: "▶"; }
summary:hover h2 { color: var(--accent); }
details > .grid, details > .empty { margin-top: 12px; }
.grid { display: grid; gap: 10px;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); }
/* Auto ads廃止に伴う手動広告枠。グリッド内ではカードの1つとして、
   ヘッダー直下では単独の帯として収まるよう幅を960pxに揃える */
/* width:100%指定必須。margin:auto単独だとグリッド内では
   shrink-to-fitになり、中身がまだ無い広告は幅0に潰れて出ない。
   overflowは切らない(広告の一部が隠れるとポリシー違反になりうる) */
.ad-slot { width: 100%; max-width: 960px; margin: 0 auto;
  background: var(--card); border: 1px solid var(--line);
  border-radius: 10px; padding: 12px; text-align: center; }
/* 広告が配信されなかった枠は畳む。枠線とパディングだけの空の箱が
   カードの間に残らないようにする。判定が出るまでは表示のままにする
   (幅0だとAdSenseがサイズを決められず配信自体が失敗するため) */
.ad-slot:has(ins[data-ad-status="unfilled"]) { display: none; }
.book { display: flex; gap: 12px; background: var(--card);
  border: 1px solid var(--line); border-radius: 10px; padding: 12px;
  text-decoration: none; color: var(--text); }
.book:hover { border-color: var(--accent); }
/* flexアイテムはデフォルトでmin-width:autoのため、長い英数字が
   続くタイトルがあるとカード枠をはみ出す。0にして縮小を許可する */
.book > div { min-width: 0; }
.book img { width: 60px; height: 86px; object-fit: cover; border-radius: 4px;
  flex-shrink: 0; background: var(--line); }
.book .t { font-size: 14px; font-weight: 600; display: -webkit-box;
  -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.book .a { font-size: 12px; color: var(--muted); margin-top: 2px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.price { margin-top: 6px; font-size: 14px; }
.price .now { font-weight: 700; color: var(--badge-hi); }
.price .was { font-size: 12px; color: var(--muted);
  text-decoration: line-through; margin-left: 6px; }
.off { display: inline-block; font-size: 11px; font-weight: 700;
  color: #fff; background: var(--badge-mid); border-radius: 4px;
  padding: 1px 6px; margin-left: 6px; vertical-align: 1px; }
.off.hi { background: var(--badge-hi); }
.points { font-size: 11px; color: #0a7d3c; font-weight: 600; margin-top: 2px; }
@media (prefers-color-scheme: dark) { .points { color: #4fd689; } }
.group { max-width: 960px; margin: 24px auto 0; padding: 0 16px;
  font-size: 13px; font-weight: 700; color: var(--muted);
  letter-spacing: 0.08em; }
/* グリッド末尾の「続きを見る」カード。書影が無いぶん中央揃えにして
   他のカードと高さを合わせる */
.book.more { align-items: center; justify-content: center;
  border-style: dashed; background: transparent; }
.book.more:hover { background: var(--card); }
.book.more .more-i { font-size: 22px; flex-shrink: 0; }
.book.more .more-t { font-size: 14px; font-weight: 600;
  color: var(--accent); line-height: 1.4; }
.cmeta { color: var(--muted); font-size: 13px; margin: 8px 0 0 19px; }
/* 見出しに添えるセール規模・掲載開始日。企画名より控えめに見せる */
.hmeta { font-size: 13px; font-weight: normal; color: var(--muted); }
.cmeta a { color: var(--accent); }
.cmeta-link { display: inline-block; margin: 8px 0 0 19px; padding: 6px 14px;
  background: var(--accent); color: #fff; border-radius: 999px;
  font-size: 13px; font-weight: 600; text-decoration: none; }
.cmeta-link:hover { opacity: 0.85; }
footer { max-width: 960px; margin: 0 auto; padding: 16px;
  color: var(--muted); font-size: 12px; border-top: 1px solid var(--line); }
.empty { color: var(--muted); font-size: 14px; padding: 12px 0; }
/* サイトの説明。訪問者の目的(セール情報)を邪魔しないよう本文の最後に置く。
   AIは位置に関わらずページ全体を読むため、下でも検索・AI向けの効果は落ちない */
.about { max-width: 960px; margin: 40px auto 0; padding: 20px 16px 0;
  border-top: 1px solid var(--line); color: var(--muted); font-size: 13px;
  line-height: 1.9; }
.about h2 { font-size: 14px; border-left-width: 3px; margin-bottom: 8px;
  color: var(--text); }
.about p { margin-top: 8px; }
"""


def esc(s):
    return html.escape(s or "", quote=True)


# AdSenseダッシュボードではvignette(全画面)広告をサブドメイン単位で
# 無効化できないため、リンクごとにdata-google-vignette="false"を付与する
def render_book(item: dict) -> str:
    off = item.get("percent_off")
    off_html = ""
    if off:
        cls = "off hi" if off >= 50 else "off"
        off_html = f'<span class="{cls}">{off}%OFF</span>'
    was_html = (
        f'<span class="was">&yen;{int(item["list_price"]):,}</span>'
        if item.get("list_price")
        else ""
    )
    img_html = (
        f'<img src="{esc(item.get("image"))}" alt="{esc(item["title"])}" loading="lazy">'
        if item.get("image")
        else "<img alt=''>"
    )
    author = f'<div class="a">{esc(item["author"])}</div>' if item.get("author") else ""
    points_html = ""
    if item.get("points"):
        pct = item.get("points_percent")
        pct_txt = f"{pct}%還元" if pct else "還元"
        points_html = f'<div class="points">+{item["points"]}pt ({pct_txt})</div>'
    return f"""<a class="book" href="{esc(item["url"])}" data-google-vignette="false" target="_blank" rel="noopener sponsored">
  {img_html}
  <div>
    <div class="t">{esc(item["title"])}</div>
    {author}
    <div class="price"><span class="now">&yen;{int(item["price"]):,}</span>{was_html}{off_html}</div>
    {points_html}
  </div>
</a>"""


def render_ad_slot() -> str:
    """手動設置のディスプレイ広告ユニット。

    Auto adsはサブドメイン単位でヴィネット/アンカー広告を無効化できな
    かったため除外し、代わりにこの広告ユニット1種類をヘッダー直下と
    カード一覧に手動で配置する。adsense_ad_slotが未設定なら何も出さない
    """
    ad_slot = CONFIG.get("adsense_ad_slot", "")
    adsense_id = CONFIG.get("adsense_client_id", "")
    if not ad_slot or not adsense_id:
        return ""
    return f"""<div class="ad-slot">
<ins class="adsbygoogle"
     style="display:block"
     data-ad-client="{esc(adsense_id)}"
     data-ad-slot="{esc(ad_slot)}"
     data-ad-format="rectangle"
     data-full-width-responsive="true"></ins>
<script>
     (adsbygoogle = window.adsbygoogle || []).push({{}});
</script>
</div>"""


AD_EVERY = 16


def intersperse_ads(cards: list[str], every: int = AD_EVERY) -> str:
    """カード一覧に広告枠を16件おきに挟み込む。"""
    ad = render_ad_slot()
    if not ad:
        return "\n".join(cards)
    out = []
    for i, c in enumerate(cards, 1):
        out.append(c)
        if i % every == 0:
            out.append(ad)
    return "\n".join(out)


def render_ga_tag() -> str:
    """Google Analyticsのタグ。ga_measurement_idが未設定なら何も出さない"""
    ga_id = CONFIG.get("ga_measurement_id", "")
    if not ga_id:
        return ""
    return f"""<script async src="https://www.googletagmanager.com/gtag/js?id={esc(ga_id)}"></script>
<script>
window.dataLayer = window.dataLayer || [];
function gtag(){{dataLayer.push(arguments);}}
gtag('js', new Date());
gtag('config', '{esc(ga_id)}');
</script>"""


def render_adsense_tag() -> str:
    """AdSenseの広告コード。ads.txtはルートドメイン(netaful.jp)のものが
    サブドメインにも適用されるため、各サイトでの設置は不要"""
    adsense_id = CONFIG.get("adsense_client_id", "")
    if not adsense_id:
        return ""
    return (
        '<script async src="https://pagead2.googlesyndication.com/pagead/js/'
        f'adsbygoogle.js?client={esc(adsense_id)}" crossorigin="anonymous"></script>'
    )


def render_related_html() -> str:
    """姉妹サイト・運営ブログへの相互リンク(ヘッダーとフッターの両方に出す)"""
    related = CONFIG.get("related_sites") or []
    if not related:
        return ""
    links = "\n".join(
        f'<a href="{esc(s["url"])}" data-google-vignette="false">{esc(s["name"])}'
        + (f'<span class="lbl"> {esc(s["desc"])}</span>' if s.get("desc") else "")
        + "</a>"
        for s in related
    )
    return f'<div class="sites"><span class="lbl">関連サイト</span>\n{links}\n</div>'


def render_policy_link() -> str:
    """メディアポリシー(プライバシーポリシー・AdSenseのCookie告知を含む)は
    netaful.jp/policy.html に既にある。各サイトに複製せずリンクで参照する"""
    policy_url = CONFIG.get("policy_url", "")
    if not policy_url:
        return ""
    return (
        f'｜ <a href="{esc(policy_url)}" data-google-vignette="false" '
        f'style="color:inherit">メディアポリシー</a>\n'
    )


def generate_html(data: dict, identity_nav: str = "") -> str:
    fetched = datetime.datetime.fromisoformat(data["fetched_at"]).astimezone(
        datetime.timezone(datetime.timedelta(hours=9))
    )
    updated = fetched.strftime("%Y年%m月%d日 %H:%M")

    campaigns = data.get("campaigns") or []
    others = data.get("others") or []

    def head_meta(c: dict) -> str:
        """見出しに添える情報(セール規模と掲載開始日)。

        3件目以降は畳んだ状態で表示するため、見出しだけでセールの
        規模と新しさが分かるようにしておく。
        """
        parts = []
        scale = scale_text(c.get("total"))
        if scale:
            parts.append(scale)
        since = c.get("since")
        if since:
            try:
                d = datetime.date.fromisoformat(since)
                parts.append(f"{d.month}/{d.day}〜")
            except ValueError:
                pass
        return f" 【{' ・ '.join(parts)}】" if parts else ""

    sections = []
    if campaigns:
        sections.append('<p class="group">開催中のセール企画 (新着順)</p>')
    for i, c in enumerate(campaigns):
        # グリッド末尾に「続きを見る」カードを、途中に広告枠を置くぶん、
        # 本のカードを削って列数(最大3)の倍数を保ち、末尾行が欠けないよう
        # にする。広告枠もグリッドの1マスを占めるので冊数の計算に含める
        n = len(c["items"])
        while n > 1 and (n + n // AD_EVERY + 1) % 3 != 0:
            n -= 1
        shown = c["items"][:n]
        books = intersperse_ads([render_book(b) for b in shown])
        # 上部のボタンは本を見終わった時点では画面外に流れているため、
        # 読了直後の「もっと見たい」を受け止める導線として機能する
        rest = c["total"] - len(shown) if c.get("total") else 0
        rest_txt = f"ほか約{rest:,}冊" if rest > 0 else "対象本"
        books += (
            f'\n<a class="book more" href="{esc(c["url"])}" '
            f'data-google-vignette="false" target="_blank" rel="noopener sponsored">'
            f'<span class="more-i">🛒</span>'
            f'<div><div class="more-t">{rest_txt}を<br>Amazonで見る</div></div>'
            f"</a>"
        )
        # 企画数が多くページが極端に縦長になるため、3件目以降は畳んでおく。
        # 一覧性を保ちつつ、新着2件はすぐ中身が見える状態にする
        opened = " open" if i < 2 else ""
        sections.append(
            f'<details{opened} id="c{i}">\n'
            f'<summary><h2>🔥 {esc(c["name"])}'
            f'<span class="hmeta">{head_meta(c)}</span></h2></summary>\n'
            f'<a class="cmeta-link" href="{esc(c["url"])}" '
            f'data-google-vignette="false" target="_blank" rel="noopener sponsored">'
            f'🛒 このセールの対象本をAmazonですべて見る</a>\n'
            f'<div class="grid">\n{books}\n</div>\n'
            f'</details>'
        )

    if others:
        books = intersperse_ads([render_book(b) for b in others])
        sections.append(
            '<details open id="others">\n'
            f'<summary><h2>その他のセール本 ({len(others)}冊)</h2></summary>\n'
            f'<div class="grid">\n{books}\n</div>\n'
            '</details>'
        )

    site_url = CONFIG.get("site_url", "")
    # 検索結果用の説明文。ヘッダーに出す短い site_description とは別に持つ
    meta_description = CONFIG.get("meta_description") or CONFIG["site_description"]
    tagline = CONFIG.get("site_tagline", "")
    page_title = (
        f'{CONFIG["site_title"]}｜{tagline}' if tagline else CONFIG["site_title"]
    )
    gsv = CONFIG.get("google_site_verification", "")
    gsv_tag = (
        f'<meta name="google-site-verification" content="{esc(gsv)}">' if gsv else ""
    )
    # 姉妹サイト・運営ブログへの相互リンク(ヘッダーとフッターの両方に出す)
    # サイトの説明。データ元・更新頻度・掲載基準・運営者を明記して、
    # 検索エンジンやAIが「このサイトは何者か」を判断できるようにする
    about = CONFIG.get("about") or []
    about_html = ""
    if about:
        paras = "\n".join(f"<p>{esc(x)}</p>" for x in about)
        about_html = (
            f'<section class="about">\n'
            f'<h2>{esc(CONFIG["site_title"])}について</h2>\n{paras}\n</section>'
        )

    related_html = render_related_html()
    policy_link = render_policy_link()

    adsense_tag = render_adsense_tag()
    header_ad = render_ad_slot()

    ga_tag = render_ga_tag()

    # 構造化データ: サイト情報と開催中セール企画の一覧
    json_ld = json.dumps(
        [
            {
                "@context": "https://schema.org",
                "@type": "WebSite",
                "name": CONFIG["site_title"],
                "url": site_url,
                "description": CONFIG["site_description"],
                # 毎時更新はこのサイトの強みだが、画面上の「最終更新」表記は
                # 機械には読めない。検索エンジンやAIに鮮度を伝えるため
                # 構造化データにも入れる
                "dateModified": fetched.isoformat(timespec="seconds"),
            },
            {
                "@context": "https://schema.org",
                "@type": "ItemList",
                "name": "開催中のKindle本セール企画",
                "itemListElement": [
                    {
                        "@type": "ListItem",
                        "position": i + 1,
                        "name": c["name"],
                        "url": c["url"],
                    }
                    for i, c in enumerate(campaigns)
                ],
            },
        ],
        ensure_ascii=False,
    ).replace("</", "<\\/")

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(page_title)}</title>
<meta name="description" content="{esc(meta_description)}">
<link rel="canonical" href="{esc(site_url)}">
{gsv_tag}
{ga_tag}
{adsense_tag}
<link rel="icon" type="image/png" sizes="96x96" href="assets/favicon.png">
<link rel="apple-touch-icon" href="assets/apple-touch-icon.png">
<meta property="og:type" content="website">
<meta property="og:title" content="{esc(page_title)}">
<meta property="og:description" content="{esc(meta_description)}">
<meta property="og:url" content="{esc(site_url)}">
<meta property="og:site_name" content="{esc(CONFIG["site_title"])}">
<meta property="og:locale" content="ja_JP">
<meta property="og:image" content="{esc(site_url)}assets/ogp.jpg">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<link rel="alternate" type="application/rss+xml" title="RSS" href="rss.xml">
<script type="application/ld+json">{json_ld}</script>
<style>{CSS}</style>
</head>
<body>
<header>
<h1><a href="./" data-google-vignette="false"><img src="assets/logo.png" alt="" width="44" height="44">{esc(CONFIG["site_title"])}</a></h1>
<p>{esc(CONFIG["site_description"])} ｜ 割引率とポイント還元率の合計が{data["min_saving_percent"]}%以上の本を掲載 ｜ 最終更新: {updated}</p>
</header>
{header_ad}
<main>
{identity_nav}
{chr(10).join(sections)}
{about_html}
</main>
<footer>
価格・割引率は取得時点のものです。購入前にAmazonの商品ページで最新の価格をご確認ください。
Amazonのアソシエイトとして、当サイトは適格販売により収入を得ています。
当サイトはアクセス解析のためGoogle Analyticsを利用しています(データは匿名で収集され、Googleに送信されます)。
{policy_link}｜ <a href="rss.xml" data-google-vignette="false" style="color:inherit">RSS</a>
{related_html}
</footer>
</body>
</html>
"""


def scale_text(total) -> str:
    """企画の規模を表す文言を作る。

    AmazonのtotalResultCountは1000で頭打ちになるため、そのまま「約1,000冊」
    と書くと、企画名に「対象作品2500点以上」とあるものと矛盾する。
    上限に張り付いた場合は「以上」にして実数と誤解されないようにする。
    """
    if not total:
        return ""
    if total >= 1000:
        return "対象1,000冊以上"
    return f"対象約{total:,}冊"


def generate_rss(data: dict) -> str:
    """在庫一覧ではなく「新しく始まったセール企画」のフィードにする。

    対象本をそのまま並べると、平時は何日も更新が無く、企画が入れ替わった
    回だけ百件以上がまとめて届く。guidをASINだけにしていたため、
    一度終わった本が後日また値引きされても購読者には届かなかった。
    企画単位なら「何が始まったか」が1記事で伝わり、guidに開始日を含めれば
    同じ企画が再開催されたときも新しい記事として届く。
    """
    site_url = CONFIG.get("site_url", "")
    now_dt = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
    now = now_dt.astimezone(datetime.timezone.utc).strftime(
        "%a, %d %b %Y %H:%M:%S +0000"
    )
    # 企画は数日に1本しか始まらないので、窓を広めに取ってもフィードは
    # 短いままになる。guidに開始日が入っているため再配信もされない
    window = CONFIG.get("rss_campaign_days", 7)
    items_xml = []
    rows = []
    for c in data.get("campaigns") or []:
        at = c.get("since_at")
        if not at:
            continue
        try:
            started = datetime.datetime.fromisoformat(at)
        except ValueError:
            continue
        if (now_dt - started).days > window:
            continue
        rows.append((started, c))
    rows.sort(key=lambda r: r[0], reverse=True)
    for started, c in rows:
        scale = scale_text(c.get("total"))
        title = c["name"] + (f"（{scale}）" if scale else "")
        # 企画名だけでは中身が想像できないため、目立つ数冊を添える
        picks = "".join(
            f"<li>{esc(b['title'])}"
            + (f"（{b['percent_off']}%OFF）" if b.get("percent_off") else "")
            + "</li>"
            for b in (c.get("items") or [])[:5]
        )
        desc = f"<ul>{picks}</ul>" if picks else ""
        items_xml.append(
            f"""<item>
<title>{esc(title)}</title>
<link>{esc(c["url"])}</link>
<guid isPermaLink="false">{esc(c["node_id"] + "-" + (c.get("since") or ""))}</guid>
<description>{esc(desc)}</description>
<pubDate>{started.strftime("%a, %d %b %Y %H:%M:%S %z")}</pubDate>
</item>"""
        )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
<title>{esc(CONFIG["site_title"])}</title>
<link>{esc(site_url)}</link>
<description>{esc(CONFIG["site_description"])}</description>
<lastBuildDate>{now}</lastBuildDate>
{chr(10).join(items_xml)}
</channel>
</rss>
"""


# --- 出版社別・型別の個別ページ ---
#
# トップページは1枚しかなく、検索では「電子書籍 セール」のような汎用
# クエリしか拾えていない。毎日集めているセールデータを捨てずに貯め、
# 繰り返し開催される単位(出版社と、週末セール等のセールの型)ごとに
# 固定URLのページを作り、開催中＋開催履歴を持たせる。
#
# 開催履歴の元データは2つ:
#   - data/campaign_state.json: CIがコミットする唯一の状態ファイル。
#     fetch_sales.py が終了した企画も落とさず保持し続けるため、
#     ここが現在進行形のアーカイブになる
#   - data/campaign_history.json: 状態ファイルが企画を剪定していた時代の
#     開催分を復元した種データ(静的な補完分。以後は更新しない)
# 期間はAmazon公式の開催期間ではなく、当サイトで掲載を確認した期間
# (初検出日〜最終検出日)。ページ上にもその旨を明記する

HISTORY_PATH = ROOT / "data" / "campaign_history.json"
CAMPAIGN_STATE_PATH = ROOT / "data" / "campaign_state.json"

# 出版社のキュレーション済みマッピング。(slug, 表示名, パターン)。
# 企画名にパターンを含む最初の出版社を、その企画の出版社とする
# (「7社合同フェア」のように出版社名を含まない企画は属さない)。
# 開催実績がまだ無い出版社も将来の開催に備えて載せてある
# (実績が無ければページ自体が生成されない)
PUBLISHERS = [
    ("kadokawa", "KADOKAWA", [r"KADOKAWA", r"カドカワ", r"カドサマー"]),
    ("kodansha", "講談社", [r"講談社"]),
    ("shogakukan", "小学館", [r"小学館"]),
    ("shueisha", "集英社", [r"集英社"]),
    ("hakusensha", "白泉社", [r"白泉社"]),
    ("akitashoten", "秋田書店", [r"秋田書店"]),
    ("square-enix", "スクウェア・エニックス", [r"スクウェア・エニックス", r"スクエニ"]),
    ("shoeisha", "翔泳社", [r"翔泳社"]),
    ("mag-garden", "マッグガーデン", [r"マッグガーデン"]),
    ("coamix", "コアミックス", [r"コアミックス"]),
    ("number-nine", "ナンバーナイン", [r"ナンバーナイン"]),
    ("shufunotomo", "主婦の友社", [r"主婦の友"]),
    ("bungeishunju", "文藝春秋", [r"文藝春秋"]),
    ("kobunsha", "光文社", [r"光文社"]),
    ("gentosha", "幻冬舎", [r"幻冬舎"]),
    ("yamatokeikoku", "山と溪谷社", [r"山と溪谷社"]),
    ("gijutsuhyoron", "技術評論社", [r"技術評論社"]),
    ("fusosha", "扶桑社", [r"扶桑社"]),
    ("starts", "スターツ出版", [r"スターツ出版"]),
]

# セールの型。(slug, 表示名, パターン)。型は切り口が重なってよいため、
# 1つの企画が複数の型に同時に属せる
FORMATS = [
    ("weekend", "週末セール", [r"週末"]),
    ("uniform", "均一セール", [r"均一", r"[0-9０-９]+円セール", r"[0-9０-９]+円キャンペーン"]),
    ("points", "ポイント還元フェア", [r"ポイント還元"]),
    ("seasonal", "季節ビッグセール", [r"ビッグセール", r"[春夏秋冬]の特別セール"]),
]

_PUBLISHER_RES = [
    (slug, disp, [re.compile(p) for p in pats]) for slug, disp, pats in PUBLISHERS
]
_FORMAT_RES = [
    (slug, disp, [re.compile(p) for p in pats]) for slug, disp, pats in FORMATS
]
PUBLISHER_NAMES = {slug: disp for slug, disp, _ in PUBLISHERS}
FORMAT_NAMES = {slug: disp for slug, disp, _ in FORMATS}

# 個別ページ専用の追加スタイル(トップページの見た目には影響しない)
PAGE_CSS = CSS + """
.crumb { font-size: 12px; color: var(--muted); margin: 4px 0 10px; }
.crumb a { color: var(--accent); text-decoration: none; }
/* 個別ページではサイト名を見出し要素にしないだけで、見た目はトップと
   同じ大きさに揃える。ページの主題を h1 にする
   (SEOのための見出し階層。オーナー指示 2026-11-14) */
header .brand { font-size: 24px; font-weight: 700; }
header .brand a { color: var(--text); text-decoration: none;
  display: inline-flex; align-items: center; gap: 8px; }
header .brand img { width: 44px; height: 44px; }
main > h1 { font-size: 20px; margin: 2px 0 0; padding-left: 10px;
  border-left: 4px solid var(--accent); }
.lead { font-size: 14px; margin: 8px 0 4px; }
.hist { list-style: none; margin-top: 10px; }
.hist li { padding: 7px 0; border-bottom: 1px solid var(--line);
  font-size: 14px; }
.hist .hdate { color: var(--muted); font-size: 12px; margin-right: 10px;
  white-space: nowrap; }
.hist .now { color: #fff; background: var(--badge-hi); font-size: 11px;
  font-weight: 700; border-radius: 4px; padding: 1px 6px; margin-left: 6px;
  vertical-align: 1px; }
.note { color: var(--muted); font-size: 12px; margin-top: 12px; }
"""


def publisher_of(name: str):
    """企画名から出版社を判定する。(slug, 表示名) か None"""
    name = name or ""
    for slug, disp, res in _PUBLISHER_RES:
        if any(r.search(name) for r in res):
            return slug, disp
    return None


def formats_of(name: str) -> list:
    """企画名からセールの型を判定する。[(slug, 表示名), ...](該当する型すべて)"""
    name = name or ""
    return [
        (slug, disp)
        for slug, disp, res in _FORMAT_RES
        if any(r.search(name) for r in res)
    ]


def _archive_row(name, first_seen, last_seen, node_id=None, total=None):
    """開催履歴の1行に正規化する。開始日が解釈できなければ None"""
    name = (name or "").strip()
    first = parse_since_date(first_seen)
    if not name or first is None:
        return None
    last = parse_since_date(last_seen) or first
    if last < first:
        last = first
    return {
        "name": name,
        "first_seen": first.isoformat(),
        "last_seen": last.isoformat(),
        "node_id": str(node_id) if node_id else None,
        "total": total if isinstance(total, int) and total > 0 else None,
    }


def merge_archive_rows(seed_rows, state) -> list:
    """履歴の種データと現在の状態を、開催履歴のリストにまとめる。

    キーは (企画名, 開始日)。状態側は node_id を持ち last_seen も新しい
    ため、重なる行は状態側を優先する(種データの対象冊数だけ引き継ぐ)。
    並びは開始日の新しい順
    """
    merged: dict = {}
    for r in seed_rows or []:
        if not isinstance(r, dict):
            continue
        row = _archive_row(
            r.get("name"),
            r.get("first_seen"),
            r.get("last_seen"),
            r.get("node_id"),
            r.get("total"),
        )
        if row:
            merged[(row["name"], row["first_seen"])] = row
    for node_id, e in (state or {}).items():
        if not isinstance(e, dict):
            continue
        row = _archive_row(e.get("name"), e.get("first_seen"), e.get("last_seen"), node_id)
        if not row:
            continue
        key = (row["name"], row["first_seen"])
        prev = merged.get(key)
        if prev and prev.get("total") and not row.get("total"):
            row["total"] = prev["total"]
        merged[key] = row
    return sorted(
        merged.values(), key=lambda r: (r["first_seen"], r["name"]), reverse=True
    )


def load_campaign_archive() -> list:
    """data/campaign_history.json(種データ)と data/campaign_state.json
    (現在の状態)を合わせた開催履歴を返す。ファイルが無い・壊れている
    場合は読めた分だけで組み立てる(個別ページは追加の生成物なので、
    トップページの生成まで巻き込んで落とさない)"""
    try:
        seed = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        seed = []
    if not isinstance(seed, list):
        seed = []
    try:
        state = json.loads(CAMPAIGN_STATE_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        state = {}
    if not isinstance(state, dict):
        state = {}
    return merge_archive_rows(seed, state)


def build_identity_index(data: dict, archive: list) -> dict:
    """出版社・型ごとに {"current": [...], "history": [...]} を作る。

    current は sales.json の開催中企画(商品つきのdictそのもの)。
    history はアーカイブの行で、開催中の企画の行も含む(is_current で区別)
    """
    index: dict = {}

    def bucket(kind, slug):
        return index.setdefault((kind, slug), {"current": [], "history": []})

    campaigns = data.get("campaigns") or []
    current_nodes = {c.get("node_id") for c in campaigns}
    totals = {
        c.get("node_id"): c.get("total")
        for c in campaigns
        if c.get("node_id") and c.get("total")
    }
    for row in archive:
        row = dict(row)
        if not row.get("total") and row.get("node_id") in totals:
            row["total"] = totals[row["node_id"]]
        row["is_current"] = row.get("node_id") in current_nodes
        pub = publisher_of(row["name"])
        if pub:
            bucket("publisher", pub[0])["history"].append(row)
        for slug, _disp in formats_of(row["name"]):
            bucket("format", slug)["history"].append(row)
    for c in campaigns:
        pub = publisher_of(c.get("name") or "")
        if pub:
            bucket("publisher", pub[0])["current"].append(c)
        for slug, _disp in formats_of(c.get("name") or ""):
            bucket("format", slug)["current"].append(c)
    return index


def period_text(row) -> str:
    """開催履歴の期間表記。開催中なら終了日を出さない"""
    first = datetime.date.fromisoformat(row["first_seen"])
    if row.get("is_current"):
        return f"{first.year}/{first.month}/{first.day}〜開催中"
    last = datetime.date.fromisoformat(row["last_seen"])
    if first == last:
        return f"{first.year}/{first.month}/{first.day}"
    if first.year == last.year:
        return f"{first.year}/{first.month}/{first.day}〜{last.month}/{last.day}"
    return f"{first.year}/{first.month}/{first.day}〜{last.year}/{last.month}/{last.day}"


def render_identity_page(kind: str, slug: str, display: str, entry: dict, data: dict) -> str:
    """出版社別・型別の個別ページ1枚分のHTMLを作る。"""
    site_url = CONFIG.get("site_url", "")
    seg = "publishers" if kind == "publisher" else "formats"
    canonical = f"{site_url}{seg}/{slug}/"
    fetched = datetime.datetime.fromisoformat(data["fetched_at"]).astimezone(
        datetime.timezone(datetime.timedelta(hours=9))
    )
    updated = fetched.strftime("%Y年%m月%d日 %H:%M")
    if kind == "publisher":
        heading = f"{display}のKindle本セール・フェア"
        kind_label = "出版社・版元別"
    else:
        heading = f"Kindle本の{display}"
        kind_label = "セールの型別"
    page_title = f"{heading}｜{CONFIG['site_title']}"
    description = (
        f"{heading}の開催中情報と開催履歴をまとめています。"
        f"期間や対象冊数を{CONFIG['site_title']}が自動更新でお届けします。"
    )
    current = entry["current"]
    history = entry["history"]
    if kind == "publisher":
        lead = (
            f"{display}のKindle本セール・フェアの一覧です。"
            f"開催中の企画は{len(current)}件、これまでの開催履歴は{len(history)}件です。"
        )
    else:
        lead = (
            f"{display}に該当するKindle本セール企画の一覧です。"
            f"開催中の企画は{len(current)}件、これまでの開催履歴は{len(history)}件です。"
        )

    sections = [
        f'<p class="crumb"><a href="{esc(site_url)}" data-google-vignette="false">'
        f'{esc(CONFIG["site_title"])} トップ</a> ＞ {esc(kind_label)} ＞ {esc(display)}</p>',
        f"<h1>{esc(heading)}</h1>",
        f'<p class="lead">{esc(lead)}</p>',
    ]
    if current:
        for c in current:
            books = "\n".join(render_book(b) for b in (c.get("items") or [])[:6])
            scale = scale_text(c.get("total"))
            meta = f'<span class="hmeta"> 【{esc(scale)}】</span>' if scale else ""
            sections.append(
                f"<details open>\n"
                f"<summary><h2>🔥 {esc(c['name'])}{meta}</h2></summary>\n"
                f'<a class="cmeta-link" href="{esc(c["url"])}" '
                f'data-google-vignette="false" target="_blank" rel="noopener sponsored">'
                f"🛒 このセールの対象本をAmazonですべて見る</a>\n"
                f'<div class="grid">\n{books}\n</div>\n'
                f"</details>"
            )
    else:
        sections.append(
            f'<p class="empty">現在開催中の{esc(display)}の企画はありません。'
            f"過去の開催は下の履歴をご覧ください。</p>"
        )
    rows = []
    for row in history:
        scale = scale_text(row.get("total"))
        meta = f' <span class="hmeta">{esc(scale)}</span>' if scale else ""
        now = '<span class="now">開催中</span>' if row.get("is_current") else ""
        rows.append(
            f'<li><span class="hdate">{esc(period_text(row))}</span>'
            f"{esc(row['name'])}{meta}{now}</li>"
        )
    sections.append(
        f'<p class="group">開催履歴 ({len(history)}件)</p>\n'
        f'<ul class="hist">\n{chr(10).join(rows)}\n</ul>\n'
        f'<p class="note">期間は当サイトで掲載を確認した期間(初検出日〜最終検出日)です。'
        f"Amazon公式の開催期間とは異なる場合があります。</p>"
    )

    gsv = CONFIG.get("google_site_verification", "")
    gsv_tag = (
        f'<meta name="google-site-verification" content="{esc(gsv)}">' if gsv else ""
    )
    json_ld = json.dumps(
        {
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": 1,
                    "name": CONFIG["site_title"],
                    "item": site_url,
                },
                {"@type": "ListItem", "position": 2, "name": kind_label},
                {
                    "@type": "ListItem",
                    "position": 3,
                    "name": display,
                    "item": canonical,
                },
            ],
        },
        ensure_ascii=False,
    ).replace("</", "<\\/")
    header_ad = render_ad_slot()

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(page_title)}</title>
<meta name="description" content="{esc(description)}">
<link rel="canonical" href="{esc(canonical)}">
{gsv_tag}
{render_ga_tag()}
{render_adsense_tag()}
<link rel="icon" type="image/png" sizes="96x96" href="{esc(site_url)}assets/favicon.png">
<link rel="apple-touch-icon" href="{esc(site_url)}assets/apple-touch-icon.png">
<meta property="og:type" content="website">
<meta property="og:title" content="{esc(page_title)}">
<meta property="og:description" content="{esc(description)}">
<meta property="og:url" content="{esc(canonical)}">
<meta property="og:site_name" content="{esc(CONFIG["site_title"])}">
<meta property="og:locale" content="ja_JP">
<meta property="og:image" content="{esc(site_url)}assets/ogp.jpg">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<link rel="alternate" type="application/rss+xml" title="RSS" href="{esc(site_url)}rss.xml">
<script type="application/ld+json">{json_ld}</script>
<style>{PAGE_CSS}</style>
</head>
<body>
<header>
<p class="brand"><a href="{esc(site_url)}" data-google-vignette="false"><img src="{esc(site_url)}assets/logo.png" alt="" width="44" height="44">{esc(CONFIG["site_title"])}</a></p>
<p>{esc(CONFIG["site_description"])} ｜ 割引率とポイント還元率の合計が{data["min_saving_percent"]}%以上の本を掲載 ｜ 最終更新: {updated}</p>
</header>
{header_ad}
<main>
{chr(10).join(sections)}
</main>
<footer>
価格・割引率は取得時点のものです。購入前にAmazonの商品ページで最新の価格をご確認ください。
Amazonのアソシエイトとして、当サイトは適格販売により収入を得ています。
当サイトはアクセス解析のためGoogle Analyticsを利用しています(データは匿名で収集され、Googleに送信されます)。
{render_policy_link()}｜ <a href="{esc(site_url)}rss.xml" data-google-vignette="false" style="color:inherit">RSS</a>
{render_related_html()}
</footer>
</body>
</html>
"""


def generate_identity_pages(data: dict, index: dict) -> dict:
    """個別ページの {相対パス: HTML} を返す。
    開催履歴も開催中も無い単位のページは作らない"""
    pages = {}
    for (kind, slug), entry in index.items():
        if not entry["history"] and not entry["current"]:
            continue
        display = (PUBLISHER_NAMES if kind == "publisher" else FORMAT_NAMES)[slug]
        seg = "publishers" if kind == "publisher" else "formats"
        pages[f"{seg}/{slug}/index.html"] = render_identity_page(
            kind, slug, display, entry, data
        )
    return pages


def identity_nav_html(index: dict) -> str:
    """トップページに差し込む、個別ページへのチップ状ナビ。
    ページが生成される単位だけを定義順に並べる"""

    def chips(kind, names, seg, label):
        present = [(slug, disp) for slug, disp in names if (kind, slug) in index]
        if not present:
            return ""
        links = "\n".join(
            f'<a href="{seg}/{slug}/" data-google-vignette="false">{esc(disp)}</a>'
            for slug, disp in present
        )
        return f'<div class="sites"><span class="lbl">{label}</span>\n{links}\n</div>'

    parts = [
        chips(
            "publisher",
            [(s, d) for s, d, _ in PUBLISHERS],
            "publishers",
            "出版社・版元から探す",
        ),
        chips("format", [(s, d) for s, d, _ in FORMATS], "formats", "セールの型から探す"),
    ]
    return "\n".join(p for p in parts if p)


def generate_sitemap(data: dict, extra_urls=None) -> str:
    site_url = CONFIG.get("site_url", "")
    lastmod = data["fetched_at"][:10]
    extras = "".join(
        f"<url>\n<loc>{esc(u)}</loc>\n<lastmod>{lastmod}</lastmod>\n"
        f"<changefreq>daily</changefreq>\n</url>\n"
        for u in extra_urls or []
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url>
<loc>{esc(site_url)}</loc>
<lastmod>{lastmod}</lastmod>
<changefreq>hourly</changefreq>
</url>
{extras}</urlset>
"""


WIDGET_JS = r"""(function () {
  "use strict";

  var FALLBACK_SITE_URL = "__FALLBACK_SITE_URL__";

  // currentScriptはスクリプト評価中しか参照できない。init()はDOMContentLoaded
  // 後に走ることがあるため、ここで(評価時に)一度だけ取得しておく
  var SCRIPT_SRC = document.currentScript && document.currentScript.src;

  function baseUrlFromScript() {
    if (!SCRIPT_SRC) return null;
    return SCRIPT_SRC.replace(/widget\.js.*$/, "");
  }

  function fmtYen(n) {
    return "¥" + Math.round(n).toLocaleString("ja-JP");
  }

  function el(tag, opts) {
    opts = opts || {};
    var e = document.createElement(tag);
    if (opts.className) e.className = opts.className;
    if (opts.text !== undefined) e.textContent = opts.text;
    if (opts.attrs) {
      for (var k in opts.attrs) {
        if (Object.prototype.hasOwnProperty.call(opts.attrs, k)) {
          e.setAttribute(k, opts.attrs[k]);
        }
      }
    }
    return e;
  }

  function injectStyle() {
    if (document.getElementById("dpy-widget-style")) return;
    var style = document.createElement("style");
    style.id = "dpy-widget-style";
    style.textContent = [
      "#densho-widget{font-size:14px;line-height:1.5;font-family:-apple-system,BlinkMacSystemFont,\"Hiragino Sans\",\"Noto Sans JP\",sans-serif;}",
      ".dpy-box{border:1px solid #e5e2dc;border-radius:10px;overflow:hidden;background:#ffffff;color:#1a1a1a;}",
      ".dpy-head{display:flex;align-items:baseline;gap:8px;padding:8px 14px;font-size:14px;font-weight:700;background:#faf6ef;color:#1a1a1a;text-decoration:none;border-bottom:1px solid #e5e2dc;}",
      ".dpy-more{font-size:11px;font-weight:600;color:#e47911;white-space:nowrap;flex-shrink:0;margin-left:auto;}",
      ".dpy-head:hover{color:#e47911;}",
      ".dpy-list{display:flex;flex-direction:column;}",
      ".dpy-row{display:flex;gap:10px;padding:8px 14px;text-decoration:none;color:#1a1a1a;border-bottom:1px solid #f0ede7;}",
      ".dpy-row:last-child{border-bottom:none;}",
      ".dpy-row:hover{background:#faf8f4;}",
      ".dpy-img{width:46px;height:66px;object-fit:cover;border-radius:4px;flex-shrink:0;background:#e5e2dc;}",
      ".dpy-ph{width:46px;height:66px;border-radius:4px;flex-shrink:0;background:#e5e2dc;}",
      ".dpy-info{min-width:0;flex:1;}",
      ".dpy-title{font-size:13px;font-weight:600;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;}",
      ".dpy-price{margin-top:2px;font-size:13px;}",
      ".dpy-now{font-weight:700;color:#d0342c;}",
      ".dpy-was{font-size:11px;color:#6b6b6b;text-decoration:line-through;margin-left:5px;}",
      ".dpy-off{display:inline-block;font-size:10px;font-weight:700;color:#fff;background:#e47911;border-radius:4px;padding:1px 5px;margin-left:5px;vertical-align:1px;}",
      ".dpy-off.dpy-hi{background:#d0342c;}",
      ".dpy-pt{font-size:10px;color:#0a7d3c;font-weight:600;margin-top:1px;}",
      '@media (prefers-color-scheme: dark) {',
      ".dpy-box{border-color:#2c2e36;background:#1e2027;color:#e8e8e6;}",
      ".dpy-head{background:#20222a;color:#e8e8e6;border-bottom-color:#2c2e36;}",
      ".dpy-row{color:#e8e8e6;border-bottom-color:#282a31;}",
      ".dpy-row:hover{background:#22242c;}",
      ".dpy-img,.dpy-ph{background:#2c2e36;}",
      ".dpy-was{color:#9a9a96;}",
      ".dpy-pt{color:#4fd689;}",
      "}",
    ].join("\n");
    document.head.appendChild(style);
  }

  function renderBookRow(book) {
    var row = el("a", {
      className: "dpy-row no-icon",
      attrs: {
        href: book.url || "#",
        target: "_blank",
        rel: "noopener sponsored",
      },
    });

    if (book.image) {
      var img = el("img", { className: "dpy-img", attrs: { src: book.image, alt: "", loading: "lazy" } });
      row.appendChild(img);
    } else {
      row.appendChild(el("span", { className: "dpy-ph" }));
    }

    var info = el("div", { className: "dpy-info" });
    info.appendChild(el("div", { className: "dpy-title", text: book.title || "" }));

    var price = el("div", { className: "dpy-price" });
    price.appendChild(el("span", { className: "dpy-now", text: fmtYen(book.price) }));
    if (book.list_price) {
      price.appendChild(el("span", { className: "dpy-was", text: fmtYen(book.list_price) }));
    }
    if (book.percent_off) {
      var offCls = "dpy-off" + (book.percent_off >= 50 ? " dpy-hi" : "");
      price.appendChild(el("span", { className: offCls, text: book.percent_off + "%OFF" }));
    }
    info.appendChild(price);

    if (book.points) {
      var pct = book.points_percent ? book.points_percent + "%還元" : "還元";
      info.appendChild(el("div", { className: "dpy-pt", text: "+" + book.points + "pt (" + pct + ")" }));
    }

    row.appendChild(info);
    return row;
  }

  function sampleRandom(arr, n) {
    var copy = arr.slice();
    for (var i = copy.length - 1; i > 0; i--) {
      var j = Math.floor(Math.random() * (i + 1));
      var tmp = copy[i]; copy[i] = copy[j]; copy[j] = tmp;
    }
    return copy.slice(0, n);
  }

  function render(container, data) {
    var siteUrl = data.site_url || FALLBACK_SITE_URL;
    var count = parseInt(container.getAttribute("data-count"), 10);
    if (!count || count < 1 || count > 5) count = 3;
    var books = sampleRandom(data.books || [], count);
    if (books.length === 0) return;

    injectStyle();

    var box = el("div", { className: "dpy-box" });

    // 見出しと末尾ボタンはリンク先が同じで導線が重複していた。
    // 見出しに寄せて1つにまとめ、40px分の縦幅を削る。
    // ただし見出しだけではリンクと分からないため、右端に誘導文言を添える
    var campaignCount = data.campaign_count || 0;
    var head = el("a", {
      className: "dpy-head no-icon",
      attrs: { href: siteUrl, target: "_blank", rel: "noopener" },
    });
    head.appendChild(el("span", { text: "📚 本日のKindleセール" }));
    head.appendChild(
      el("span", {
        className: "dpy-more",
        text: campaignCount
          ? "セール" + campaignCount + "件を見る →"
          : "すべて見る →",
      })
    );
    box.appendChild(head);

    var list = el("div", { className: "dpy-list" });
    for (var i = 0; i < books.length; i++) {
      list.appendChild(renderBookRow(books[i]));
    }
    box.appendChild(list);

    container.textContent = "";
    container.appendChild(box);
  }

  function init() {
    var container = document.getElementById("densho-widget");
    if (!container) return;

    var base = baseUrlFromScript() || FALLBACK_SITE_URL;
    var url = base + "widget.json";

    fetch(url, { cache: "no-store" })
      .then(function (res) {
        if (!res.ok) throw new Error("bad response");
        return res.json();
      })
      .then(function (data) {
        render(container, data);
      })
      .catch(function () {
        /* fetch失敗時は何もしない(既存のnoscriptリンクを残す) */
      });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
"""


def compact_title(title: str) -> str:
    """ウィジェット用にタイトルを短くする。

    ライトノベル系は「作品名～長い副題～1巻 (レーベル名)」という形式が多く、
    そのままだと2行に折り返してウィジェットが縦に伸びる。実データ264冊のうち
    223冊が該当した。リンク先のAmazonページには完全なタイトルがあるので、
    ここでは1行に収まることを優先する。
    """
    s = re.sub(r"[～~][^～~]{8,}[～~]", "", title)
    s = re.sub(r"[（(][^（()）]{2,30}[)）]\s*$", "", s)
    s = re.sub(r"[\s　]+", " ", s).strip()
    # 副題を落とすと「作品名 1 作品名」のように同じ語が残ることがある
    m = re.match(r"^(.{4,}?)\s", s)
    if m:
        head = m.group(1)
        idx = s.find(head, len(head))
        if idx > 0:
            s = s[:idx].strip()
    return s or title


def widget_book(b: dict) -> dict:
    return {
        "title": compact_title(b.get("title") or ""),
        "price": b.get("price"),
        "list_price": b.get("list_price"),
        "percent_off": b.get("percent_off"),
        "points": b.get("points"),
        "points_percent": b.get("points_percent"),
        "image": b.get("image"),
        "url": b.get("url"),
    }


# これ未満の価格は、取得ミスや無料同然の異常値とみなして除外する
MANGA_MIN_PRICE = 30


def generate_manga_books(data: dict) -> list[dict]:
    """マンガだけのセール本リスト(漫画ポチが読む)。

    元データはfetch_sales.pyが仕分けた data["manga_items"]。マンガと判定できない
    本は最初から入っていない。古いsales.json(キー無し)では空リストになる。
    割引率が確認できない本(定価なし・割引率なし)と異常に安い本は除く
    """
    items = [
        b
        for b in data.get("manga_items") or []
        if (b.get("price") or 0) >= MANGA_MIN_PRICE
        and b.get("list_price")
        and b.get("percent_off")
    ]
    items.sort(
        key=lambda b: (b.get("percent_off") or 0, b.get("points_percent") or 0),
        reverse=True,
    )
    pool_size = CONFIG.get("widget_manga_pool_size", 10)
    return [widget_book(b) for b in items[:pool_size]]


# 企画名の先頭にある「【対象作品950点以上】」のような【…】の接頭辞
CAMPAIGN_PREFIX_RE = re.compile(r"^【[^】]*】")


def campaign_display_name(name: str) -> str:
    """表示用の企画名。先頭の【…】を削る(削ると空になるなら元の名前)"""
    name = (name or "").strip()
    stripped = CAMPAIGN_PREFIX_RE.sub("", name).strip()
    return stripped or name


def parse_since_date(since: str | None) -> datetime.date | None:
    """since(日時でも日付のみでも可)の日付部分を返す。解釈できなければ None。
    タイムゾーンは考慮せず、日付単位で扱う"""
    if not since or not isinstance(since, str):
        return None
    try:
        return datetime.date.fromisoformat(since.strip()[:10])
    except ValueError:
        return None


def usable_percent_off(b: dict) -> float | None:
    """割引率が確認できる本ならその割引率、除外対象なら None。

    manga_books と同じ除外条件: price が MANGA_MIN_PRICE 未満の異常値
    (¥11 で 99%OFF など)、定価(list_price)なし、割引率が数値でない/0以下は除く。
    campaign_max_percent_off と campaign_sample_titles が同じ判定を共有する
    """
    pct = b.get("percent_off")
    if (
        isinstance(pct, bool)
        or not isinstance(pct, (int, float))
        or (b.get("price") or 0) < MANGA_MIN_PRICE
        or not b.get("list_price")
        or pct <= 0
    ):
        return None
    return pct


def campaign_max_percent_off(items: list[dict]) -> int | None:
    """企画の items のうち最大の割引率(整数)。該当が無ければ None。

    根拠: sales.json の campaigns[].items は企画の全商品ではなく、
    割引率+ポイント還元率の降順で上位 items_per_campaign 件に切った一部。
    なので「最大」は保存されている範囲での実測値(企画全体の真の最大ではない)。
    除外条件は usable_percent_off を参照
    """
    best = None
    for b in items or []:
        pct = usable_percent_off(b)
        if pct is None:
            continue
        if best is None or pct > best:
            best = pct
    return None if best is None else int(round(best))


# 先頭/末尾の【合本版】【電子特典付き】［カラー版］のような括り
BRACKET_EDGE_RE = re.compile(r"^【[^】]*】|【[^】]*】$|^［[^］]*］|［[^］]*］$")
# 末尾の括弧書き(レーベル名・「（１）」のような巻数)。全角/半角どちらも
TRAILING_PAREN_RE = re.compile(r"[（(][^（）()]*[）)]$")
# 末尾の巻数表記: 「全17巻」「第3巻」「 3巻」「全巻」、区切り空白つきの数字だけ(「 3」「　３」)
# 「C3」のように空白なしでタイトルに溶けている数字は巻数とみなさず残す
TRAILING_VOLUME_RES = (
    re.compile(r"[\s　]*全[0-9０-９]*巻$"),
    re.compile(r"[\s　]*第?[0-9０-９]+巻$"),
    re.compile(r"[\s　]+[0-9０-９]+$"),
)
# 2行目に添える作品名の最大文字数(「…」を含む)
SERIES_TITLE_MAX_LEN = 18


def series_title(title: str) -> str:
    """本のタイトルを作品名(シリーズ名)に整える。

    レーベル名の括弧書き、【合本版】などの【…】、巻数表記を落とし、
    SERIES_TITLE_MAX_LEN 文字を超えたら末尾を「…」にする。
    落とした結果が空になるなら元のタイトル(前後の空白だけ除いたもの)を使う
    """
    original = (title or "").strip()
    cur = original
    # 全角スペースの後ろは副題(「ナナとカオル　Black Label」)なので落とす。
    # 頭が1文字以下になるなら切らない
    head, sep, _ = cur.partition("　")
    if sep and len(head.strip()) >= 2:
        cur = head.strip()
    while True:
        prev = cur
        cur = BRACKET_EDGE_RE.sub("", cur).strip()
        cur = TRAILING_PAREN_RE.sub("", cur).strip()
        for rx in TRAILING_VOLUME_RES:
            cur = rx.sub("", cur).strip()
        if cur == prev:
            break
    result = cur or original
    if len(result) > SERIES_TITLE_MAX_LEN:
        result = result[: SERIES_TITLE_MAX_LEN - 1] + "…"
    return result


def campaign_sample_titles(items: list[dict], limit: int = 2) -> list[str]:
    """企画の代表作品名(漫画ポチが企画名の下に小さく添える)。0〜limit件。

    割引率の高い順(同率は元の並びのまま)に series_title して、同じ作品の
    別巻は1つにまとめる。除外条件は usable_percent_off(割引率が確認できない本は
    候補にしない。候補が無ければ空リスト)。titleが空・文字列でない本は無視する
    """
    if limit <= 0:
        return []
    ranked = []
    for b in items or []:
        pct = usable_percent_off(b)
        title = b.get("title")
        if pct is None or not isinstance(title, str) or not title.strip():
            continue
        ranked.append((pct, title))
    ranked.sort(key=lambda r: r[0], reverse=True)  # 安定ソートなので同率は元の順
    result: list[str] = []
    for _, title in ranked:
        name = series_title(title)
        if name in result:
            continue
        result.append(name)
        if len(result) >= limit:
            break
    return result


def generate_sale_campaigns(data: dict, today: datetime.date | None = None) -> list[dict]:
    """セール企画の一覧(漫画ポチがお知らせ欄に企画名＋企画ページへのリンクを出す)。

    マンガ企画が先、その中は掲載開始の新しい順。続けてマンガ以外の企画。
    企画名が同じ(接頭辞を除いて同じ)ものは新しい方だけ残す。
    古いsales.json(キー無し)では空リストになる。Amazon APIは呼ばない

    企画が開催中かはAPIから判定できないので、初検出(since)が
    widget_campaign_max_age_days(既定30)日より古い企画と、sinceが無い/
    解釈できない企画は出さない(古さが分からないものは出さない)。
    today は日付での比較用(テストで固定する。省略時は実際の今日)
    """
    today = today or datetime.date.today()
    max_age = CONFIG.get("widget_campaign_max_age_days", 30)
    found: dict[str, dict] = {}
    for c in data.get("campaigns") or []:
        url = c.get("url") or ""
        name = campaign_display_name(c.get("name") or "")
        total = c.get("total") or 0
        if (
            not url.startswith("https://www.amazon.co.jp/")
            or not name
            or total <= 0
            or not c.get("items")
        ):
            continue
        since = c.get("since_at") or c.get("since") or ""
        since_date = parse_since_date(since)
        if since_date is None or (today - since_date).days > max_age:
            continue
        prev = found.get(name)
        if prev is not None and (prev["since"] or "") >= since:
            continue
        found[name] = {
            "name": name,
            "url": url,
            "total": total,
            "since": since or None,
            "is_manga": is_manga_campaign_name(c.get("name") or ""),
            "max_percent_off": campaign_max_percent_off(c.get("items")),
            "sample_titles": campaign_sample_titles(c.get("items")),
        }
    # since の新しい順(無ければ最後)→ マンガ企画を先頭へ。安定ソートを2回かける
    rows = sorted(found.values(), key=lambda r: r["since"] or "", reverse=True)
    dated = [r for r in rows if r["since"]] + [r for r in rows if not r["since"]]
    dated.sort(key=lambda r: not r["is_manga"])
    pool_size = CONFIG.get("widget_campaign_pool_size", 6)
    return dated[:pool_size]


def generate_widget_data(data: dict, today: datetime.date | None = None) -> dict:
    site_url = CONFIG.get("site_url", "")
    campaigns = data.get("campaigns") or []
    others = data.get("others") or []

    all_items = []
    for c in campaigns:
        all_items.extend(c.get("items") or [])
    all_items.extend(others)

    def savings(item: dict) -> int:
        return (item.get("percent_off") or 0) + (item.get("points_percent") or 0)

    seen: set[str] = set()
    deduped = []
    for item in all_items:
        asin = item.get("asin")
        if asin in seen:
            continue
        seen.add(asin)
        deduped.append(item)

    deduped.sort(key=savings, reverse=True)

    pool_size = CONFIG.get("widget_pool_size", 20)

    books = [widget_book(b) for b in deduped[:pool_size]]

    return {
        "updated": data.get("fetched_at"),
        "site_url": site_url,
        "site_title": CONFIG.get("site_title", ""),
        "campaign_count": len(campaigns),
        "books": books,
        "manga_books": generate_manga_books(data),
        "sale_campaigns": generate_sale_campaigns(data, today),
    }


def generate_widget_assets(data: dict) -> tuple[str, str]:
    widget_json = json.dumps(generate_widget_data(data), ensure_ascii=False, indent=2)
    site_url = CONFIG.get("site_url", "")
    widget_js = WIDGET_JS.replace("__FALLBACK_SITE_URL__", site_url)
    return widget_json, widget_js


def main():
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    site_url = CONFIG.get("site_url", "")
    # 出版社別・型別の個別ページ(開催履歴はアーカイブから組み立てる)
    archive = load_campaign_archive()
    index = build_identity_index(data, archive)
    identity_pages = generate_identity_pages(data, index)
    DOCS.mkdir(exist_ok=True)
    (DOCS / "index.html").write_text(
        generate_html(data, identity_nav_html(index)), encoding="utf-8"
    )
    (DOCS / "rss.xml").write_text(generate_rss(data), encoding="utf-8")
    page_urls = sorted(
        f"{site_url}{path[: -len('index.html')]}" for path in identity_pages
    )
    (DOCS / "sitemap.xml").write_text(
        generate_sitemap(data, page_urls), encoding="utf-8"
    )
    for rel, content in identity_pages.items():
        dest = DOCS / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
    (DOCS / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\nSitemap: {site_url}sitemap.xml\n",
        encoding="utf-8",
    )
    widget_json, widget_js = generate_widget_assets(data)
    (DOCS / "widget.json").write_text(widget_json, encoding="utf-8")
    (DOCS / "widget.js").write_text(widget_js, encoding="utf-8")
    total = len(data.get("others") or []) + sum(
        len(c["items"]) for c in data.get("campaigns") or []
    )
    print(
        f"generated: index.html, rss.xml, sitemap.xml, robots.txt, "
        f"widget.json, widget.js ({total}冊, 個別ページ{len(identity_pages)}件)"
    )


if __name__ == "__main__":
    main()
