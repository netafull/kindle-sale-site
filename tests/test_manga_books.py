"""widget.json の manga_books と、その元になるマンガ判定のテスト。

実行: python3 -m unittest discover -s tests -v
Amazon APIは呼ばない(ダミーデータだけで検証する)。
"""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import fetch_sales  # noqa: E402
import generate_site  # noqa: E402


def item(asin, title, price=100, list_price=200, percent_off=50, points_percent=0):
    return {
        "asin": asin,
        "title": title,
        "author": None,
        "price": price,
        "list_price": list_price,
        "percent_off": percent_off,
        "points": None,
        "points_percent": points_percent,
        "image": f"https://example.com/{asin}.jpg",
        "url": f"https://www.amazon.co.jp/dp/{asin}",
    }


class CollectMangaItems(unittest.TestCase):
    def test_only_manga_genre_and_manga_campaigns(self):
        genres = [
            {"name": "総合", "items": [item("G1", "小説アルファ")]},
            {"name": "マンガ", "items": [item("M1", "漫画あ")]},
        ]
        campaigns = [
            {"name": "Amazonマンガ週末祭 第4弾", "items": [item("C1", "漫画い")]},
            {"name": "実用書フェア", "items": [item("C2", "実用書")]},
            {"name": "スターツ出版 夏のコミック＆ノベルフェア", "items": [item("C3", "混在")]},
        ]
        asins = {b["asin"] for b in fetch_sales.collect_manga_items(genres, campaigns)}
        self.assertEqual(asins, {"M1", "C1"})

    def test_dedupe_by_asin_and_sorted(self):
        genres = [
            {
                "name": "マンガ",
                "items": [
                    item("A", "作品アルファ", percent_off=30),
                    item("B", "作品ベータ", percent_off=60),
                ],
            }
        ]
        campaigns = [
            {"name": "コミックフェア", "items": [item("A", "作品アルファ", percent_off=30)]}
        ]
        result = fetch_sales.collect_manga_items(genres, campaigns)
        self.assertEqual([b["asin"] for b in result], ["B", "A"])

    def test_no_manga_genre_returns_empty(self):
        self.assertEqual(
            fetch_sales.collect_manga_items([{"name": "総合", "items": [item("X", "x")]}], []),
            [],
        )


class MangaBooks(unittest.TestCase):
    def data(self, manga_items):
        return {
            "fetched_at": "2026-01-01T00:00:00+00:00",
            "campaigns": [{"name": "c", "items": [item("C1", "本1", percent_off=10)]}],
            "others": [item("O1", "本2", percent_off=20)],
            "manga_items": manga_items,
        }

    def test_sort_by_percent_then_points(self):
        d = self.data(
            [
                item("A", "漫画A", percent_off=40, points_percent=10),
                item("B", "漫画B", percent_off=70, points_percent=0),
                item("C", "漫画C", percent_off=40, points_percent=30),
            ]
        )
        books = generate_site.generate_widget_data(d)["manga_books"]
        self.assertEqual([b["title"] for b in books], ["漫画B", "漫画C", "漫画A"])

    def test_excludes_abnormal(self):
        d = self.data(
            [
                item("OK", "正常", price=30),
                item("CHEAP", "安すぎ", price=29),
                item("NOLIST", "定価なし", list_price=None),
                item("NOPCT", "割引率なし", percent_off=None),
            ]
        )
        books = generate_site.generate_widget_data(d)["manga_books"]
        self.assertEqual([b["title"] for b in books], ["正常"])

    def test_pool_size_from_config(self):
        d = self.data([item(f"A{i}", f"漫画{i}", percent_off=i + 1) for i in range(30)])
        old = generate_site.CONFIG.get("widget_manga_pool_size")
        try:
            generate_site.CONFIG["widget_manga_pool_size"] = 3
            self.assertEqual(len(generate_site.generate_widget_data(d)["manga_books"]), 3)
            del generate_site.CONFIG["widget_manga_pool_size"]
            self.assertEqual(len(generate_site.generate_widget_data(d)["manga_books"]), 10)
        finally:
            if old is not None:
                generate_site.CONFIG["widget_manga_pool_size"] = old

    def test_book_fields(self):
        d = self.data([item("A", "漫画A")])
        book = generate_site.generate_widget_data(d)["manga_books"][0]
        self.assertEqual(
            set(book),
            {"title", "price", "list_price", "percent_off", "points",
             "points_percent", "image", "url"},
        )

    def test_old_sales_json_without_key(self):
        d = self.data([])
        del d["manga_items"]
        self.assertEqual(generate_site.generate_widget_data(d)["manga_books"], [])

    def test_books_unchanged_by_manga_items(self):
        with_manga = self.data([item("A", "漫画A", percent_off=99)])
        without = self.data([])
        a = generate_site.generate_widget_data(with_manga)
        b = generate_site.generate_widget_data(without)
        self.assertEqual(a["books"], b["books"])
        self.assertEqual([x["title"] for x in a["books"]], ["本2", "本1"])
        for k in ("updated", "site_url", "site_title", "campaign_count"):
            self.assertEqual(a[k], b[k])


if __name__ == "__main__":
    unittest.main()
