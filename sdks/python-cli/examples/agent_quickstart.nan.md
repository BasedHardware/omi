# 予代理用的 omi-cli

> 予 LLM 驅動的架構用的實用指南（Claude Code、Cursor、你家己的機器人）。

## 為啥物 CLI 適合代理

* **穩定的 JSON 約定。** `--json` 干焦輸出有效的 JSON 文件去 stdout——無進度訊息，無踅玲瑯。錯誤用 `{"error": "...", "detail": "..."}` 送去 stderr。
* **穩定的結束碼。** `0` 成功 / `1` 用法 / `2` 認證 / `3` 伺服器 / `4` 限流 / `5` 揣無。代理會使根據這兜代碼分叉，毋免解析自然語言的錯誤。
* **無頭環境無互動提示。** 破壞性的命令傳 `--yes`（或者 `-y`）；傳 `--api-key` 或者設定 `OMI_API_KEY` 來跳過互動式登入。
* **寬容的重試行為。** `429` 佮 `5xx` 會用 backoff 重試了後才報告。

## 認證（一擺，予人來做）

使用者佇 Omi 網頁應用（`https://app.omi.me` → Developer → API Keys）提開發者 API 金鑰，然後兩種方法隨選一項：
```bash
omi auth login                          # 互動式貼上；金鑰袂出現佇 shell 歷史裡面
# 或者
export OMI_API_KEY=omi_dev_...          # 臨時的，適合容器
```

## 代理上常用的五項代誌

### 1. 讀記持
```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. 建立記持
```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. 讀對話
```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. 讀拍開的待辦
```bash
omi action-item list --json --open
```

### 5. 將待辦標做完成
```bash
omi action-item complete --json a1b2c3d4
```

## 本地桌面 API

當 Omi Desktop 公開伊的本地 API，代理會使查詢裝置頂懸的螢幕歷史、摘要、SQL 佮任務，毋免經過雲開發者 API：
```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# 或者，臨時的連線用：
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

干焦佇使用者明確要求的時陣才完成或者刪除任務：
```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` 將截圖寫去磁碟，同時猶向 stdout 印 JSON 予跤本用。截圖 ID 一般來自 `local search-screen` 或者佇 `screenshots` 表頂懸的 SQL。若是 Desktop 轉去 `screenshot_pending`、`screenshot_file_missing` 或者 `screenshot_chunk_corrupted` 這款結構化失敗，JSON 模式會佇 stderr 頂懸保留 `reason`、`hint` 佮 `screenshot_id` 欄位，予代理重試較舊的 ID 或者準確報告出問題的位。將成功的輸出用 `file PATH` 驗證了後，才傳予視覺工具。
```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """用 JSON 模式叫 omi CLI，非成功結束碼會擲異常。"""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI 佇 JSON 模式將結構化錯誤印去 stderr：
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# 讀所有拍開的待辦，將超過 30 日的標做完成。
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
if result.returncode == 4:                             # 予限流
    err = json.loads(result.stderr)
    # err["detail"] 看起來像："Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## 貼士

* 若是你的代理管幾若个 Omi 口座，用 `--profile <name>`。逐个 profile 有家己的憑證佮 API base。
* 本地後端測試用 `--api-base http://localhost:8080`。
* 用 `OMI_LOCAL_API_URL` 佮 `OMI_LOCAL_TOKEN` 來崁過單擺走的 profile 本地桌面 API 設定。
* 除錯用 `--verbose`——伊將 `METHOD path → status (Ns)` 記去 stderr，袂影響 stdout，所以 JSON 模式猶有效。
* 欲將內容管路送去對話裡面，用 `--text -`：
```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
