# 予 Agent 使用个 omi-cli

> 予 LLM 驅動个 harness（Claude Code、Cursor、汝自家做个 bot）使用个實戰指南。

## 為啥物這个 CLI 適合 agent

* **JSON 契約穩定。** 加 `--json` 了後，stdout 會輸出一个合法 JSON 文件，
  *干焦* JSON 文件 — 無進度訊息，嘛無 spinner。錯誤會以
  `{"error": "...", "detail": "..."}` 个形式去著 stderr。
* **結束代碼穩定。** `0` 成功 / `1` 用法錯誤 / `2` 認證錯誤 /
  `3` 伺服器錯誤 / `4` 限流 / `5` 揣無。Agent 毋免解析自然語言个
  錯誤訊息，直接按這个值分支就會使。
* **headless 環境袂弹出交互提示。** 破壞性个指令加 `--yes`（抑是 `-y`）；
  傳 `--api-key` 抑是設 `OMI_API_KEY` 就會使略過交互登入。
* **重試較寬容。** `429` 佮 `5xx` 會佇出現進前先帶 backoff 重試。

## 認證（人干焦做一擺）

使用者佇 Omi 網站應用（`https://app.omi.me` → Developer → API Keys）
提開發者 API key，然後做下底兩項內底个一項：

```bash
omi auth login                          # 交互式貼入；key 袂入 shell 歷史
# 抑是
export OMI_API_KEY=omi_dev_...          # 臨時个，適合容器
```

## Agent 上捷做个五項代誌

### 1. 讀 memories

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. 建立 memory

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. 讀 conversations

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. 讀猶未完成个 action items

```bash
omi action-item list --json --open
```

### 5. 共 action item 標做完成

```bash
omi action-item complete --json a1b2c3d4
```

## 本地 Desktop API

若是 Omi Desktop 有公開伊个本地 API，agent 毋免用雲端个開發者 API，
就會使查詢設備頂个螢幕歷史、摘要、SQL 佮任務：

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# 抑是，臨時會話用：
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

干焦使用者明確要求个時陣，才完成抑是刪除任務：

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` 會共截圖寫落磁碟，
同時閣會對 stdout 打印 JSON 予腳本用。Screenshot ID 一般是對
`local search-screen` 抑是對 `screenshots` 表个 SQL 來个。若是 Desktop
回傳 `screenshot_pending`、`screenshot_file_missing`、
`screenshot_chunk_corrupted` 這款結構化失敗，JSON 模式會共 `reason`、
`hint`、`screenshot_id` 這幾个欄位保留佇 stderr，agent 就會使用較舊个
ID 重試，抑是報告確實个阻塞原因。成功个輸出佇交予視覺工具進前，
請先用 `file PATH` 驗證一擺。

## 實例：Python agent 循環

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """用 JSON 模式呼叫 omi CLI，結束代碼毋是 0 就擲出例外。"""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # JSON 模式內底 CLI 會佇 stderr 輸出結構化錯誤：
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# 讀全部猶未完成个 action items，超過 30 工个攏標做完成。
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## 限流按怎處理

Memories：一點鐘 120 擺。Conversations：一點鐘 25 擺。批次建立：一點鐘 15 擺。

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # 限流
    err = json.loads(result.stderr)
    # err["detail"] 是這款樣仔："Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## 小提醒

* 若是汝个 agent 愛管理多个 Omi 帳號，用 `--profile <name>`。
  逐个 profile 有家己个 credential 佮 API base。
* 試本地後端个時陣用 `--api-base http://localhost:8080`。
* 用 `OMI_LOCAL_API_URL` 佮 `OMI_LOCAL_TOKEN`，會使干焦對一擺執行覆寫
  profile 內底个 Desktop API 設定。
* 除錯用 `--verbose` — 伊會共 `METHOD path → status (Ns)` 記落 stderr，
  袂影響 stdout，所以 JSON 模式照樣有效。
* 欲共內容 pipe 入 conversation，用 `--text -`：
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
