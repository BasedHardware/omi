# 代理用个 omi-cli

> 分 LLM 驅動个架構用个實用指南（Claude Code、Cursor、若自家个機器人）。

## 做麼个 CLI 適合代理

* **穩定个 JSON 約定。** `--json` 淨輸出有效个 JSON 文檔到 stdout——無進度消息，無轉圈圈。錯誤用 `{"error": "...", "detail": "..."}` 送到 stderr。
* **穩定个退出碼。** `0` 成功 / `1` 用法 / `2` 認證 / `3` 服務器 / `4` 限流 / `5` 無尋着。代理做得根據這兜代碼分支，毋使解析自然語言个錯誤。
* **無頭環境無交互提示。** 破壞性命令傳 `--yes`（或者 `-y`）；傳 `--api-key` 或者設置 `OMI_API_KEY` 來跳過交互式登錄。
* **寬容个重試行為。** `429` 同 `5xx` 會用 backoff 重試過後正報告。

## 認證（一擺，分人來做）

用戶在 Omi 網頁應用（`https://app.omi.me` → Developer → API Keys）拿開發者 API 密鑰，然後兩種方法任選一隻：
```bash
omi auth login                          # 交互式粘貼；密鑰毋會出現在 shell 歷史裡肚
# 或者
export OMI_API_KEY=omi_dev_...          # 臨時个，適合容器
```

## 代理最常用个五件事

### 1. 讀記憶
```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. 創建記憶
```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. 讀對話
```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. 讀打開个待辦
```bash
omi action-item list --json --open
```

### 5. 將待辦標記做完成
```bash
omi action-item complete --json a1b2c3d4
```

## 本地桌面 API

當 Omi Desktop 公開佢个本地 API，代理做得查詢設備頂高个屏幕歷史、摘要、SQL 同任務，毋使經過雲開發者 API：
```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# 或者，臨時會話用：
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

淨在用戶明確要求个時節正完成或者刪除任務：
```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` 將截圖寫到磁盤，同時還向 stdout 打印 JSON 分腳本用。截圖 ID 一般來自 `local search-screen` 或者在 `screenshots` 表頂高个 SQL。若係 Desktop 返回 `screenshot_pending`、`screenshot_file_missing` 或者 `screenshot_chunk_corrupted` 這種結構化失敗，JSON 模式會在 stderr 頂高保留 `reason`、`hint` 同 `screenshot_id` 字段，分代理重試舊个 ID 或者準確報告阻塞點。將成功个輸出用 `file PATH` 驗證過後，正傳分視覺工具。
```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """用 JSON 模式調用 omi CLI，非成功退出碼會拋異常。"""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI 在 JSON 模式下將結構化錯誤打印到 stderr：
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# 讀取所有打開个待辦，將超過 30 日个標記做完成。
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## 處理限流

Memories: 120/hr. Conversations: 25/hr. Batch creates: 15/hr.
```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # 被限流
    err = json.loads(result.stderr)
    # err["detail"] 看起來像："Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## 貼士

* 若係若个代理管幾隻 Omi 賬號，用 `--profile <name>`。每個 profile 有自家个憑證同 API base。
* 本地後端測試用 `--api-base http://localhost:8080`。
* 用 `OMI_LOCAL_API_URL` 同 `OMI_LOCAL_TOKEN` 來覆蓋單擺運行个 profile 本地桌面 API 設置。
* 調試用 `--verbose`——佢將 `METHOD path → status (Ns)` 記錄到 stderr，毋影響 stdout，所以 JSON 模式還有效。
* 愛將內容管道送到對話裡肚，用 `--text -`：
```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
