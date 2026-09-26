# ਏਜੰਟਾਂ ਲਈ omi-cli

> LLM-ਸੰਚਾਲਿਤ ਏਜੰਟ ਵਾਤਾਵਰਨਾਂ ਲਈ (Claude Code, Cursor, ਤੁਹਾਡੇ ਆਪਣੇ ਬੌਟ) ਵਿਹਾਰਕ ਗਾਈਡ।

## CLI ਏਜੰਟ-ਅਨੁਕੂਲ ਕਿਉਂ ਹੈ

* **ਸਥਿਰ JSON ਇਕਰਾਰਨਾਮਾ।** `--json` stdout 'ਤੇ ਇੱਕ ਵੈਧ JSON ਦਸਤਾਵੇਜ਼ ਭੇਜਦਾ ਹੈ ਅਤੇ
  *ਸਿਰਫ਼* ਇੱਕ JSON ਦਸਤਾਵੇਜ਼ — ਕੋਈ ਪ੍ਰਗਤੀ ਸੁਨੇਹੇ ਨਹੀਂ, ਕੋਈ ਸਪਿਨਰ ਨਹੀਂ। ਗਲਤੀਆਂ
  stderr 'ਤੇ `{"error": "...", "detail": "..."}` ਦੇ ਰੂਪ ਵਿੱਚ ਜਾਂਦੀਆਂ ਹਨ।
* **ਸਥਿਰ ਐਗਜ਼ਿਟ ਕੋਡ।** `0` ਸਫਲ / `1` ਗਲਤ ਵਰਤੋਂ / `2` ਪ੍ਰਮਾਣਿਕਤਾ /
  `3` ਸਰਵਰ / `4` ਦਰ-ਸੀਮਤ / `5` ਨਹੀਂ ਲੱਭਿਆ। ਏਜੰਟ ਕੁਦਰਤੀ-ਭਾਸ਼ਾ ਦੀਆਂ ਗਲਤੀਆਂ
  ਪਾਰਸ ਕੀਤੇ ਬਿਨਾਂ ਇਨ੍ਹਾਂ ਕੋਡਾਂ 'ਤੇ ਸ਼ਾਖਾਵਾਂ ਬਣਾ ਸਕਦੇ ਹਨ।
* **ਹੈੱਡਲੈੱਸ ਸੰਦਰਭਾਂ ਵਿੱਚ ਕੋਈ ਇੰਟਰਐਕਟਿਵ ਪ੍ਰੋਂਪਟ ਨਹੀਂ।** ਵਿਨਾਸ਼ਕਾਰੀ ਕਮਾਂਡਾਂ ਲਈ
  `--yes` (ਜਾਂ `-y`) ਦਿਓ; ਇੰਟਰਐਕਟਿਵ ਲੌਗਇਨ ਟਾਲਣ ਲਈ `--api-key` ਦਿਓ ਜਾਂ
  `OMI_API_KEY` ਸੈੱਟ ਕਰੋ।
* **ਬਰਦਾਸ਼ਤ ਕਰਨ ਵਾਲਾ ਮੁੜ-ਕੋਸ਼ਿਸ਼ ਵਿਵਹਾਰ।** `429` ਅਤੇ `5xx` ਸਾਹਮਣੇ ਆਉਣ ਤੋਂ ਪਹਿਲਾਂ
  ਬੈਕਆਫ ਨਾਲ ਮੁੜ ਕੋਸ਼ਿਸ਼ ਕੀਤੀ ਜਾਂਦੀ ਹੈ।

## ਪ੍ਰਮਾਣਿਕਤਾ (ਇੱਕ ਵਾਰ, ਮਨੁੱਖ ਵੱਲੋਂ)

ਵਰਤੋਂਕਾਰ Omi ਵੈੱਬ ਐਪ (`https://app.omi.me` → Developer → API Keys) ਤੋਂ ਡਿਵ API ਕੀ
ਲੈਂਦਾ ਹੈ ਅਤੇ ਇਨ੍ਹਾਂ ਵਿੱਚੋਂ ਇੱਕ ਤਰੀਕਾ ਚੁਣਦਾ ਹੈ:

