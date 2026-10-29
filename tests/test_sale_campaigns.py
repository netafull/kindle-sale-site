"""widget.json の sale_campaigns(セール企画一覧)のテスト。

実行: python3 -m unittest discover -s tests -v
Amazon APIは呼ばない(ダミーデータだけで検証する)。
"""

import datetime
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import generate_site  # noqa: E402

AMAZON = "https://www.amazon.co.jp/b?node="
# 鮮度判定の「今日」は固定する(既定の許容は30日 → 2026-07-02 以降が対象)
TODAY = datetime.date(2026, 8, 1)
DEFAULT_SINCE = "2026-07-30T00:00:00+00:00"
NO_SINCE = object()


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


def camp(name, since_at=DEFAULT_SINCE, total=100, items=True, url=None, node="1", since=None):
    c = {
        "node_id": node,
        "name": name,
        "url": AMAZON + node if url is None else url,
        "total": total,
        "items": [book("X" + node)] if items else [],
    }
    if since_at is NO_SINCE or since:
        since_at = None
    if since_at:
        c["since_at"] = since_at
    if since:
        c["since"] = since
    return c


def build(campaigns, today=TODAY, **extra):
    d = {"fetched_at": "2026-01-01T00:00:00+00:00", "campaigns": campaigns, "others": []}
    d.update(extra)
    return generate_site.generate_widget_data(d, today)["sale_campaigns"]


class SaleCampaigns(unittest.TestCase):
    def _max(self, items):
        c = camp("マンガ祭")
        c["items"] = items
        return build([c])[0]["max_percent_off"]

    def test_max_percent_off_is_max_of_items(self):
        self.assertEqual(self._max([book("A", 40), book("B", 91), book("C", 70)]), 91)

    def test_max_percent_off_rounds_to_int(self):
        self.assertEqual(self._max([book("A", 80.6), book("B", 40)]), 81)

    def test_max_percent_off_excludes_abnormal_price(self):
        cheap = book("A", 99)
        cheap["price"] = 11
        zero = book("B", 95)
        zero["price"] = None
        edge = book("C", 60)
        edge["price"] = 30
        self.assertEqual(self._max([cheap, zero, edge, book("D", 50)]), 60)

    def test_max_percent_off_excludes_missing_list_price(self):
        no_list = book("A", 90)
        no_list["list_price"] = None
        self.assertEqual(self._max([no_list, book("B", 30)]), 30)

    def test_max_percent_off_null_when_nothing_qualifies(self):
        cheap = book("A", 99)
        cheap["price"] = 11
        no_list = book("B", 90)
        no_list["list_price"] = None
        no_pct = book("C", None)
        zero_pct = book("D", 0)
        neg_pct = book("E", -5)
        self.assertIsNone(self._max([cheap, no_list, no_pct, zero_pct, neg_pct]))

    def test_max_percent_off_does_not_change_order_or_other_keys(self):
        r = build([camp("A祭", node="1"), camp("B祭", node="2")])
        self.assertEqual([x["name"] for x in r], ["A祭", "B祭"])
        self.assertTrue(all("max_percent_off" in x for x in r))

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
                    "max_percent_off": 50,
                    "sample_titles": ["本X9"],
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
            camp("小学館 漫祭2026 第7弾", node="6"),
        ])}
        self.assertEqual(
            r,
            {
                "Amazonマンガ週末祭": True,
                "夏休み コミックフェア": True,
                "スターツ出版 夏のコミック＆ノベルフェア": False,
                "実用書フェア": False,
                "文庫フェア": False,
                "小学館 漫祭2026 第7弾": True,
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
            camp("漫画E(日付なし)", NO_SINCE, node="5"),
            camp("実用書F(日付なし)", NO_SINCE, node="6"),
        ])
        self.assertEqual(
            [c["name"] for c in r],
            ["コミックC", "マンガB", "実用書A", "実用書D"],
        )

    def test_pool_size_from_config(self):
        camps = [camp(f"企画{i}", f"2026-07-{i + 10:02d}T00:00:00+00:00", node=str(i)) for i in range(10)]
        old = generate_site.CONFIG.get("widget_campaign_pool_size")
        try:
            generate_site.CONFIG["widget_campaign_pool_size"] = 3
            self.assertEqual(len(build(camps)), 3)
            del generate_site.CONFIG["widget_campaign_pool_size"]
            self.assertEqual(len(build(camps)), 6)
        finally:
            if old is not None:
                generate_site.CONFIG["widget_campaign_pool_size"] = old

    def test_old_campaigns_excluded(self):
        r = build([
            camp("新しい", "2026-07-30T00:00:00+00:00", node="1"),
            camp("古い企画", "2026-06-01T00:00:00+00:00", node="2"),
            camp("古いマンガ企画", "2026-05-01", node="3"),
        ])
        self.assertEqual([c["name"] for c in r], ["新しい"])

    def test_age_boundary_30_days(self):
        # 今日=2026-08-01。30日前=2026-07-02 は残り、31日前=2026-07-01 は除外
        r = build([
            camp("ちょうど30日", "2026-07-02T23:59:59+00:00", node="1"),
            camp("31日前", "2026-07-01T23:59:59+00:00", node="2"),
            camp("日付のみ30日", since="2026-07-02", node="3"),
            camp("日付のみ31日", since="2026-07-01", node="4"),
        ])
        self.assertEqual(sorted(c["name"] for c in r), ["ちょうど30日", "日付のみ30日"])

    def test_missing_or_invalid_since_excluded(self):
        r = build([
            camp("日付なし", NO_SINCE, node="1"),
            camp("壊れた日付", "not-a-date", node="2"),
            camp("空文字", "", node="3"),
            camp("OK", node="4"),
        ])
        self.assertEqual([c["name"] for c in r], ["OK"])

    def test_old_duplicate_does_not_override(self):
        # 新しい方が鮮度条件を満たし、古い同名は無視される
        r = build([
            camp("サマー", "2026-05-01T00:00:00+00:00", node="1"),
            camp("サマー", "2026-07-29T00:00:00+00:00", node="2"),
        ])
        self.assertEqual([c["url"] for c in r], [AMAZON + "2"])

    def test_max_age_from_config(self):
        camps = [camp("A", "2026-07-20T00:00:00+00:00", node="1")]
        old = generate_site.CONFIG.get("widget_campaign_max_age_days")
        try:
            generate_site.CONFIG["widget_campaign_max_age_days"] = 5
            self.assertEqual(build(camps), [])
            generate_site.CONFIG["widget_campaign_max_age_days"] = 12
            self.assertEqual(len(build(camps)), 1)
        finally:
            if old is not None:
                generate_site.CONFIG["widget_campaign_max_age_days"] = old

    def test_today_defaults_to_real_today(self):
        today = datetime.date.today()
        fresh = camp("今日", today.isoformat() + "T00:00:00+00:00", node="1")
        stale = camp("古い", (today - datetime.timedelta(days=60)).isoformat(), node="2")
        d = {"fetched_at": "x", "campaigns": [fresh, stale], "others": []}
        r = generate_site.generate_widget_data(d)["sale_campaigns"]
        self.assertEqual([c["name"] for c in r], ["今日"])

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


