# omi-cli 日本語クイックスタートガイド

> ターミナルから Omi と対話するための実践ガイド。人間にも AI エージェントにも対応しています。

`omi-cli` は、[Omi](https://omi.me) 開発者 API を操作するための公式コマンドラインインターフェースです。
Omi が保持する 4 つの主要リソース（メモリ、会話、アクションアイテム、目標）を効率的かつスクリプト可能に操作できます。

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **公式ドキュメント:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **ソースコード:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. インストール

推奨されるインストール方法は、依存関係が分離される `pipx` を使用することです。

```bash
# 推奨: pipx を使用したインストール
pipx install omi-cli

# または pip を使用
pip install omi-cli
```

> **重要: パッケージ名とコマンド名の違い**
> * インストールする Python パッケージ名は **`omi-cli`** です（単体の `omi` は別の無関係なパッケージです）。
> * インストール後にターミナルで実行するコマンド名は **`omi`** です。

インストール後、バージョンとヘルプを確認します。

```bash
omi --version
omi --help
```

---

## 2. 認証 (Authentication)

`omi-cli` は 2 つの認証方式をサポートしています。

| 認証方式 | 主な用途 | コマンド例 |
| :--- | :--- | :--- |
| **開発者 API キー (`omi_dev_*`)** | CI/CD、自動化スクリプト、AI エージェント | `omi auth login --api-key ...` または環境変数 |
| **ブラウザ OAuth (Google/Apple)** | 開発者のローカル PC / ラップトップ | `omi auth login --browser` |

### 対話型ログイン
オプションなしで実行すると、ブラウザログインまたは API キー入力の選択肢が表示されます。

```bash
omi auth login
# 1) Browser — Google または Apple アカウントでログイン（人間向け）
# 2) API key — app.omi.me で取得した開発者キーを貼り付け（エージェント/CI向け）
```

### ブラウザで直接ログイン
```bash
omi auth login --browser
```

### API キーを使用する場合
[app.omi.me](https://app.omi.me) の「Developer → API Keys」から開発者キーを取得し、設定します。

```bash
# コマンドで設定
omi auth login --api-key omi_dev_...

# または環境変数で設定 (CI/CD やコンテナ環境に最適)
export OMI_API_KEY=omi_dev_...
```

### 認証状態の確認
* `omi auth status`: ローカルに保存されている認証プロファイル、マスクされたトークン、有効期限を表示します（オフラインで動作）。
* `omi auth whoami`: Omi サーバーに実際に検証リクエストを送信し、認証情報が有効であることを確認します（ネットワーク接続が必要）。

```bash
omi auth status
omi auth whoami
```

ログアウトする場合は以下を実行します。
```bash
omi auth logout
```

---

## 3. 基本的な使い方

Omi の 4 つのコアリソースを一覧表示・操作できます。

### メモリ (Memories)
システムが学習した事実や知識を管理します。

```bash
# メモリ一覧の取得
omi memory list

# 新しいメモリの作成
omi memory create "ユーザーはダークモードを好む" --category lifestyle

# 特定のメモリの詳細表示
omi memory get <MEMORY_ID>
```

### 会話 (Conversations)
ウェアラブルデバイスやアプリから取得された音声・テキストの会話履歴です。

```bash
# 最近の会話 5 件を取得
omi conversation list --limit 5

# 会話の詳細と文字起こしを表示
omi conversation get <CONVERSATION_ID> --include-transcript
```

### アクションアイテム (Action Items)
会話から自動抽出されたタスクやフォローアップ項目です。

```bash
# 未完了のアクションアイテムのみ一覧表示
omi action-item list --open

# アクションアイテムを完了としてマーク
omi action-item complete <ACTION_ITEM_ID>
```

### 目標 (Goals)
進捗を追跡している目標を管理します。

```bash
# 目標の一覧表示
omi goal list
```

---

## 4. スクリプト処理と JSON 出力 (`--json`)

`omi-cli` は JSON 出力にネイティブ対応しています。`jq` や Python スクリプトと連携する際は、**グローバルオプション**としてサブコマンドの前に `--json` を指定します。

```bash
# メモリ一覧を JSON で取得し、ID と内容を抽出
omi --json memory list | jq '.[] | {id, content, category}'

# 最近の会話のタイトル一覧を取得
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# 未完了アクションアイテムの一覧
omi --json action-item list --open | jq '.'
```

> **ポイント:** `--json` は必ず `memory` や `conversation` などの**サブコマンドより前**に配置してください。
> * 正しい例: `omi --json memory list`
> * 誤った例: `omi memory list --json`

---

## 5. 終了コード (Exit Codes)

スクリプトや CI で分岐処理を行うために、明確な終了コードが定義されています。

| 終了コード | 意味 | 詳細 |
| :---: | :--- | :--- |
| `0` | 成功 (Success) | コマンドが正常に完了 |
| `1` | コマンド利用法エラー (Usage Error) | 不正なフラグ、引数の不足など |
| `2` | 認証エラー (Auth Error) | 未ログイン、無効な API キーまたはトークン期限切れ |
| `3` | サーバーエラー (Server Error) | 5xx 応答、接続タイムアウト、ネットワーク接続障害 |
| `4` | レート制限 (Rate Limited) | 429 Too Many Requests |
| `5` | リソース未検出 (Not Found) | 404 Not Found (指定された ID が存在しない) |

---

## 6. シェル別環境変数設定の例

### Bash / Zsh (Linux / macOS)
```bash
# API キーの設定
export OMI_API_KEY="omi_dev_your_actual_key_here"

# 一覧取得
omi --json memory list --limit 10
```

### PowerShell (Windows)
```powershell
# API キーの設定
$env:OMI_API_KEY = "omi_dev_your_actual_key_here"

# PowerShell での JSON パース例
(omi --json memory list | ConvertFrom-Json) | Select-Object id, content
```

---

## 7. ローカル Desktop API との連携

Omi Desktop アプリが起動している環境では、クラウド API を経由せずにローカル画面履歴や SQL データベースを直接照会できます。

```bash
# ローカル API の接続先を設定
omi local configure --url http://127.0.0.1:47778 --token YOUR_DESKTOP_TOKEN

# 接続ステータスの確認
omi --json local status

# 画面履歴の検索
omi --json local search-screen "料金プラン" --days 7 --app Safari
```

---

## 8. プロファイル機能 (Profiles)

複数のアカウントや環境（本番環境、検証環境など）を使い分ける場合、`--profile` オプションを使用します。設定は `~/.omi/config.toml` に保存されます。

```bash
# 個人用プロファイルでログイン
omi --profile personal auth login

# 開発・仕事用プロファイルでログイン
omi --profile work auth login

# プロファイルを切り替えて実行
omi --profile work memory list
```
