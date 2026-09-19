# エージェント向け omi-cli ガイド

> LLM 駆動ハーネス（Claude Code、Cursor、自作ボットなど）向けの実践ガイド。

## CLI がエージェントに適している理由

* **安定した JSON コントラクト:** `--json` は標準出力（stdout）に有効な JSON ドキュメントを出力し、JSON ドキュメント*のみ*を出力します（進捗バーやスピナーなどは一切含みません）。エラーは標準エラー出力（stderr）に `{"error": "...", "detail": "..."}` として出力されます。
* **安定した終了コード:** `0` 成功 / `1` 構文・使用方法エラー / `2` 認証エラー / `3` サーバーエラー / `4` レート制限到達 / `5` 未検出。エージェントは自然言語のエラーを解析することなく、これらの終了コードに基づいて条件分岐できます。
* **ヘッドレス環境での対話型プロンプトなし:** 破壊的コマンドには `--yes`（または `-y`）を渡します。また、`--api-key` を渡すか `OMI_API_KEY` を設定することで対話型ログインをスキップできます。
* **寛容なリトライ動作:** `429` および `5xx` エラーは、表面化する前に指数バックオフを用いて自動的に再試行されます。

## 認証（ユーザーによる初回の1回のみ）

ユーザーは Omi Web アプリ（`https://app.omi.me` → Developer → API Keys）から開発者 API キーを取得し、以下のいずれかの方法で設定します:

```bash
omi auth login                          # 対話型で貼り付け（シェル履歴にキーが残りません）
# または
export OMI_API_KEY=omi_dev_...          # 一時的・コンテナ向け
```

## エージェントが最も頻繁に行う5つの操作

### 1. メモリを読み取る

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. メモリを作成する

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. 会話を読み取る

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. 未完了のアクションアイテムを読み取る

```bash
omi action-item list --json --open
```

### 5. アクションアイテムを完了としてマークする

```bash
omi action-item complete --json a1b2c3d4
```

## ローカルデスクトップ API

Omi Desktop がローカル API を公開している場合、エージェントはクラウドの開発者 API を使用せずに、端末上の画面履歴、要約、SQL、タスクを直接クエリできます:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# または一時的なセッションの場合:
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

タスクの完了または削除は、ユーザーが明示的に要求した場合にのみ実行してください:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` はスクリーンショットをディスクに書き込み、スクリプト用に標準出力へ JSON を出力します。スクリーンショット ID は通常、`local search-screen` または `screenshots` テーブルに対する SQL から取得します。Desktop が `screenshot_pending`、`screenshot_file_missing`、または `screenshot_chunk_corrupted` などの構造化された失敗を返した場合、JSON モードでは標準エラー出力（stderr）に `reason`、`hint`、および `screenshot_id` フィールドが保持されるため、エージェントは古い ID で再試行したり、正確な障害内容を報告したりできます。出力ファイルをビジョンツールに渡す前に、`file PATH` で検証してください。

## 実践例: Python エージェントループ

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """JSON モードで omi CLI を呼び出し、正常終了以外の終了コードで例外を発生させます。"""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI は JSON モード時に標準エラー出力へ構造化エラーを出力します:
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
if result.returncode == 4:                             # レート制限到達
    err = json.loads(result.stderr)
    # err["detail"] の例: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## ヒント

* エージェントが複数の Omi アカウントを使い分ける場合は `--profile <name>` を使用します。各プロファイルは独自の認証情報と API ベース URL を持ちます。
* ローカルバックエンドのテストには `--api-base http://localhost:8080` を使用します。
* 1回の実行でプロファイル固有のローカル Desktop API 設定を上書きするには、`OMI_LOCAL_API_URL` および `OMI_LOCAL_TOKEN` を使用します。
* デバッグには `--verbose` を使用します。これは標準出力に影響を与えずに `METHOD path → status (Ns)` を標準エラー出力へ記録するため、JSON モードの有効性を維持できます。
* 会話へコンテンツをパイプ経由で渡すには `--text -` を使用します:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
