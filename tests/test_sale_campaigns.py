"""widget.json の sale_campaigns(セール企画一覧)のテスト。

実行: python3 -m unittest discover -s tests -v
Amazon APIは呼ばない(ダミーデータだけで検証する)。
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import generate_site  # noqa: E402

AMAZON = "https://www.amazon.co.jp/b?node="


def book(asin, percent_off=50):
    return {
        "asin": asin,
        "title": f"本{asin}",
        "price": 100,
        "list_price": 200,
        "percent_off": percent_off,
        "points": None,
        "points_percent": 0,
        "image": None,
        "url": f"https://www.amazon.co.jp/dp/{asin}",
    }


def camp(name, since_at=None, total=100, items=True, url=None, node="1", since=None):
    c = {
        "node_id": node,
        "name": name,
        "url": AMAZON + node if url is None else url,
        "total": total,
        "items": [book("X" + node)] if items else [],
    }
    if since_at:
        c["since_at"] = since_at
    if since:
        c["since"] = since
    return c


def build(campaigns, **extra):
    d = {"fetched_at": "2026-01-01T00:00:00+00:00", "campaigns": campaigns, "others": []}
    d.update(extra)
    return generate_site.generate_widget_data(d)["sale_campaigns"]


class SaleCampaigns(unittest.TestCase):
    def test_fields(self):
        r = build([camp("マンガ祭", "2026-07-30T01:00:00+00:00", total=42, node="9")])
        self.assertEqual(
            r,
            [
                {
                    "name": "マンガ祭",
                    "url": AMAZON + "9",
                    "total": 42,
                    "since": "2026-07-30T01:00:00+00:00",
                    "is_manga": True,
                }
            ],
        )

    def test_since_falls_back_to_date(self):
        r = build([camp("実用書フェア", since="2026-07-28")])
        self.assertEqual(r[0]["since"], "2026-07-28")

    def test_is_manga_judgement(self):
        r = {c["name"]: c["is_manga"] for c in build([
            camp("Amazonマンガ週末祭", node="1"),
            camp("夏休み コミックフェア", node="2"),
            camp("スターツ出版 夏のコミック＆ノベルフェア", node="3"),
            camp("実用書フェア", node="4"),
            camp("文庫フェア", node="5"),
        ])}
        self.assertEqual(
            r,
            {
                "Amazonマンガ週末祭": True,
                "夏休み コミックフェア": True,
                "スターツ出版 夏のコミック＆ノベルフェア": False,
                "実用書フェア": False,
                "文庫フェア": False,
            },
        )

    def test_exclusions(self):
        r = build([
            camp("OK", node="1"),
            camp("非Amazon", url="https://example.com/b?node=2", node="2"),
            camp("偽装", url="https://www.amazon.co.jp.evil.com/b", node="3"),
            camp("", node="4"),
            camp("   ", node="5"),
            camp("冊数ゼロ", total=0, node="6"),
            camp("冊数負", total=-1, node="7"),
            camp("商品なし", items=False, node="8"),
        ])
        self.assertEqual([c["name"] for c in r], ["OK"])

    def test_duplicate_name_keeps_newer(self):
        r = build([
            camp("サマーセール", "2026-07-23T00:00:00+00:00", node="1", total=10),
            camp("サマーセール", "2026-07-29T00:00:00+00:00", node="2", total=20),
            camp("サマーセール", "2026-07-25T00:00:00+00:00", node="3", total=30),
        ])
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["url"], AMAZON + "2")
        self.assertEqual(r[0]["total"], 20)

    def test_prefix_removed(self):
        r = build([
            camp("【対象作品2500点以上】カドサマー2026第3弾", node="1"),
            camp("【告知】", node="2"),
            camp("  前後空白  ", node="3"),
            camp("＜最大60％OFF＞カドサマー", node="4"),
            camp("途中の【注】は残す", node="5"),
        ])
        self.assertEqual(
            sorted(c["name"] for c in r),
            sorted(["カドサマー2026第3弾", "【告知】", "前後空白", "＜最大60％OFF＞カドサマー", "途中の【注】は残す"]),
        )

    def test_duplicate_after_prefix_removed(self):
        r = build([
            camp("【対象作品800点以上】KADOKAWAフェア", "2026-07-22T01:00:00+00:00", node="1"),
            camp("【対象作品490点以上】KADOKAWAフェア", "2026-07-22T02:00:00+00:00", node="2"),
        ])
        self.assertEqual([c["name"] for c in r], ["KADOKAWAフェア"])
        self.assertEqual(r[0]["url"], AMAZON + "2")

    def test_manga_first_then_newest(self):
        r = build([
            camp("実用書A", "2026-07-30T00:00:00+00:00", node="1"),
            camp("マンガB", "2026-07-20T00:00:00+00:00", node="2"),
            camp("コミックC", "2026-07-25T00:00:00+00:00", node="3"),
            camp("実用書D", "2026-07-28T00:00:00+00:00", node="4"),
            camp("漫画E(日付なし)", node="5"),
            camp("実用書F(日付なし)", node="6"),
        ])
        self.assertEqual(
            [c["name"] for c in r],
            ["コミックC", "マンガB", "漫画E(日付なし)", "実用書A", "実用書D", "実用書F(日付なし)"],
        )

    def test_pool_size_from_config(self):
        camps = [camp(f"企画{i}", f"2026-07-{i + 1:02d}T00:00:00+00:00", node=str(i)) for i in range(10)]
        old = generate_site.CONFIG.get("widget_campaign_pool_size")
        try:
            generate_site.CONFIG["widget_campaign_pool_size"] = 3
            self.assertEqual(len(build(camps)), 3)
            del generate_site.CONFIG["widget_campaign_pool_size"]
            self.assertEqual(len(build(camps)), 6)
        finally:
            if old is not None:
                generate_site.CONFIG["widget_campaign_pool_size"] = old

    def test_old_data_without_campaigns_key(self):
        d = {"fetched_at": "x", "others": [], "campaigns": None}
        self.assertEqual(generate_site.generate_widget_data(d)["sale_campaigns"], [])
        del d["campaigns"]
        self.assertEqual(generate_site.generate_widget_data(d)["sale_campaigns"], [])

    def test_books_and_manga_books_unchanged(self):
        base = [camp("実用書", "2026-07-30T00:00:00+00:00", node="1")]
        with_extra = base + [camp("マンガ祭", "2026-07-31T00:00:00+00:00", node="2")]
        manga = [book("M1", 60)]
        a = generate_site.generate_widget_data(
            {"fetched_at": "t", "campaigns": base, "others": [], "manga_items": manga}
        )
        b = generate_site.generate_widget_data(
            {"fetched_at": "t", "campaigns": base, "others": [], "manga_items": manga}
        )
        self.assertEqual(a, b)
        self.assertEqual([x["title"] for x in a["manga_books"]], ["本M1"])
        self.assertEqual([x["title"] for x in a["books"]], ["本X1"])
        c = generate_site.generate_widget_data(
            {"fetched_at": "t", "campaigns": with_extra, "others": [], "manga_items": manga}
        )
        self.assertEqual(c["manga_books"], a["manga_books"])


if __name__ == "__main__":
    unittest.main()
