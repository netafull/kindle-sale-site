# Kindleセール速報サイト

セール中のKindle本をAmazon PA-API (Creators API) から取得し、静的サイトとして自動公開するツールです。GitHub Actionsで1時間ごとに自動更新されます。

## 仕組み

```
GitHub Actions (毎時実行)
  → scripts/fetch_sales.py   PA-APIから割引中のKindle本を取得 → data/sales.json
  → scripts/generate_site.py HTML + RSS を生成 → docs/
  → GitHub Pages にデプロイ
```

外部ライブラリ不要(Python標準ライブラリのみ)。サーバー・維持費も不要です。

## セットアップ

### 1. PA-APIの認証情報を用意する

[Amazonアソシエイト・セントラル](https://affiliate.amazon.co.jp/) → ツール → Product Advertising API から、**アクセスキー**と**シークレットキー**を取得します(アソシエイト登録済みで販売実績があることが条件)。**アソシエイトタグ**(例: `xxxx-22`)も控えておきます。

### 2. GitHubリポジトリを作成してpush

```sh
cd kindle-sale-site
git init && git add -A && git commit -m "initial commit"
gh repo create kindle-sale-site --public --source=. --push
```

### 3. Secretsを設定

リポジトリの Settings → Secrets and variables → Actions で以下を登録:

| Name | 値 |
|---|---|
| `PAAPI_ACCESS_KEY` | PA-APIアクセスキー |
| `PAAPI_SECRET_KEY` | PA-APIシークレットキー |
| `PAAPI_PARTNER_TAG` | `natafull-22` |

```sh
gh secret set PAAPI_PARTNER_TAG --body "natafull-22"
gh secret set PAAPI_ACCESS_KEY --body "<アクセスキー>"
gh secret set PAAPI_SECRET_KEY --body "<シークレットキー>"
```

### 4. GitHub Pagesを有効化

Settings → Pages → Source を **GitHub Actions** に設定。

### 5. 動作確認

Actions タブ →「Update Kindle sale site」→ Run workflow で手動実行。成功すると `https://<ユーザー名>.github.io/kindle-sale-site/` で公開されます。以降は毎時7分に自動更新されます。

## カスタマイズ (config.json)

- `site_title` / `site_description` / `site_url` — サイト情報。`site_url` はRSSに使うので公開URLに書き換えてください
- `min_saving_percent` — 掲載する最低割引率(デフォルト30%)
- `pages_per_genre` — ジャンルごとの取得ページ数(1ページ=10冊)。増やすとAPIリクエスト数も増えるので注意(PA-APIの無料枠は約8,640リクエスト/日)
- `genres` — ジャンルと Browse Node ID。**Node IDは要確認**: Amazonのカテゴリページ URL の `node=` パラメータから取得できます。`null` にするとKindleストア全体から検索します

## ローカルでのテスト

キーをコマンドに直接打つとシェル履歴に残るため、`.env` ファイル(gitignore済み)を使います。

```sh
cp .env.example .env   # .env を開いて実際のキーを記入する
set -a; source .env; set +a
python3 scripts/fetch_sales.py
python3 scripts/generate_site.py
open docs/index.html
```

## 注意事項

- PA-APIには「30日間APIから売上が発生しないとアクセス停止」等の利用条件があります
- 生成ページには景表法・アソシエイト規約対応の注意書き(価格は取得時点のもの/アソシエイト開示)を含めています
- セール「企画」単位(「○○フェア」など)の一覧はPA-APIでは取得できません。必要であれば特集ページの取得処理を追加する拡張が可能です
