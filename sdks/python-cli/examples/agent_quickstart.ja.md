# エージェントのための omi-cli

> LLM 駆動のハーネス（Claude Code、Cursor、自作のボット）向けの実践ガイド。

## この CLI がエージェント向きな理由

* **JSON の契約が安定している。** `--json` を付けると stdout には正しい JSON 文書が
  *1 つだけ* 出力されます。進捗メッセージもスピナーも混ざりません。エラーは stderr に
  `{"error": "...", "detail": "..."}` の形で出ます。
* **終了コードが安定している。** `0` 成功 / `1` 利用法エラー / `2` 認証エラー /
  `3` サーバーエラー / `4` レート制限 / `5` 見つからない。エージェントは自然言語の
  エラー文を解析せずに、この値で分岐できます。
* **ヘッドレス環境で対話プロンプトが出ない。** 破壊的なコマンドには `--yes`（または `-y`）を
  付けます。`--api-key` を渡すか `OMI_API_KEY` を設定すれば、対話ログインを省略できます。
* **再試行に寛容。** `429` と `5xx` は、表に出す前にバックオフつきで再試行されます。

## 認証（人間が 1 回だけ行う）

ユーザーが Omi のウェブアプリ（`https://app.omi.me` → Developer → API Keys）で
開発者 API キーを取得し、次のどちらかを行います。

```bash
omi auth login                          # 対話式に貼り付け。キーはシェル履歴に残らない
# または
export OMI_API_KEY=omi_dev_...          # 一時的。コンテナ向き
```

## エージェントがよく行う 5 つの操作

### 1. メモリを読む

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. メモリを作る

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. 会話を読む

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. 未完了のアクションアイテムを読む

```bash
omi action-item list --json --open
```

### 5. アクションアイテムを完了にする

```bash
omi action-item complete --json a1b2c3d4
```

## ローカル Desktop API

Omi Desktop がローカル API を公開している場合、エージェントはクラウドの開発者 API を
使わずに、端末上の画面履歴・要約・SQL・タスクを照会できます。

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# または、一時的なセッションでは:
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

タスクの完了や削除は、ユーザーがはっきりそう求めたときだけ行います。

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` はスクリーンショットをディスクに書き、
スクリプト向けに stdout へは JSON を出力し続けます。スクリーンショットの ID は通常、
`local search-screen` か `screenshots` テーブルへの SQL で得られます。Desktop が
`screenshot_pending`、`screenshot_file_missing`、`screenshot_chunk_corrupted` のような
構造化された失敗を返した場合、JSON モードでは `reason`、`hint`、`screenshot_id` の
各フィールドが stderr に保たれるので、エージェントは古い ID で再試行するか、正確な
原因を報告できます。成功した出力は、画像認識ツールに渡す前に `file PATH` で確認してください。

## 実例: Python のエージェントループ

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """omi CLI を JSON モードで呼び出し、終了コードが 0 以外なら例外を投げる。"""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # JSON モードでは CLI が構造化エラーを stderr に出す:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# 未完了のアクションアイテムを全部読み、30 日より古いものを完了にする。
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## レート制限の扱い

メモリ: 120 回/時。会話: 25 回/時。一括作成: 15 回/時。

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # レート制限
    err = json.loads(result.stderr)
    # err["detail"] は次のような形: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## ヒント

* エージェントが複数の Omi アカウントを扱うなら `--profile <name>` を使います。
  プロファイルごとに認証情報と API base を持ちます。
* ローカルのバックエンドを試すときは `--api-base http://localhost:8080` を使います。
* `OMI_LOCAL_API_URL` と `OMI_LOCAL_TOKEN` で、その 1 回の実行だけプロファイルの
  Desktop API 設定を上書きできます。
* デバッグには `--verbose` を使います。`METHOD path → status (Ns)` を stderr に記録し、
  stdout には影響しないので、JSON モードは壊れません。
* 内容をパイプで会話に流し込むには `--text -` を使います。
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
