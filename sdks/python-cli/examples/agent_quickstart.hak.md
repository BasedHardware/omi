# 分 Agent 使用个 omi-cli

> 分 LLM 驅動个 harness（Claude Code、Cursor、你自家做个 bot）使用个實戰指南。

## 仰脣這隻 CLI 適合 agent

* **JSON 契約穩定。** 加 `--json` 了後，stdout 會輸出一隻合法 JSON 文件，
  *淨係* JSON 文件 — 無進度訊息，乜無 spinner。錯誤會以
  `{"error": "...", "detail": "..."}` 个形式去著 stderr。
* **結束碼穩定。** `0` 成功 / `1` 用法錯誤 / `2` 認證錯誤 /
  `3` 伺服器錯誤 / `4` 限流 / `5` 尋無。Agent 毋使解析自然語言个
  錯誤訊息，直接按這個值分支就做得。
* **headless 環境毋會彈出交互提示。** 破壞性个指令加 `--yes`（或者 `-y`）；
  傳 `--api-key` 或者設 `OMI_API_KEY` 就做得略過交互登入。
* **重試較寬容。** `429` 同 `5xx` 會在出現之前先帶 backoff 重試。

## 認證（人淨做一擺）

使用者在 Omi 網站應用（`https://app.omi.me` → Developer → API Keys）
提開發者 API key，然後做下背兩項裡背个一項：

```bash
omi auth login                          # 交互式貼入；key 毋會入 shell 歷史
# 或者
export OMI_API_KEY=omi_dev_...          # 臨時个，適合容器
```

## Agent 最常做个五項事體

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

### 4. 讀還未完成个 action items

```bash
omi action-item list --json --open
```

### 5. 摝 action item 標做完成

```bash
omi action-item complete --json a1b2c3d4
```

## 本地 Desktop API

假使 Omi Desktop 有公開佢个本地 API，agent 毋使用雲端个開發者 API，
就做得查詢設備上个螢幕歷史、摘要、SQL 同任務：

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

淨係使用者明確要求个時節，正完成或者刪除任務：

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` 會摝截圖寫落磁碟，
同時還會對 stdout 打印 JSON 分腳本用。Screenshot ID 一般係對
`local search-screen` 或者對 `screenshots` 表个 SQL 來个。假使 Desktop
回傳 `screenshot_pending`、`screenshot_file_missing`、
`screenshot_chunk_corrupted` 這款結構化失敗，JSON 模式會摝 `reason`、
`hint`、`screenshot_id` 這幾隻欄位保留在 stderr，agent 就做得用較舊个
ID 重試，或者報告準確个阻塞原因。成功个輸出在交分視覺工具之前，
請先用 `file PATH` 驗證一擺。

## 實例：Python agent 循環

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """用 JSON 模式呼叫 omi CLI，結束碼毋係 0 就擲出例外。"""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # JSON 模式裡背 CLI 會在 stderr 輸出結構化錯誤：
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# 讀全部還未完成个 action items，超過 30 日个總下標做完成。
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## 限流仰脣處理

Memories：一點鐘 120 擺。Conversations：一點鐘 25 擺。批次建立：一點鐘 15 擺。

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # 限流
    err = json.loads(result.stderr)
    # err["detail"] 係這款樣仔："Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## 小提醒

* 假使若你个 agent 愛管理多个 Omi 帳號，用 `--profile <name>`。
  逐隻 profile 有自家个 credential 同 API base。
* 試本地後端个時節用 `--api-base http://localhost:8080`。
* 用 `OMI_LOCAL_API_URL` 同 `OMI_LOCAL_TOKEN`，做得淨對一擺執行覆寫
  profile 裡背个 Desktop API 設定。
* 除錯用 `--verbose` — 佢會摝 `METHOD path → status (Ns)` 記落 stderr，
  毋會影響 stdout，所以 JSON 模式照樣有效。
* 想摝內容 pipe 入 conversation，用 `--text -`：
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