```bash
omi auth login                          # ਇੰਟਰਐਕਟਿਵ ਪੇਸਟ; ਕੀ shell ਇਤਿਹਾਸ ਵਿੱਚ ਨਹੀਂ ਰਹਿੰਦੀ
# ਜਾਂ
export OMI_API_KEY=omi_dev_...          # ਅਸਥਾਈ, ਕੰਟੇਨਰ-ਅਨੁਕੂਲ
```

## ਏਜੰਟ ਸਭ ਤੋਂ ਵੱਧ ਕਰਦੇ ਹਨ ਇਹ ਪੰਜ ਕੰਮ

### 1. ਯਾਦਾਂ ਪੜ੍ਹੋ

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. ਯਾਦ ਬਣਾਓ

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. ਗੱਲਬਾਤਾਂ ਪੜ੍ਹੋ

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. ਖੁੱਲ੍ਹੀਆਂ ਐਕਸ਼ਨ ਆਈਟਮਾਂ ਪੜ੍ਹੋ

```bash
omi action-item list --json --open
```

### 5. ਐਕਸ਼ਨ ਆਈਟਮ ਪੂਰੀ ਕਰੋ

```bash
omi action-item complete --json a1b2c3d4
```

## ਲੋਕਲ ਡੈਸਕਟਾਪ API

ਜਦੋਂ Omi Desktop ਆਪਣਾ ਲੋਕਲ API ਪ੍ਰਗਟ ਕਰਦਾ ਹੈ, ਤਾਂ ਏਜੰਟ ਕਲਾਊਡ ਡਿਵ API ਵਰਤੇ ਬਿਨਾਂ
ਡਿਵਾਈਸ ਦੀ ਸਕਰੀਨ ਹਿਸਟਰੀ, ਸਾਰਾਂਸ਼, SQL ਅਤੇ ਟਾਸਕਾਂ ਦੀ ਕੁਐਰੀ ਕਰ ਸਕਦੇ ਹਨ:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# ਜਾਂ, ਅਸਥਾਈ ਸੈਸ਼ਨਾਂ ਲਈ:
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

ਵਰਤੋਂਕਾਰ ਸਪੱਸ਼ਟ ਤੌਰ 'ਤੇ ਕਹੇ ਤਾਂ ਹੀ ਟਾਸਕ ਪੂਰੇ ਕਰੋ ਜਾਂ ਮਿਟਾਓ:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` ਸਕਰੀਨਸ਼ਾਟ ਡਿਸਕ 'ਤੇ ਲਿਖਦਾ ਹੈ ਅਤੇ
ਸਕ੍ਰਿਪਟਾਂ ਲਈ stdout 'ਤੇ JSON ਪ੍ਰਿੰਟ ਕਰਦਾ ਹੈ। ਸਕਰੀਨਸ਼ਾਟ ਆਈਡੀ ਆਮ ਤੌਰ 'ਤੇ
`local search-screen` ਜਾਂ `screenshots` ਟੇਬਲ 'ਤੇ SQL ਤੋਂ ਆਉਂਦੀ ਹੈ। ਜੇ Desktop
`screenshot_pending`, `screenshot_file_missing` ਜਾਂ `screenshot_chunk_corrupted`
ਵਰਗੀ ਢਾਂਚਾਗਤ ਅਸਫਲਤਾ ਵਾਪਸ ਕਰੇ, ਤਾਂ JSON ਮੋਡ stderr 'ਤੇ `reason`, `hint` ਅਤੇ
`screenshot_id` ਫੀਲਡ ਸੰਭਾਲਦਾ ਹੈ, ਤਾਂ ਜੋ ਏਜੰਟ ਪੁਰਾਣੀ ਆਈਡੀ ਨਾਲ ਮੁੜ ਕੋਸ਼ਿਸ਼ ਕਰ ਸਕਣ
ਜਾਂ ਸਹੀ ਰੁਕਾਵਟ ਦੀ ਰਿਪੋਰਟ ਕਰ ਸਕਣ। ਸਫਲ ਆਉਟਪੁੱਟਾਂ ਨੂੰ ਵਿਜ਼ਨ ਟੂਲਾਂ ਨੂੰ ਭੇਜਣ ਤੋਂ
ਪਹਿਲਾਂ `file PATH` ਨਾਲ ਜਾਂਚੋ।

