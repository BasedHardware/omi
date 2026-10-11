# omi-cli 日本語クイックスタートガイド

> ターミナルから Omi を操作するための実践ガイド。人間にも AI エージェントにも使えます。

`omi-cli` は [Omi](https://omi.me) 開発者 API の公式コマンドラインクライアントです。
Omi が持つ 4 つの主要リソース（メモリ、会話、アクションアイテム、目標）に、
素早く・スクリプトから扱える形でアクセスできます。

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **公式ドキュメント:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **ソースコード:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. インストール

推奨は `pipx` です。ツールが独立した環境にインストールされるので、
依存関係が手元のプロジェクトと衝突しません。

```bash
# 推奨: pipx でインストール
pipx install omi-cli

# または pip で
pip install omi-cli
```

> **重要: パッケージ名とコマンド名は別物です。**
> * インストールするパッケージは **`omi-cli`** です（`omi` という別パッケージは無関係の別プロジェクトです）。
> * インストール後に実行するコマンドは **`omi`** です。

動作確認:

```bash
omi --version
omi --help
```

---

## 2. 認証

`omi-cli` は 2 つのログイン方法に対応しています。

| 方法 | 向いている用途 | コマンド |
| :--- | :--- | :--- |
| **開発者キー (`omi_dev_*`)** | CI/CD、スクリプト、AI エージェント | `omi auth login --api-key ...` または環境変数 |
| **ブラウザログイン (Google/Apple)** | 自分の PC での作業 | `omi auth login --browser` |

### 対話型ログイン

オプションなしで実行すると、どちらの方法を使うか聞かれます。

```bash
omi auth login
# 1) Browser — Google または Apple でログイン（人間向け）
# 2) API key — app.omi.me で取得した開発者キーを貼り付け（エージェント・CI 向け）
```

キーを選んだ場合、入力は隠されるのでターミナルの履歴にキーが残りません。

### ブラウザで直接ログイン

```bash
omi auth login --browser
```

### 開発者キーでログイン

キーは [app.omi.me](https://app.omi.me) の **Developer → API Keys** で取得します。

```bash
# キーを設定ファイルに保存する
omi auth login --api-key omi_dev_...

# または環境変数で渡す — CI/CD やコンテナではこちらを推奨
export OMI_API_KEY=omi_dev_...
```

環境変数 `OMI_API_KEY` は、**使用中のプロファイルにキーが保存されていないとき**に使われます。
コンテナではディスクに何も書かずに済みます。
プロファイルに既にキーがある場合は、そちらが環境変数より優先されます。

### ログイン状態の確認

次の 2 つのコマンドは答える質問が違うので、混同しないでください。

* `omi auth status` — **ローカルに保存されている**内容: プロファイル名、マスクされたキー、有効期限。
  ネットワークなしで動きます。
* `omi auth whoami` — **Omi サーバーに問い合わせ**て、キーが実際に受け付けられるか確認します。
  ネットワークが必要です。

```bash
omi auth status    # ローカル確認（オフライン可）
omi auth whoami    # サーバー側で確認
```

期限が近いトークンをログインし直さずに更新するコマンドがありますが、これは
**ブラウザ/OAuth セッションにだけ**使えます。API キー（`omi_dev_*`）で認証した
プロファイルでは、`omi auth refresh` は「更新するトークンがない」という利用法エラー
（終了コード 1）になります。必要なら Omi のウェブアプリでキーを作り直してください。

```bash
omi auth refresh
```

ログアウト:

```bash
omi auth logout
```

---

## 3. 基本コマンド

### メモリ (memories)

システムがあなたについて覚えている事実や知識です。

```bash
# メモリの一覧
omi memory list

# 新しく作る
omi memory create "ユーザーはダークモードを好む" --category lifestyle

# 特定のメモリを見る
omi memory get <MEMORY_ID>
```

### 会話 (conversations)

デバイスやアプリから届いた音声・テキストの履歴です。

```bash
# 最近の会話 5 件
omi conversation list --limit 5

# 文字起こしつきで 1 件を丸ごと見る
omi conversation get <CONVERSATION_ID> --include-transcript
```

### アクションアイテム (action items)

Omi が会話から見つけたタスクです。

```bash
# 未完了のものだけ
omi action-item list --open

# 完了にする
omi action-item complete <ACTION_ITEM_ID>
```

### 目標 (goals)

```bash
# 目標の一覧
omi goal list

# 進捗の値を記録する（目標 ID と値の **両方** が必要）
omi goal progress <GOAL_ID> 25

# 変更履歴
omi goal history <GOAL_ID>
```

---

## 自分の言葉で質問する (`ask`)

独立したトップレベルのコマンドです。自然な言葉で質問すると、
あなた自身の会話をもとに答えが作られます。

```bash
omi ask "引っ越しについて何を決めたっけ"
omi --json ask "今週中に終わらせると約束したタスクは何"
```

---

## 4. JSON とスクリプト (`--json`)

`omi-cli` は機械で読める JSON を出力できます。`--json` は**グローバル**オプションなので、
サブコマンドの**前**に置きます。

```bash
# メモリ: id・本文・カテゴリを取り出す
omi --json memory list | jq '.[] | {id, content, category}'

# 最近の会話のタイトル
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# 未完了のアクションアイテム
omi --json action-item list --open | jq '.'
```

> **よくある間違い。** `--json` はサブコマンドの前です。後ろではありません。
> * 正しい: `omi --json memory list`
> * 誤り: `omi memory list --json`

`--json` モードでは、stdout には JSON そのもの以外は一切出力されません。
スクリプトはこれを前提にして構いません。

---

## 5. 終了コード

終了コードは固定です。スクリプトや CI はこの値で分岐できます。

| コード | 意味 | いつ |
| :---: | :--- | :--- |
| `0` | 成功 | コマンドが正常に終わった |
| `1` | 利用法エラー | omi-cli 自身の検証（例: `--browser` と `--api-key` の同時指定、ログイン方法の選択が不正、stdin が空） |
| `2` | 認証エラー | 未ログイン、キーが無効または期限切れ |
| `3` | サーバーエラー | 5xx 応答、タイムアウト、接続できない |
| `4` | リクエスト過多 | 429 Too Many Requests |
| `5` | 見つからない | 404、その ID が存在しない |

> **補足。** 未知のオプションや引数不足は Click が先に捕まえるため、終了コードは `2` になります。

Bash での判定例:

```bash
if omi --json auth whoami > /dev/null 2>&1; then
  echo "キーは有効です"
else
  code=$?
  [ "$code" -eq 2 ] && echo "ログインし直してください"
  [ "$code" -eq 3 ] && echo "サーバーが落ちています。あとで再試行してください"
fi
```

---

## 6. 環境変数

### Bash / Zsh (Linux, macOS)

```bash
export OMI_API_KEY="omi_dev_あなたのキー"

omi --json memory list --limit 10
```

新しいセッションでもキーを読み込ませたい場合は、この行を `~/.bashrc` か `~/.zshrc` に追加します。

### PowerShell (Windows)

```powershell
$env:OMI_API_KEY = "omi_dev_あなたのキー"

# PowerShell で JSON をパースする
(omi --json memory list | ConvertFrom-Json) | Select-Object id, content
```

恒久的に設定する場合:

```powershell
[Environment]::SetEnvironmentVariable("OMI_API_KEY", "omi_dev_あなたのキー", "User")
```

---

## 7. ローカルの Omi Desktop アプリ

Omi のデスクトップアプリが起動していれば、一部のデータはクラウドを経由せずに
直接読めます。

```bash
# ローカル API の接続先を登録する
omi local configure --url http://127.0.0.1:47778 --token あなたのトークン

# 応答するか確認する
omi --json local status

# 画面履歴を検索する
omi --json local search-screen "料金プラン" --days 7 --app Safari

# ID を指定してスクリーンショットを保存する
omi --json local screenshot 123 --output /tmp/omi-shot.jpg

# ローカル DB に任意の SQL を投げる
omi --json local sql "SELECT appName, COUNT(*) FROM screenshots GROUP BY appName"
```

おすすめの手順: まず `local status`、次に `local tools` で使えるツールとその引数を確認し、
それから実際の呼び出しに進みます。

---

## 8. プロファイル

複数のアカウントや環境を使い分けるなら、プロファイルで分けます。
設定は `~/.omi/config.toml` に保存されます。

```bash
# 個人用プロファイルでログイン
omi --profile personal auth login

# 仕事用プロファイルでログイン
omi --profile work auth login

# 指定したプロファイルでコマンドを実行する
omi --profile work memory list
```

使われるプロファイルは次の順で決まります。`--profile`（または `-p`）オプションが最優先。
なければ環境変数 `OMI_PROFILE`。なければ `~/.omi/config.toml` に設定された使用中のプロファイル。
最後の手段として `default` プロファイルです。

設定そのものを見る・変える:

```bash
# いま設定されている内容
omi config show

# 設定ファイルの場所
omi config path

# 値を変える
omi config set api_base https://api.omi.me
```

---

## 9. 次のステップ

* [`agent_quickstart.ja.md`](./agent_quickstart.ja.md) — `omi-cli` を AI エージェントにつなぐ方法（日本語）。
* [`agent_quickstart.md`](./agent_quickstart.md) — 同じ内容の英語版。
* [`shell_examples.sh`](./shell_examples.sh) — そのまま使えるシェルの例。
* [Omi ドキュメント](https://docs.omi.me/doc/developer/cli/introduction) — コマンドの完全なリファレンス。
