#!/usr/bin/env python3
"""data/sales.json から docs/index.html と docs/rss.xml を生成する。"""

import datetime
import html
import json
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
header h1 a { color: var(--text); text-decoration: none; }
header p { color: var(--muted); font-size: 13px; margin-top: 4px; }
nav { max-width: 960px; margin: 12px auto 0; padding: 0 16px;
  display: flex; gap: 8px; flex-wrap: wrap; }
nav a { font-size: 13px; padding: 5px 12px; border: 1px solid var(--line);
  border-radius: 999px; color: var(--text); text-decoration: none;
  background: var(--card); }
nav a:hover { border-color: var(--accent); color: var(--accent); }
main { max-width: 960px; margin: 0 auto; padding: 8px 16px 48px; }
h2 { font-size: 18px; margin: 28px 0 12px; padding-left: 10px;
  border-left: 4px solid var(--accent); }
.grid { display: grid; gap: 10px;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); }
.book { display: flex; gap: 12px; background: var(--card);
  border: 1px solid var(--line); border-radius: 10px; padding: 12px;
  text-decoration: none; color: var(--text); }
.book:hover { border-color: var(--accent); }
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
footer { max-width: 960px; margin: 0 auto; padding: 16px;
  color: var(--muted); font-size: 12px; border-top: 1px solid var(--line); }
.empty { color: var(--muted); font-size: 14px; padding: 12px 0; }
"""


def esc(s):
    return html.escape(s or "", quote=True)


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
    return f"""<a class="book" href="{esc(item["url"])}" target="_blank" rel="noopener sponsored">
  {img_html}
  <div>
    <div class="t">{esc(item["title"])}</div>
    {author}
    <div class="price"><span class="now">&yen;{int(item["price"]):,}</span>{was_html}{off_html}</div>
    {points_html}
  </div>
</a>"""


def generate_html(data: dict) -> str:
    fetched = datetime.datetime.fromisoformat(data["fetched_at"]).astimezone(
        datetime.timezone(datetime.timedelta(hours=9))
    )
    updated = fetched.strftime("%Y年%m月%d日 %H:%M")

    nav = "\n".join(
        f'<a href="#g{i}">{esc(g["name"])}</a>'
        for i, g in enumerate(data["genres"])
    )
    sections = []
    for i, genre in enumerate(data["genres"]):
        books = "\n".join(render_book(b) for b in genre["items"])
        body = (
            f'<div class="grid">\n{books}\n</div>'
            if genre["items"]
            else '<p class="empty">現在このジャンルのセール情報はありません</p>'
        )
        sections.append(
            f'<h2 id="g{i}">{esc(genre["name"])} '
            f'({len(genre["items"])}冊)</h2>\n{body}'
        )

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(CONFIG["site_title"])}</title>
<meta name="description" content="{esc(CONFIG["site_description"])}">
<link rel="alternate" type="application/rss+xml" title="RSS" href="rss.xml">
<style>{CSS}</style>
</head>
<body>
<header>
<h1><a href="./">{esc(CONFIG["site_title"])}</a></h1>
<p>{esc(CONFIG["site_description"])} ｜ {data["min_saving_percent"]}%OFF以上 ｜ 最終更新: {updated}</p>
</header>
<nav>{nav}</nav>
<main>
{chr(10).join(sections)}
</main>
<footer>
価格・割引率は取得時点のものです。購入前にAmazonの商品ページで最新の価格をご確認ください。
Amazonのアソシエイトとして、当サイトは適格販売により収入を得ています。
｜ <a href="rss.xml" style="color:inherit">RSS</a>
</footer>
</body>
</html>
"""


def generate_rss(data: dict) -> str:
    site_url = CONFIG.get("site_url", "")
    now = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%a, %d %b %Y %H:%M:%S +0000"
    )
    items_xml = []
    seen: set[str] = set()
    for genre in data["genres"]:
        for b in genre["items"][:20]:
            if b["asin"] in seen:
                continue
            seen.add(b["asin"])
            off = f"【{b['percent_off']}%OFF】" if b.get("percent_off") else ""
            items_xml.append(
                f"""<item>
<title>{esc(off + b["title"] + f" ¥{int(b['price']):,}")}</title>
<link>{esc(b["url"])}</link>
<guid isPermaLink="false">{esc(b["asin"])}</guid>
<category>{esc(genre["name"])}</category>
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


def main():
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    DOCS.mkdir(exist_ok=True)
    (DOCS / "index.html").write_text(generate_html(data), encoding="utf-8")
    (DOCS / "rss.xml").write_text(generate_rss(data), encoding="utf-8")
    total = sum(len(g["items"]) for g in data["genres"])
    print(f"generated: docs/index.html, docs/rss.xml ({total}冊)")


if __name__ == "__main__":
    main()
