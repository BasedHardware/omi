# omi-cli（日本語）

[English README](README.md) · [Русский: быстрый старт](README.ru.md) · [日本語クイックスタート](examples/quickstart.ja.md)

> ターミナルから Omi と話す。人間にも**エージェントにも**使えるように設計。

`omi-cli` は [Omi](https://omi.me) 開発者 API のコマンドラインインターフェースです。
Omi があなたについて持っている 4 つの主要な対象に対して、範囲を絞った
エージェント向きの動詞を提供します。

* **メモリ** — システムがあなたについて知っている事実や学び
* **会話** — 取り込んで処理された音声・テキストのやりとり
* **アクションアイテム** — タスクとフォローアップ
* **目標** — 追跡している進捗の指標

意図的に小さく、スクリプトから扱いやすく、JSON を第一に作られています。Omi を
シェルのパイプライン、CI ジョブ、エージェントのハーネス、あるいは自分だけの自動化に
つなぐのに必要なものが揃っています。

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **ドキュメント:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **ソース:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

## インストール

```bash
pipx install omi-cli            # 推奨 — 隔離された環境にインストール
# または
pip install omi-cli
```

インストール後、`$PATH` 上のコマンド名は `omi` です。

```bash
omi --version
omi --help
```

> PyPI での配布名は `omi-cli` です（`omi` という名前は無関係の別パッケージが
> 使っています）。コンソールのコマンド名はどちらにせよ `omi` です。

## クイックスタート

```bash
# 1. ログインする。フラグなしで実行すると、omi-cli が認証方法を尋ねます:
omi auth login
# → 1) Browser — Google または Apple でサインイン（人間向けの推奨）
# → 2) API key — app.omi.me の開発者キーを貼り付け（エージェント・CI 向けの推奨）

# 2. 使い始める:
omi memory list
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

どのコマンドにも `--json` を付けると（グローバルフラグなので動詞の前に置きます）、
`jq` やエージェントのハーネスなどでそのまま使える機械可読の出力になります。

```bash
omi --json memory list | jq '.[] | {id, content}'
```

通常の表示では、返ってきたテキストは角括弧や `:warning:` のような絵文字風の
コードも含めてそのまま表示されます。装飾は表のレイアウトに適用され、メモリや会話の
中身には適用されません。
列があらかじめ決まっていない表は、すべての行のフィールドを初出順に含めます。

> 他の言語のガイドは [`examples/README.md`](examples/README.md) にまとまっています。

## 認証

認証方法は 2 つあり、どちらも完全に対応しています。

| 方法                          | 向いている用途                                   | 使い方                                      |
| ----------------------------- | ------------------------------------------------ | ------------------------------------------- |
| 開発者 API キー (`omi_dev_*`) | エージェント、CI、ヘッドレス、権限を絞りたいとき | `omi auth login --api-key ...` または環境変数 |
| Firebase OAuth (Google/Apple) | ノート PC 上の人間                               | `omi auth login --browser`                  |

ブラウザ方式は、既定のブラウザを OAuth のために開き、localhost のコールバックで
コードを受け取り、Firebase の ID トークンとリフレッシュトークンを保存します。
ID トークンは期限が近づくと各リクエストの前に自動で更新されるので、意識する必要は
ありません。

```bash
omi auth login                  # 対話式の選択（ブラウザまたはキー）
omi auth login --browser        # OAuth を強制（既定のプロバイダ: google）
omi auth login --browser --provider apple
omi auth login --api-key K      # API キー方式を強制
omi auth login < key.txt        # パイプでキーを渡す。CI で便利
omi auth status                 # プロファイル＋マスクされた認証情報＋有効期限を表示
omi auth whoami                 # サーバーに問い合わせて認証情報が有効か確認
omi auth refresh                # Firebase の更新を強制（API キーでは何もしない）
omi auth logout                 # 認証情報を消去
```

API キーでのログインは、保存済みの認証情報を置き換える前に検証されます。
検証が HTTP 401 または 403 で拒否された場合、既存のプロファイルと使用中プロファイルの
選択はそのまま変わりません。その他の HTTP エラーでは、従来どおり保存して警告します。
通信の失敗では保存済みの認証情報は変わりません。ブラウザ OAuth は別のフローです。

環境変数 `OMI_API_KEY` を設定すれば、ディスク上の設定を一切使わずに済みます。
コンテナや CI で便利です。

```bash
export OMI_API_KEY=omi_dev_...
omi memory list
```

## プロファイル

状態は `~/.omi/config.toml` にあります（`$OMI_CONFIG` で上書き可能）。このファイルは
1 つ以上の名前付きプロファイルを持ち、それぞれが独自の認証方法と API base を持ちます。
設定を保存するとき、ルートとプロファイルの両方の階層で未知の設定は保持されるので、
既知の設定を編集しても、より新しいクライアントの拡張が消えることはありません。
`--profile` で切り替えます。

```bash
omi config profile use work
omi auth login                  # 使用中のプロファイル（work）にログイン
omi --profile personal memory list
```

よく使う設定:

```bash
omi config show
omi config path
omi config set api_base https://api.staging.omi.me
omi config set local_api_url http://127.0.0.1:47778
omi config set local_token ...
omi config profile list
omi config profile delete old-account --yes
```

## ローカルの Omi Desktop API

`omi local` は、起動中の Omi Desktop のローカル API と通信します。使用中の
プロファイルに一度設定するか、一時的なエージェントセッションでは環境変数を使います。

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
export OMI_LOCAL_API_URL=http://127.0.0.1:47778
export OMI_LOCAL_TOKEN=...
```

よく使うローカルツール:

```bash
omi --json local status
omi --json local tools
omi --json local call search_screen_history --args-json '{"query":"pricing page","days":7}'
omi --json local search-screen "pricing page" --days 7 --app Safari
omi --json local screenshot 123 --output /tmp/omi-shot.jpg
omi --json local recap --days-ago 1
omi --json local sql "SELECT appName, COUNT(*) FROM screenshots GROUP BY appName"
omi --json local task search "taxes" --include-completed
```

エージェントによる画面履歴の手順:

1. `omi --json local status` で利用可否を確認し、`screen_history_available`、
   `screenshot_count`、`indexed_screenshot_count` を見る。
2. `omi --json local tools` でツールのスキーマを調べる。
3. `omi --json local search-screen "query" --days 7` で OCR・画面履歴を検索する。
   アプリやウィンドウで絞り込みたいときは `screenshots` に対して SQL を直接実行する。
4. 返ってきた `screenshot_id` を
   `omi --json local screenshot <id> --output /tmp/omi-shot.jpg` に渡す。
5. 画像認識ツールに渡す前に、`file /tmp/omi-shot.jpg` などでファイルを確認する。

意味検索で結果が 0 件のとき、JSON モードではアプリ名・ウィンドウタイトル・OCR テキストに
対する部分文字列の検索も試みます。この代替検索では、クエリや `--app` フィルタの `%` と
`_` は SQL のワイルドカードではなく、その文字そのものに一致します。

画像が取得できない場合、JSON モードのエラーには Desktop の構造化フィールド
（`status_code`、`error`、`reason`、`hint`、`screenshot_id` など）が保たれます。
たとえば `screenshot_pending` は、そのフレームがまだ録画中のセグメントにあることを
意味します。少し待って再試行するか、検索結果から古いスクリーンショット ID を選んでください。

タスクへの書き込みは、ユーザーがその変更をはっきり求めたときだけ実行してください。

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

### 画面の完全一致検索にも指定した期間を適用する

`omi --json local search-screen` のアプリ名・ウィンドウ名・OCR による完全一致のフォールバックも、
セマンティック検索と同じ `--days` のローリング期間に従います。

## コマンド一覧

全体の木構造（最新版は `omi --help` で確認できます）:

```text
omi
├── auth
│   ├── login [--browser] [--api-key KEY]
│   ├── logout
│   ├── status
│   ├── whoami
│   └── refresh
├── config
│   ├── show
│   ├── path
│   ├── set <key> <value>
│   └── profile
│       ├── list
│       ├── use <name>
│       └── delete <name>
├── memory
│   ├── list [--limit N] [--offset N] [--categories ...]
│   ├── get <id>
│   ├── create <content> [--category ...] [--visibility ...] [--tag ...]
│   ├── update <id> [--content ...] [--category ...] [--visibility ...] [--tag ...]
│   └── delete <id> [-y]
├── conversation
│   ├── list [--limit N] [--start-date ...] [--end-date ...] [--include-transcript]
│   ├── get <id> [--include-transcript]
│   ├── create [--text ...] [--text-source ...] [...]
│   ├── from-segments <file.json> [--source ...]
│   ├── update <id> [--title ...] [--discarded/--no-discarded]
│   └── delete <id> [-y]
├── action-item
│   ├── list [--completed/--open] [--conversation-id ...] [...]
│   ├── get <id>
│   ├── create <description> [--due-at ...]
│   ├── update <id> [--description ...] [--completed/--open] [--due-at ...]
│   ├── complete <id>
│   └── delete <id> [-y]
├── local
│   ├── configure --url URL --token TOKEN
│   ├── status
│   ├── tools
│   ├── call <tool> [--args-json JSON]
│   ├── search-screen <query> [--days N] [--app NAME]
│   ├── screenshot <id> [--output PATH]
│   ├── recap [--days-ago N]
│   ├── sql <query>
│   └── task
│       ├── search <query> [--include-completed]
│       ├── complete <id>
│       └── delete <id> [-y]
└── goal
    ├── list [--limit N] [--include-inactive]
    ├── get <id>
    ├── create <title> --target N [--type ...] [--current N] [--unit ...]
    ├── update <id> [--unit ... | --clear-unit] [...]
    ├── progress <id> <value>
    ├── history <id> [--days N]
    └── delete <id> [-y]
```

`conversation from-segments` は、システムの既定の文字コードに関係なく、JSON ファイルを
UTF-8（BOM の有無を問わない）、UTF-16、UTF-32 として読みます。
文字起こしの JSON と `local call --args-json` は、いずれも有限の数値を要求します。
`NaN`、`Infinity`、`-Infinity`、および Python の有限浮動小数点の範囲外の値は、
API クライアントを開く前に拒否されます。`--json` モードでは、これらの入力エラーは
stderr に JSON として報告されます。

`action-item get` は、ID が見つかるか結果の末尾に達するまで API のページを順に
検索します。先頭 1,000 件より後の項目も取得できますが、古い項目や存在しない項目を
探す場合は、複数回の API リクエストが必要になることがあります。

## グローバルフラグ

```text
--json                 stdout に JSON を出力（機械可読・エージェント向き）。
--profile, -p NAME     特定のプロファイルを使う。
--api-base URL         API base の URL を上書きする。
--verbose, -v          HTTP 通信を stderr に記録する。
--no-color             色付き出力を無効にする（$NO_COLOR も尊重）。
--version              バージョンを表示する。
--help                 文脈に応じたヘルプを表示する。
```

## 終了コード（安定した契約）

```text
0  成功
1  利用法エラー（不正なフラグ、引数不足、検証エラー）
2  認証エラー（認証情報なし、トークン期限切れ、権限不足）
3  サーバーエラー（5xx、接続失敗）
4  レート制限（429）— 再試行を推奨
5  見つからない（404）
```

## エージェント向け

この CLI は、ラッパーなしで LLM が使えるように作られています。

* `--json` は stdout に正しい JSON を返します。JSON モードでは stdout に他の何も
  書き込まれません（エラーは `{"error": "...", "detail": "..."}` として stderr に出ます）。
* 機械可読なバージョン情報（`{"version": "..."}`）には `omi --json version` を使います。
  `omi version` と即時評価される `omi --version` フラグは、プレーンテキストの出力のままです。
* 安定した終了コード（上記）により、エージェントは再試行できるエラーと
  そうでないエラーを区別できます。
* リソースの `delete --yes` が成功した場合、JSON モードでは API の応答がそのまま
  出力されます。本文のない成功応答は JSON の `null` として出力されます。
* レート制限のエラーはメッセージに `Retry-After` の待ち時間を含み、ポリシー名
  （`dev:conversations` など）も示すので、エージェントは賢く待てます。
* 環境変数 `OMI_API_KEY` と `OMI_API_BASE` は、事前の `auth login` なしで動きます。
* `OMI_LOCAL_API_URL` と `OMI_LOCAL_TOKEN` は、`omi local` で使うプロファイル内の
  Desktop API 設定を上書きします。

具体例は [`examples/agent_quickstart.ja.md`](examples/agent_quickstart.ja.md)
（英語版: [`examples/agent_quickstart.md`](examples/agent_quickstart.md)）を参照してください。

## レート制限

開発者 API はポリシーごとに 1 時間あたりの上限を設けています。

| ポリシー               | 上限        |
| ---------------------- | ----------- |
| `dev:conversations`    | 25/時間     |
| `dev:memories`         | 120/時間    |
| `dev:memories_batch`   | 15/時間     |

CLI は `429` を指数バックオフで自動的に再試行し、サーバーの `Retry-After` の
ヒントがあればそれに従います。再試行を使い切ると終了コード `4` になり、
どれだけ待てばよいかを示すメッセージが出ます。

POST と PATCH のリクエストは、曖昧な通信失敗やサーバーエラーの後に自動では
再送されません。サーバー側で既に書き込みが適用されている可能性があるためです。
これらの失敗は終了コード `3` と `outcome unknown` のメッセージを返します。
再試行する前にリソースの状態を確認してください。接続確立の失敗とレート制限の応答は
引き続き再試行され、読み取りの再試行も変わりません。

## アクションアイテムの期限を解除する

`omi action-item update ID --clear-due-at` は、明示的な null の PATCH フィールドに対応した
サーバーで期限を削除します（バックエンド側の修正 #13029）。`--due-at` と同時には使えません。
どちらも省略すると期限は変更されません。

## 日時オプション

会話とアクションアイテムの日時オプションは、`Z`（UTC）付きの ISO タイムスタンプ、
数値オフセット、および省略可能な小数秒を受け付けます。例:
`--due-at 2026-09-08T12:30:00Z` や
`--start-date 2026-09-08T12:30:00.123456+05:30`。オフセットは API リクエストに
そのまま保たれます。日付のみの値やオフセットのないタイムスタンプも引き続き使えます。
それらの入力に CLI がタイムゾーンを割り当てることはありません。

## 開発

```bash
# 開発用 extras 付きの編集可能インストール
pip install -e .[dev]

# テストスイートを実行
pytest -q

# Lint
black --check --line-length 120 --skip-string-normalization sdks/python-cli/
mypy omi_cli

# wheel と sdist をビルド（アップロードもタグ付けもしない）
bash release.sh --build-only
```

## ライセンス

MIT — [`LICENSE`](LICENSE) を参照。
