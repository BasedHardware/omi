# 畀 agent 用嘅 omi-cli

> 寫畀 LLM 驅動嘅 harness（Claude Code、Cursor、你自己嘅 bot）嘅實用指南。

## 點解呢個 CLI 對 agent 咁友善

* **穩定嘅 JSON 合約。** `--json` 只會向 stdout 輸出一個有效嘅 JSON 文件 ——
  淨係一個 JSON 文件 —— 冇進度訊息，冇載入動畫。錯誤會以
  `{"error": "...", "detail": "..."}` 嘅形式寫入 stderr。
* **穩定嘅離開碼。** `0` 成功 / `1` 用法錯誤 / `2` 認證失敗 / `3` 伺服器錯誤 /
  `4` 超出速率限制 / `5` 搵唔到。agent 可以直接依據呢啲碼分支處理，
  唔使解析自然語言錯誤訊息。
* **headless 環境下唔會出現互動提示。** 對破壞性指令傳入 `--yes`（或 `-y`）；
  傳入 `--api-key` 或者設定 `OMI_API_KEY` 就可以跳過互動登入。
* **寬容嘅重試行為。** 遇到 `429` 同 `5xx` 會先以退避方式重試，之後先至抛出錯誤。

## 認證（一次性，由人完成）

使用者從 Omi 網頁應用程式（`https://app.omi.me` → Developer → API Keys）取得
開發者 API 金鑰，然後二選一：

```bash
omi auth login                          # 互動式貼上；金鑰唔會入 shell 歷史
# 或者
export OMI_API_KEY=omi_dev_...          # 臨時生效，適合容器環境
```

## agent 最常做嘅五件事

### 1. 讀取記憶

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. 建立記憶

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. 讀取對話

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. 讀取未完成嘅行動項目

```bash
omi action-item list --json --open
```

### 5. 標記行動項目為完成

```bash
omi action-item complete --json a1b2c3d4
```

## 本機 Desktop API

當 Omi Desktop 開放佢嘅本機 API 之後，agent 就可以查詢裝置上嘅螢幕歷史、
回顧摘要、SQL 同任務，唔使經雲端開發 API：

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# 或者，臨時 session 用：
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

只喺使用者清楚要求嘅時候，先至完成或者刪除任務：

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` 會將螢幕截圖寫入磁碟，
同時照樣向 stdout 輸出 JSON 畀指令碼用。螢幕截圖 ID 通常嚟自
`local search-screen` 或者對 `screenshots` 表嘅 SQL 查詢。如果 Desktop 回傳
`screenshot_pending`、`screenshot_file_missing` 或 `screenshot_chunk_corrupted`
之類嘅結構化失敗，JSON 模式會喺 stderr 保留 `reason`、`hint` 同 `screenshot_id`
欄位，等 agent 可以用舊 ID 重試，或者報告確切嘅阻塞原因。
將成功輸出交畀視覺工具之前，先用 `file PATH` 驗證。

## 完整範例：Python agent 迴圈

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """以 JSON 模式呼叫 omi CLI，喺非成功結束碼時拋出例外。"""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI 喺 JSON 模式下會將結構化錯誤寫入 stderr：
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# 讀取所有未完成嘅行動項目，將超過 30 日嘅標記為完成。
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## 處理速率限制

記憶：120/小時。對話：25/小時。批量建立：15/小時。

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # 超出速率限制
    err = json.loads(result.stderr)
    # err["detail"] 大概係噉："Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## 貼士

* 如果你嘅 agent 要處理多個 Omi 帳戶，可以用 `--profile <name>`。每個
  profile 都有自己嘅憑證同 API 位址。
* 本機後端測試用 `--api-base http://localhost:8080`。
* 用 `OMI_LOCAL_API_URL` 同 `OMI_LOCAL_TOKEN` 喺單次執行度覆寫
  profile 嘅 Desktop API 設定。
* 除錯用 `--verbose` —— 佢會將 `METHOD path → status (Ns)` 記錄到 stderr，
  唔會影響 stdout，所以 JSON 模式依然有效。
* 想將內容經管道傳入對話，用 `--text -`：
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
