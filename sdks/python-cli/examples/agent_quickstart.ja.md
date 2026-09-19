# エージェント向け omi-cli

> LLM駆動ハーネス（Claude Code、Cursor、独自のボット）向けの実践ガイド。

## CLIがエージェントに適している理由

* **安定したJSONコントラクト。** `--json` は標準出力（stdout）に有効なJSONドキュメント**のみ**を出力します。進捗メッセージやスピナーは一切ありません。エラーは
  `{"error": "...", "detail": "..."}` の形式で標準エラー出力（stderr）に出力されます。
* **安定した終了コード。** `0` 正常終了 / `1` 使用方法エラー / `2` 認証エラー / `3` サーバーエラー / `4` レート制限 / `5` 見つかりません。エージェントは自然言語エラーをパースすることなく、終了コードで直接分岐処理を行えます。
* **ヘッドレス環境での対話型プロンプトなし。** 破壊的コマンドには `--yes`（または `-y`）を渡します。`--api-key` を渡すか `OMI_API_KEY` を設定することで対話型ログインをスキップできます。
* **寛容なリトライ動作。** `429` や `5xx` はエラーを返す前に指数バックオフ付きで自動リトライされます。

## 認証（人間が一度だけ実行）

ユーザーはOmiウェブアプリ
（`https://app.omi.me` → Developer → API Keys）から開発者APIキーを取得し、以下のいずれかを実行します：

```bash
omi auth login                          # 対話型貼り付け。キーはシェルの履歴に残りません
# または
export OMI_API_KEY=omi_dev_...          # 一時的。コンテナ環境に最適
```

## エージェントが最も頻繁に行う5つの操作

### 1. メモリの読み取り

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. メモリの作成

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. 会話の読み取り

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. 未完了のアクションアイテムの読み取り

```bash
omi action-item list --json --open
```

### 5. アクションアイテムを完了としてマーク

```bash
omi action-item complete --json a1b2c3d4
```

## ローカル Desktop API

Omi DesktopがローカルAPIを公開している場合、エージェントはクラウド開発APIを使用せずに、デバイス上の画面履歴、要約、SQL、タスクをクエリできます：

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# または一時セッションの場合：
export OMI_LOCAL_API_URL=http://127.0.0.1:47778
export OMI_LOCAL_TOKEN=...

omi --json local status
omi --json local tools
omi --json local call search_screen_history --args-json '{"query":"pricing page","days":7}'
omi --json local search-screen "pricing page" --days 7 --app Safari
omi --json local screenshot 123 --output /tmp/omi-shot.jpg
omi --json local sql "SELECT COUNT(*) AS screenshots FROM screenshots"
omi --json local task search "taxes" --include-completed
```

ユーザーから明確に指示された場合のみ、タスクの完了または削除を行ってください：

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` はスクリーンショットをディスクに書き込み、スクリプト用に標準出力へJSONを出力し続けます。スクリーンショットIDは通常、`local search-screen` または `screenshots` テーブルに対するSQLから取得します。Desktopが `screenshot_pending`、`screenshot_file_missing`、`screenshot_chunk_corrupted` などの構造化された失敗を返した場合、JSONモードは `reason`、`hint`、`screenshot_id` フィールドを標準エラー出力（stderr）に保持するため、エージェントはより古いIDでリトライするか、正確な障害原因を報告できます。出力が成功した場合は、ビジョンツールに渡す前に `file PATH` で検証してください。

## 実践例：Pythonエージェントループ

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """JSONモードでomi CLIを呼び出し、失敗の終了コードで例外を発生させます。"""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLIはJSONモード時に構造化エラーを標準エラー出力に出力します：
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# すべての未完了アクションアイテムを読み取り、30日以上前のものを完了としてマークします。
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## レート制限の処理

メモリ: 120回/時。会話: 25回/時。一括作成: 15回/時。

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # レート制限に到達
    err = json.loads(result.stderr)
    # err["detail"] の形式例: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## ヒント

* エージェントが複数のOmiアカウントを操作する場合は、`--profile <name>` を使用してください。各プロファイルは独自の認証情報とAPIベースを持ちます。
* ローカルバックエンドのテストには `--api-base http://localhost:8080` を使用してください。
* 1回の実行でプロファイル固有のDesktop API設定を上書きするには、`OMI_LOCAL_API_URL` と `OMI_LOCAL_TOKEN` を使用してください。
* デバッグには `--verbose` を使用してください。標準出力に影響を与えることなく、`METHOD path → status (Ns)` を標準エラー出力に記録するため、JSONモードの整合性が保たれます。
* 会話にコンテンツをパイプで渡す場合は、`--text -` を使用します：
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