## ਕਾਰਜਪ੍ਰਵਾਹ ਉਦਾਹਰਨ: Python ਏਜੰਟ ਲੂਪ

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """omi CLI ਨੂੰ JSON ਮੋਡ ਵਿੱਚ ਚਲਾਉਂਦਾ ਹੈ, ਅਸਫਲ ਐਗਜ਼ਿਟ ਕੋਡਾਂ 'ਤੇ ਅਪਵਾਦ ਉਠਾਉਂਦਾ ਹੈ।"""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI JSON ਮੋਡ ਵਿੱਚ stderr 'ਤੇ ਢਾਂਚਾਗਤ ਗਲਤੀਆਂ ਪ੍ਰਿੰਟ ਕਰਦਾ ਹੈ:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# ਸਾਰੀਆਂ ਖੁੱਲ੍ਹੀਆਂ ਐਕਸ਼ਨ ਆਈਟਮਾਂ ਪੜ੍ਹੋ ਅਤੇ 30 ਦਿਨਾਂ ਤੋਂ ਪੁਰਾਣੀਆਂ ਪੂਰੀਆਂ ਕਰੋ।
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## ਦਰ ਸੀਮਾਵਾਂ ਨੂੰ ਸੰਭਾਲਣਾ

ਯਾਦਾਂ: 120/ਘੰਟਾ। ਗੱਲਬਾਤਾਂ: 25/ਘੰਟਾ। ਬੈਚ ਸਿਰਜਣਾ: 15/ਘੰਟਾ।

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # ਦਰ-ਸੀਮਤ
    err = json.loads(result.stderr)
    # err["detail"] ਇੰਝ ਦਿਖਦਾ ਹੈ: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## ਸੁਝਾਅ

* ਜੇ ਤੁਹਾਡਾ ਏਜੰਟ ਕਈ Omi ਖਾਤੇ ਸੰਭਾਲਦਾ ਹੈ ਤਾਂ `--profile <name>` ਵਰਤੋ। ਹਰ ਪ੍ਰੋਫਾਈਲ
  ਦੇ ਆਪਣੇ ਪ੍ਰਮਾਣ ਪੱਤਰ ਅਤੇ API ਬੇਸ ਹੁੰਦੇ ਹਨ।
* ਲੋਕਲ ਬੈਕਐਂਡ ਟੈਸਟਿੰਗ ਲਈ `--api-base http://localhost:8080` ਵਰਤੋ।
* ਇੱਕ ਰਨ ਲਈ ਪ੍ਰੋਫਾਈਲ-ਲੋਕਲ Desktop API ਸੈਟਿੰਗਾਂ ਓਵਰਰਾਈਡ ਕਰਨ ਲਈ
  `OMI_LOCAL_API_URL` ਅਤੇ `OMI_LOCAL_TOKEN` ਵਰਤੋ।
* ਡੀਬੱਗਿੰਗ ਲਈ `--verbose` ਵਰਤੋ — ਇਹ stderr 'ਤੇ `METHOD path → status (Ns)`
  ਲੌਗ ਕਰਦਾ ਹੈ, stdout ਨੂੰ ਪ੍ਰਭਾਵਿਤ ਨਹੀਂ ਕਰਦਾ, ਇਸ ਲਈ JSON ਮੋਡ ਵੈਧ ਰਹਿੰਦਾ ਹੈ।
* ਪਾਈਪ ਰਾਹੀਂ ਗੱਲਬਾਤ ਵਿੱਚ ਸਮੱਗਰੀ ਭੇਜਣ ਲਈ `--text -` ਵਰਤੋ:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
