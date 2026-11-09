"""トップの meta description と、商品画像の alt のテスト。

実行: python3 -m unittest discover -s tests
ネットワークには出ない(既存の data/ からHTMLをメモリ上で作るだけで、docs/ は書かない)。
"""

import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import generate_site  # noqa: E402


class SeoTest(unittest.TestCase):
    def page(self):
        data = json.loads((ROOT / "data" / "sales.json").read_text(encoding="utf-8"))
        return generate_site.generate_html(data)

    def test_book_image_alt_is_escaped_title(self):
        item = {"title": 'A&B "本" <1>', "price": 100, "url": "https://example.com/", "image": "https://example.com/a.jpg"}
        out = generate_site.render_book(item)
        self.assertIn('alt="A&amp;B &quot;本&quot; &lt;1&gt;"', out)

    def test_book_without_image_has_no_src_img(self):
        out = generate_site.render_book({"title": "T", "price": 100, "url": "https://example.com/"})
        self.assertNotIn("src=", out)

    def test_top_meta_description(self):
        html_text = self.page()
        desc = generate_site.CONFIG["meta_description"]
        self.assertTrue(80 <= len(desc) <= 110, len(desc))
        self.assertIn(f'<meta name="description" content="{generate_site.esc(desc)}">', html_text)
        self.assertIn(f'<meta property="og:description" content="{generate_site.esc(desc)}">', html_text)

    def test_logo_alt_stays_empty(self):
        # サイト名が隣に文字で出ているロゴは装飾扱いで alt="" のまま
        self.assertRegex(self.page(), r'<img src="assets/logo.png" alt="" ')