def titled(title, percent_off=50, **over):
    b = book("T", percent_off)
    b["title"] = title
    b.update(over)
    return b


class SeriesTitle(unittest.TestCase):
    def test_removes_label_and_volume(self):
        self.assertEqual(
            generate_site.series_title("平和の国の島崎へ（１） (モーニングコミックス)"), "平和の国の島崎へ"
        )

    def test_removes_edge_brackets_and_total_volumes(self):
        self.assertEqual(
            generate_site.series_title("【合本版】C3　-シーキューブ-　全17巻 (富士見ファンタジア文庫)"),
            "C3\u3000-シーキューブ-",
        )
        self.assertEqual(generate_site.series_title("鬼滅の刃 【電子特典付き】"), "鬼滅の刃")
        self.assertEqual(generate_site.series_title("【合本版】【電子特典付き】鬼滅の刃"), "鬼滅の刃")

    def test_volume_patterns(self):
        for t in ["進撃の巨人(2)", "進撃の巨人（２）", "進撃の巨人 3巻", "進撃の巨人 第3巻",
                  "進撃の巨人第３巻", "進撃の巨人 3", "進撃の巨人　３", "進撃の巨人 全巻",
                  "進撃の巨人 (講談社コミックス) (34)"]:
            self.assertEqual(generate_site.series_title(t), "進撃の巨人", t)

    def test_repeated_labels(self):
        self.assertEqual(generate_site.series_title("作品名 (A) (B) (C)"), "作品名")

    def test_keeps_digits_glued_to_title(self):
        self.assertEqual(generate_site.series_title("C3"), "C3")
        self.assertEqual(generate_site.series_title("Re:ゼロから始める異世界生活2"), "Re:ゼロから始める異世界生活2")

    def test_plain_title_is_unchanged(self):
        self.assertEqual(generate_site.series_title("アーキテクトの教科書"), "アーキテクトの教科書")

    def test_falls_back_to_original_when_empty(self):
        self.assertEqual(generate_site.series_title("【合本版】"), "【合本版】")
        self.assertEqual(generate_site.series_title("  (1)  "), "(1)")
        self.assertEqual(generate_site.series_title("　"), "")

    def test_truncates_to_18_chars_with_ellipsis(self):
        t18 = "あ" * 18
        self.assertEqual(generate_site.series_title(t18), t18)
        out = generate_site.series_title("あ" * 19)
        self.assertEqual(len(out), 18)
        self.assertTrue(out.endswith("…"))
        self.assertEqual(out, "あ" * 17 + "…")

    def test_truncates_after_cleaning(self):
        # 整えた後の長さで判定する(括弧書きの分で切られない)
        self.assertEqual(generate_site.series_title("あ" * 18 + " (とても長いレーベル名がここに入ります)"), "あ" * 18)


