"""出版社別・型別ページ(個別ページ)と、開催履歴の保持のテスト。

実行: python3 -m unittest discover -s tests -v
Amazon APIは呼ばない(ダミーデータだけで検証する)。
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import fetch_sales  # noqa: E402
import generate_site  # noqa: E402


def book(asin="B1", title="本B1"):
    return {
        "asin": asin,
        "title": title,
        "author": None,
        "price": 100,
        "list_price": 200,
        "percent_off": 50,
        "points": None,
        "points_percent": 0,
        "image": None,
        "url": f"https://www.amazon.co.jp/dp/{asin}",
    }


def camp(node, name, since="2026-07-30", total=100):
    return {
        "node_id": node,
        "name": name,
        "url": f"https://www.amazon.co.jp/b?node={node}&tag=natafull-22",
        "total": total,
        "items": [book()],
        "since": since,
    }


def data(campaigns):
    return {
        "fetched_at": "2026-08-01T00:00:00+00:00",
        "min_saving_percent": 20,
        "campaigns": campaigns,
        "others": [],
    }


class PublisherOf(unittest.TestCase):
    def test_representative_names(self):
        cases = {
            "【対象作品800点以上】KADOKAWAのKindle本フェア": "kadokawa",
            "＜最大60％OFF＞カドサマー2026第 2弾": "kadokawa",
            "KADOKAWAの対象作品が50％ポイント還元中": "kadokawa",
            "講談社コミックス 88円均一セール": "kodansha",
            "講談社夏電書": "kodansha",
            "小学館 漫祭2026 第7弾": "shogakukan",
            "集英社 夏デジ2026": "shueisha",
            "映像化原作シリーズ大集合！ 集英社文庫フェア": "shueisha",
            "白泉社 夏の大割引セール開催中": "hakusensha",
            "翔泳社 Kindle本50%OFF！サマーセール第一弾": "shoeisha",
            "コアミックス 夏の全巻イッキ読み！99円セール": "coamix",
            "ナンバーナイン オススメ作品特集": "number-nine",
            "主婦の友社の料理書 50％OFFセール": "shufunotomo",
            "文藝春秋 夏の大感謝祭 50%ポイント還元セール": "bungeishunju",
            "光文社新書創刊25周年記念セール第1弾 名著250円！": "kobunsha",
            "幻冬舎新書 創刊20周年特集": "gentosha",
            "【最大50％OFF】山と溪谷社 山の日フェア！": "yamatokeikoku",
            "技術評論社 「今日から変わる！ 人体クロッキー」発売記念": "gijutsuhyoron",
            "扶桑社 いま読む注目作品！": "fusosha",
            "スターツ出版 夏のコミック＆ノベルフェア": "starts",
        }
        for name, slug in cases.items():
            got = generate_site.publisher_of(name)
            self.assertIsNotNone(got, name)
            self.assertEqual(got[0], slug, name)

    def test_no_publisher(self):
        for name in [
            "「姫川玲子シリーズ」20周年記念 誉田哲也 7社合同 Kindle Unlimitedフェア",
            "実用書フェア第1弾",
            "Amazonマンガ毎週末セール",
            "",
        ]:
            self.assertIsNone(generate_site.publisher_of(name), name)


class FormatsOf(unittest.TestCase):
    def slugs(self, name):
        return [s for s, _ in generate_site.formats_of(name)]

    def test_weekend(self):
        self.assertEqual(self.slugs("Amazonマンガ毎週末セール 8月第1週"), ["weekend"])
        self.assertEqual(self.slugs("Amazonマンガ週末祭 第4弾"), ["weekend"])

    def test_uniform(self):
        self.assertEqual(self.slugs("Kindle本 99円セール"), ["uniform"])
        self.assertEqual(self.slugs("Kindle本 199円セール"), ["uniform"])
        self.assertEqual(self.slugs("Kindle本499円キャンペーン"), ["uniform"])
        self.assertEqual(self.slugs("講談社コミックス 88円均一セール"), ["uniform"])
        self.assertEqual(self.slugs("コアミックス 夏の全巻イッキ読み！99円セール"), ["uniform"])

    def test_points(self):
        self.assertEqual(self.slugs("50%ポイント還元フェア"), ["points"])
        self.assertEqual(self.slugs("読書の秋 50%ポイント還元フェア"), ["points"])

    def test_seasonal(self):
        self.assertEqual(self.slugs("最大50％OFF 冬のビッグセール"), ["seasonal"])
        self.assertEqual(self.slugs("本のビッグセール2026冬"), ["seasonal"])
        self.assertEqual(self.slugs("秋の特別セール"), ["seasonal"])
        self.assertEqual(self.slugs("Kindle 秋の特別セール"), ["seasonal"])

    def test_multiple_formats(self):
        self.assertEqual(
            self.slugs("Kindle本 夏の超ビッグセール50％ポイント還元"),
            ["points", "seasonal"],
        )

    def test_no_format(self):
        self.assertEqual(self.slugs("実用書フェア第1弾"), [])
        # 「250円！」は均一セールのパターン(○円セール/キャンペーン/均一)に当たらない
        self.assertEqual(self.slugs("光文社新書創刊25周年記念セール第1弾 名著250円！"), [])


class MergeArchiveRows(unittest.TestCase):
    def test_state_wins_and_inherits_total(self):
        seed = [
            {"name": "フェア", "first_seen": "2026-07-22", "last_seen": "2026-08-01", "total": 570}
        ]
        state = {
            "123": {
                "name": "フェア",
                "first_seen": "2026-07-22",
                "last_seen": "2026-08-05",
                "notified": True,
            }
        }
        rows = generate_site.merge_archive_rows(seed, state)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["last_seen"], "2026-08-05")
        self.assertEqual(rows[0]["node_id"], "123")
        self.assertEqual(rows[0]["total"], 570)

    def test_dedupes_by_name_and_first_seen(self):
        seed = [
            {"name": "フェア", "first_seen": "2026-07-22", "last_seen": "2026-08-01"},
            {"name": "フェア", "first_seen": "2026-07-22", "last_seen": "2026-08-02"},
            {"name": "フェア", "first_seen": "2026-09-01", "last_seen": "2026-09-10"},
        ]
        rows = generate_site.merge_archive_rows(seed, {})
        self.assertEqual(len(rows), 2)
        # 開始日の新しい順
        self.assertEqual(rows[0]["first_seen"], "2026-09-01")

    def test_skips_broken_rows(self):
        seed = [
            {"name": "", "first_seen": "2026-07-22", "last_seen": "2026-08-01"},
            {"name": "日付なし", "first_seen": None, "last_seen": None},
            {"name": "壊れた日付", "first_seen": "not-a-date", "last_seen": "2026-08-01"},
            {"name": "逆転", "first_seen": "2026-08-10", "last_seen": "2026-08-01"},
            "not-a-dict",
        ]
        state = {"9": {"name": "状態のみ", "first_seen": "2026-08-01"}}
        rows = generate_site.merge_archive_rows(seed, state)
        names = {r["name"] for r in rows}
        self.assertEqual(names, {"逆転", "状態のみ"})
        # 終了日が開始日より前なら開始日に丸める
        rev = next(r for r in rows if r["name"] == "逆転")
        self.assertEqual(rev["last_seen"], "2026-08-10")
        # last_seen が無い状態エントリは開始日で補う
        only = next(r for r in rows if r["name"] == "状態のみ")
        self.assertEqual(only["last_seen"], "2026-08-01")
        self.assertEqual(only["node_id"], "9")


class IdentityPages(unittest.TestCase):
    def setUp(self):
        self.data = data([camp("N1", "【対象作品2500点以上】カドサマー2026第3弾")])
        self.archive = [
            {"name": "【対象作品2500点以上】カドサマー2026第3弾", "first_seen": "2026-07-30",
             "last_seen": "2026-08-01", "node_id": "N1", "total": None},
            {"name": "講談社夏電書", "first_seen": "2026-08-04",
             "last_seen": "2026-09-30", "node_id": "N2", "total": 300},
            {"name": "Amazonマンガ週末祭 第4弾", "first_seen": "2026-07-28",
             "last_seen": "2026-07-31", "node_id": "N3", "total": None},
            {"name": "実用書フェア第1弾", "first_seen": "2026-08-04",
             "last_seen": "2026-08-04", "node_id": "N4", "total": None},
        ]
        self.index = generate_site.build_identity_index(self.data, self.archive)
        self.pages = generate_site.generate_identity_pages(self.data, self.index)

    def test_page_paths(self):
        self.assertEqual(
            set(self.pages),
            {
                "publishers/kadokawa/index.html",
                "publishers/kodansha/index.html",
                "formats/weekend/index.html",
            },
        )

    def test_current_campaign_page(self):
        html = self.pages["publishers/kadokawa/index.html"]
        self.assertIn("<title>KADOKAWAのKindle本セール・フェア｜電書ポチ</title>", html)
        self.assertIn(
            '<link rel="canonical" href="https://book.netaful.jp/publishers/kadokawa/">',
            html,
        )
        self.assertIn("カドサマー2026第3弾", html)
        self.assertIn("本B1", html)  # 代表商品
        self.assertIn("開催中</span>", html)  # 履歴行の開催中バッジ
        self.assertIn("2026/7/30〜開催中", html)

    def test_history_only_page(self):
        html = self.pages["publishers/kodansha/index.html"]
        self.assertIn("現在開催中の講談社の企画はありません", html)
        self.assertIn("講談社夏電書", html)
        self.assertIn("2026/8/4〜9/30", html)
        self.assertIn("対象約300冊", html)

    def test_format_page(self):
        html = self.pages["formats/weekend/index.html"]
        self.assertIn("<title>Kindle本の週末セール｜電書ポチ</title>", html)
        self.assertIn("Amazonマンガ週末祭 第4弾", html)
        self.assertIn("2026/7/28〜7/31", html)

    def test_no_page_without_data(self):
        # 開催実績の無い出版社はマッピングにあってもページを作らない
        self.assertNotIn("publishers/akitashoten/index.html", self.pages)

    def test_current_total_fills_history_row(self):
        # sales.json の total が、状態由来で total を持たない履歴行に補われる
        entry = self.index[("publisher", "kadokawa")]
        row = next(r for r in entry["history"] if r["node_id"] == "N1")
        self.assertEqual(row["total"], 100)
        self.assertTrue(row["is_current"])

    def test_nav_lists_only_generated_pages(self):
        nav = generate_site.identity_nav_html(self.index)
        self.assertIn('<a href="publishers/kadokawa/"', nav)
        self.assertIn('<a href="publishers/kodansha/"', nav)
        self.assertIn('<a href="formats/weekend/"', nav)
        self.assertNotIn("akitashoten", nav)
        self.assertNotIn("formats/uniform/", nav)

    def test_top_html_has_no_nav_by_default(self):
        html = generate_site.generate_html(self.data)
        self.assertNotIn("publishers/", html)
        self.assertNotIn("formats/", html)

    def test_sitemap_extra_urls(self):
        xml = generate_site.generate_sitemap(
            self.data, ["https://book.netaful.jp/publishers/kadokawa/"]
        )
        self.assertIn("<loc>https://book.netaful.jp/publishers/kadokawa/</loc>", xml)
        xml_plain = generate_site.generate_sitemap(self.data)
        self.assertNotIn("publishers", xml_plain)
        self.assertEqual(xml_plain.count("<url>"), 1)


class RetainEntries(unittest.TestCase):
    def test_all_undetected_entries_are_kept(self):
        state = {
            "1": {"first_seen": "2026-01-01", "last_seen": "2026-01-10", "name": "古い企画"},
            "2": {"first_seen": "2026-07-01", "last_seen": "2026-07-20", "name": "最近の企画"},
            "3": {"first_seen": "2026-07-25", "last_seen": "2026-07-30", "name": "開催中"},
        }
        new_state = {"3": dict(state["3"], last_seen="2026-08-01")}
        kept = fetch_sales.merge_retained_entries(state, new_state)
        self.assertEqual(kept, 2)
        # 何日経っていても落とさない(開催履歴として保持する)
        self.assertEqual(new_state["1"]["name"], "古い企画")
        self.assertEqual(new_state["2"]["name"], "最近の企画")
        # 今回検出された企画は新しい方で上書き済みのまま
        self.assertEqual(new_state["3"]["last_seen"], "2026-08-01")

    def test_broken_dates_are_dropped(self):
        state = {
            "1": {"first_seen": "2026-01-01", "last_seen": "壊れた日付", "name": "A"},
            "2": {"first_seen": None, "last_seen": None, "name": "B"},
            "3": {"first_seen": "2026-01-01", "last_seen": None, "name": "C"},
        }
        new_state = {}
        kept = fetch_sales.merge_retained_entries(state, new_state)
        # last_seen が無ければ first_seen で判定する(従来どおり)
        self.assertEqual(kept, 1)
        self.assertIn("3", new_state)


if __name__ == "__main__":
    unittest.main()
