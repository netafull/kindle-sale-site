#!/usr/bin/env python3
"""data/sales.json から docs/index.html と docs/rss.xml を生成する。"""

from __future__ import annotations

import datetime
import html
import json
import re
from pathlib import Path

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
header h1 img { width: 32px; height: 32px; }
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
   shrink-to-fitになり、中身がまだ無い広告は幅0に潰れて出ない */
.ad-slot { width: 100%; max-width: 960px; margin: 0 auto;
  background: var(--card); border: 1px solid var(--line);
  border-radius: 10px; padding: 12px; text-align: center; overflow: hidden; }
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
        f'<img src="{esc(item.get("image"))}" alt="" loading="lazy">'
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


def intersperse_ads(cards: list[str], every: int = 8) -> str:
    """カード一覧に広告枠を8件おきに挟み込む。"""
    ad = render_ad_slot()
    if not ad:
        return "\n".join(cards)
    out = []
    for i, c in enumerate(cards, 1):
        out.append(c)
        if i % every == 0:
            out.append(ad)
    return "\n".join(out)


def generate_html(data: dict) -> str:
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
        # グリッド末尾に「続きを見る」カードを置くぶん、本のカードを
        # 1つ減らして列数(最大3)の倍数を保ち、末尾行が欠けないようにする
        shown = c["items"][:-1] if len(c["items"]) % 3 == 0 else c["items"]
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

    related = CONFIG.get("related_sites") or []
    related_html = ""
    if related:
        links = "\n".join(
            f'<a href="{esc(s["url"])}" data-google-vignette="false">{esc(s["name"])}'
            + (f'<span class="lbl"> {esc(s["desc"])}</span>' if s.get("desc") else "")
            + "</a>"
            for s in related
        )
        related_html = (
            f'<div class="sites"><span class="lbl">関連サイト</span>\n{links}\n</div>'
        )
    # メディアポリシー(プライバシーポリシー・AdSenseのCookie告知を含む)は
    # netaful.jp/policy.html に既にある。3サイトとも netaful.jp 配下なので
    # 各サイトに複製せずリンクで参照する
    policy_url = CONFIG.get("policy_url", "")
    policy_link = (
        f'｜ <a href="{esc(policy_url)}" data-google-vignette="false" style="color:inherit">メディアポリシー</a>\n'
        if policy_url
        else ""
    )

    # AdSenseの広告コード。ads.txtはルートドメイン(netaful.jp)のものが
    # サブドメインにも適用されるため、各サイトでの設置は不要
    adsense_id = CONFIG.get("adsense_client_id", "")
    adsense_tag = (
        '<script async src="https://pagead2.googlesyndication.com/pagead/js/'
        f'adsbygoogle.js?client={esc(adsense_id)}" crossorigin="anonymous"></script>'
        if adsense_id
        else ""
    )
    header_ad = render_ad_slot()

    ga_id = CONFIG.get("ga_measurement_id", "")
    ga_tag = (
        f"""<script async src="https://www.googletagmanager.com/gtag/js?id={esc(ga_id)}"></script>
<script>
window.dataLayer = window.dataLayer || [];
function gtag(){{dataLayer.push(arguments);}}
gtag('js', new Date());
gtag('config', '{esc(ga_id)}');
</script>"""
        if ga_id
        else ""
    )

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
<meta name="description" content="{esc(CONFIG["site_description"])}">
<link rel="canonical" href="{esc(site_url)}">
{gsv_tag}
{ga_tag}
{adsense_tag}
<link rel="icon" type="image/png" href="assets/favicon.png">
<link rel="apple-touch-icon" href="assets/apple-touch-icon.png">
<meta property="og:type" content="website">
<meta property="og:title" content="{esc(page_title)}">
<meta property="og:description" content="{esc(CONFIG["site_description"])}">
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
<h1><a href="./" data-google-vignette="false"><img src="assets/logo.png" alt="" width="32" height="32">{esc(CONFIG["site_title"])}</a></h1>
<p>{esc(CONFIG["site_description"])} ｜ 割引率とポイント還元率の合計が{data["min_saving_percent"]}%以上の本を掲載 ｜ 最終更新: {updated}</p>
{related_html}
</header>
{header_ad}
<main>
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


def generate_sitemap(data: dict) -> str:
    site_url = CONFIG.get("site_url", "")
    lastmod = data["fetched_at"][:10]
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url>
<loc>{esc(site_url)}</loc>
<lastmod>{lastmod}</lastmod>
<changefreq>hourly</changefreq>
</url>
</urlset>
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


def generate_widget_data(data: dict) -> dict:
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

    books = [
        {
            "title": compact_title(b.get("title") or ""),
            "price": b.get("price"),
            "list_price": b.get("list_price"),
            "percent_off": b.get("percent_off"),
            "points": b.get("points"),
            "points_percent": b.get("points_percent"),
            "image": b.get("image"),
            "url": b.get("url"),
        }
        for b in deduped[:pool_size]
    ]

    return {
        "updated": data.get("fetched_at"),
        "site_url": site_url,
        "site_title": CONFIG.get("site_title", ""),
        "campaign_count": len(campaigns),
        "books": books,
    }


def generate_widget_assets(data: dict) -> tuple[str, str]:
    widget_json = json.dumps(generate_widget_data(data), ensure_ascii=False, indent=2)
    site_url = CONFIG.get("site_url", "")
    widget_js = WIDGET_JS.replace("__FALLBACK_SITE_URL__", site_url)
    return widget_json, widget_js


def main():
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    site_url = CONFIG.get("site_url", "")
    DOCS.mkdir(exist_ok=True)
    (DOCS / "index.html").write_text(generate_html(data), encoding="utf-8")
    (DOCS / "rss.xml").write_text(generate_rss(data), encoding="utf-8")
    (DOCS / "sitemap.xml").write_text(generate_sitemap(data), encoding="utf-8")
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
        f"widget.json, widget.js ({total}冊)"
    )


if __name__ == "__main__":
    main()