class SampleTitles(unittest.TestCase):
    def sample(self, items, **kw):
        return generate_site.campaign_sample_titles(items, **kw)

    def test_sorted_by_percent_off_desc(self):
        r = self.sample([titled("A", 30), titled("B", 90), titled("C", 60)])
        self.assertEqual(r, ["B", "C"])

    def test_ties_keep_original_order(self):
        r = self.sample([titled("A", 50), titled("B", 50), titled("C", 50)], limit=3)
        self.assertEqual(r, ["A", "B", "C"])

    def test_same_series_is_merged(self):
        r = self.sample([
            titled("作品X（１） (レーベル)", 90),
            titled("作品X（２） (レーベル)", 85),
            titled("【合本版】作品X 全5巻", 80),
            titled("作品Y 1", 70),
            titled("作品Z 1", 60),
        ])
        self.assertEqual(r, ["作品X", "作品Y"])

    def test_limit(self):
        items = [titled(f"作品{i}", 90 - i) for i in range(5)]
        self.assertEqual(len(self.sample(items)), 2)
        self.assertEqual(len(self.sample(items, limit=4)), 4)
        self.assertEqual(self.sample(items, limit=1), ["作品0"])
        self.assertEqual(self.sample(items, limit=0), [])

    def test_fewer_candidates_than_limit(self):
        self.assertEqual(self.sample([titled("A", 50)]), ["A"])

    def test_excludes_abnormal_price_no_list_price_and_nonpositive(self):
        r = self.sample([
            titled("安すぎ", 99, price=11),
            titled("価格なし", 98, price=None),
            titled("定価なし", 97, list_price=None),
            titled("割引なし", None),
            titled("ゼロ", 0),
            titled("負", -5),
            titled("真偽値", True),
            titled("境界", 40, price=30),
            titled("通常", 20),
        ])
        self.assertEqual(r, ["境界", "通常"])

    def test_ignores_bad_titles(self):
        r = self.sample([
            titled("", 99), titled("   ", 98), titled(None, 97), titled(123, 96), titled("OK", 10),
        ])
        self.assertEqual(r, ["OK"])

    def test_empty_or_none(self):
        self.assertEqual(self.sample([]), [])
        self.assertEqual(self.sample(None), [])

    def test_same_selection_as_max_percent_off(self):
        # 除外判定は campaign_max_percent_off と共通(既存挙動は変えない)
        items = [titled("安すぎ", 99, price=11), titled("A", 60)]
        self.assertEqual(generate_site.campaign_max_percent_off(items), 60)
        self.assertEqual(self.sample(items), ["A"])


class SampleTitlesInWidget(unittest.TestCase):
    def test_generate_sale_campaigns_has_sample_titles(self):
        c = camp("マンガ祭")
        c["items"] = [
            titled("平和の国の島崎へ（１） (モーニングコミックス)", 70),
            titled("平和の国の島崎へ（２） (モーニングコミックス)", 75),
            titled("【合本版】C3　-シーキューブ-　全17巻 (富士見ファンタジア文庫)", 60),
        ]
        r = build([c])
        self.assertEqual(r[0]["sample_titles"], ["平和の国の島崎へ", "C3\u3000-シーキューブ-"])
        self.assertEqual(r[0]["max_percent_off"], 75)

    def test_empty_when_no_usable_items(self):
        c = camp("マンガ祭")
        c["items"] = [titled("安すぎ", 99, price=11)]
        self.assertEqual(build([c])[0]["sample_titles"], [])

    def test_key_always_present(self):
        r = build([camp("A祭", node="1"), camp("B祭", node="2")])
        self.assertTrue(all(isinstance(x["sample_titles"], list) for x in r))


if __name__ == "__main__":
    unittest.main()
