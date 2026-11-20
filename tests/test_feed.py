"""docs/feed.json(ポチフル用の新着フィード)のテスト。Amazon APIは呼ばない。

実行: python3 -m unittest discover -s tests -v
"""

import datetime
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import generate_site  # noqa: E402

JST = datetime.timezone(datetime.timedelta(hours=9))
NOW = datetime.datetime(2026, 11, 20, 6, 0, tzinfo=JST)


def book(asin, pct, price=100):
    return {
        "asin": asin, "title": asin, "price": price, "list_price": 500,
        "percent_off": pct, "image": f"https://m.media-amazon.com/images/I/{asin}.jpg",
        "url": f"https://www.amazon.co.jp/dp/{asin}?tag=t-22",
    }


def camp(node, name, since, items=None, since_at=None):
    c = {"node_id": node, "name": name, "since": since, "items": items if items is not None else [book("A" + node, 30), book("B" + node, 60, 1980)]}
    if since_at:
        c["since_at"] = since_at
    return c


class FeedTest(unittest.TestCase):
    def feed(self, camps):
        return generate_site.generate_feed_data({"campaigns": camps}, NOW)

    def test_shape_and_best_item(self):
        f = self.feed([camp("1", "【対象100点】春セール", "2026-11-20")])
        self.assertEqual(f["version"], 1)
        self.assertEqual(f["site"], "book")
        it = f["items"][0]
        self.assertEqual(it["id"], "book:1")
        self.assertEqual(it["title"], "春セール")
        self.assertEqual(it["note"], "最大60%OFF ¥1,980")
        self.assertTrue(it["url"].endswith("#c0"))
        self.assertIn("tag=", it["image_link"])
        self.assertEqual(it["source"], "book")

    def test_window_and_order(self):
        f = self.feed([
            camp("1", "A", "2026-11-18"),
            camp("2", "B", "2026-11-20"),
            camp("3", "C", "2026-11-17"),
            camp("4", "D", "2026-11-19"),
        ])
        self.assertEqual([i["id"] for i in f["items"]], ["book:2", "book:4", "book:1"])

    def test_since_at_utc_converted_to_jst(self):
        c = camp("1", "A", None, since_at="2026-11-19T20:00:00+00:00")
        c.pop("since")
        self.assertEqual(self.feed([c])["items"][0]["date"], "2026-11-20")

    def test_no_date_skipped_and_max_20(self):
        c = camp("nodate", "X", None)
        c.pop("since")
        camps = [c] + [camp(str(n), f"N{n}", "2026-11-20") for n in range(30)]
        f = self.feed(camps)
        self.assertEqual(len(f["items"]), 20)
        self.assertNotIn("book:nodate", [i["id"] for i in f["items"]])

    def test_no_usable_item_has_no_image(self):
        f = self.feed([camp("1", "A", "2026-11-20", items=[])])
        it = f["items"][0]
        self.assertNotIn("image", it)
        self.assertNotIn("note", it)


if __name__ == "__main__":
    unittest.main()
