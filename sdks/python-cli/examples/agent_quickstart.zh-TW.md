# 給 Agent 的 omi-cli

> 給 LLM 驅動工作流程（Claude Code、Cursor、你自己的機器人）的實用指南。

## 為什麼這個 CLI 對 Agent 友善

* **穩定的 JSON 契約。** `--json` 只會向標準輸出（stdout）輸出一份合法的 JSON
  文件 —— 沒有進度訊息，沒有載入動畫。錯誤會以
  `{"error": "...", "detail": "..."}` 的形式寫入標準錯誤（stderr）。
* **穩定的離開碼。** `0` 成功 / `1` 用法錯誤 / `2` 認證失敗 /
  `3` 伺服器錯誤 / `4` 觸發速率限制 / `5` 找不到。Agent 可以直接據此
  分支處理，不必解析自然語言錯誤訊息。
* **無頭環境下不會出現互動式提示。** 對破壞性指令傳入 `--yes`（或 `-y`）；
  傳入 `--api-key` 或設定 `OMI_API_KEY` 即可跳過互動式登入。
* **寬容的重試行為。** 遇到 `429` 和 `5xx` 時會先退避重試，再把錯誤抛出。

## 認證（由人類一次性完成）

使用者從 Omi 網頁應用程式取得開發者 API 金鑰
（`https://app.omi.me` → Developer → API Keys），然後二選一：

```bash
omi auth login                          # 互動式貼上；金鑰不會進入 shell 歷史紀錄
# 或
export OMI_API_KEY=omi_dev_...          # 臨時生效，適合容器環境
```

## Agent 最常做的五件事

### 1. 讀取記憶

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. 建立一則記憶

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. 讀取對話

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. 讀取未完成的待辦事項

```bash
omi action-item list --json --open
```

### 5. 把待辦事項標記為完成

```bash
omi action-item complete --json a1b2c3d4
```

## 本機 Desktop API

當 Omi Desktop 暴露其本機 API 時，Agent 可以查詢裝置端的螢幕歷史、回顧、
SQL 和任務，而不必使用雲端開發 API：

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# 或用於臨時工作階段：
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

只有在使用者明確要求時，才完成或刪除任務：

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` 會把螢幕截圖寫入磁碟，
同時仍向標準輸出印出 JSON 供指令碼使用。螢幕截圖 ID 通常來自
`local search-screen`，或來自對 `screenshots` 資料表執行 SQL 的結果。
如果 Desktop 傳回結構化失敗（例如 `screenshot_pending`、
`screenshot_file_missing` 或 `screenshot_chunk_corrupted`），JSON 模式
會在標準錯誤上保留 `reason`、`hint` 和 `screenshot_id` 欄位，
方便 Agent 改用較早的 ID 重試，或準確回報阻塞點。把成功輸出交給視覺工具
之前，先用 `file PATH` 驗證。

## 完整範例：Python Agent 迴圈

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """以 JSON 模式呼叫 omi CLI；離開碼非成功時抛出例外。"""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # 在 JSON 模式下，CLI 會向標準錯誤輸出結構化錯誤：
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# 讀取所有未完成的待辦事項，把超過 30 天的標記為完成。
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## 處理速率限制

記憶：每小時 120 次。對話：每小時 25 次。批次建立：每小時 15 次。

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # 觸發速率限制
    err = json.loads(result.stderr)
    # err["detail"] 形如："Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## 實用提示

* 如果你的 Agent 需要同時管理多個 Omi 帳號，使用 `--profile <name>`。
  每個設定檔有各自的憑證和 API base。
* 本機後端測試時使用 `--api-base http://localhost:8080`。
* 用 `OMI_LOCAL_API_URL` 和 `OMI_LOCAL_TOKEN` 可以在單次執行中覆寫
  設定檔裡的本機 Desktop API 設定。
* 除錯時使用 `--verbose` —— 它會把 `METHOD path → status (Ns)` 記錄到
  標準錯誤，不影響標準輸出，因此 JSON 模式依然合法。
* 需要把內容以管線傳入對話時，使用 `--text -`：
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
