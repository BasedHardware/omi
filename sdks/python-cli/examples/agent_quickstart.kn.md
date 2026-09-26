# ಏಜೆಂಟ್‌ಗಳಿಗಾಗಿ omi-cli

> LLM-ಚಾಲಿತ ಏಜೆಂಟ್ ಪರಿಸರಗಳಿಗಾಗಿ (Claude Code, Cursor, ನಿಮ್ಮ ಸ್ವಂತ ಬಾಟ್‌ಗಳು) ಪ್ರಾಯೋಗಿಕ ಮಾರ್ಗದರ್ಶಿ.

## CLI ಏಕೆ ಏಜೆಂಟ್-ಸ್ನೇಹಿ

* **ಸ್ಥಿರ JSON ಒಪ್ಪಂದ.** `--json` stdout ಗೆ ಮಾನ್ಯವಾದ JSON ದಾಖಲೆಯನ್ನು ಹೊರಡಿಸುತ್ತದೆ ಮತ್ತು
  *JSON ದಾಖಲೆಯನ್ನು ಮಾತ್ರ* — ಪ್ರಗತಿ ಸಂದೇಶಗಳಿಲ್ಲ, ಸ್ಪಿನ್ನರ್‌ಗಳಿಲ್ಲ. ದೋಷಗಳು
  stderr ಗೆ `{"error": "...", "detail": "..."}` ರೂಪದಲ್ಲಿ ಹೋಗುತ್ತವೆ.
* **ಸ್ಥಿರ ನಿರ್ಗಮನ ಕೋಡ್‌ಗಳು.** `0` ಯಶಸ್ಸು / `1` ತಪ್ಪು ಬಳಕೆ / `2` ದೃಢೀಕರಣ /
  `3` ಸರ್ವರ್ / `4` ದರ-ಮಿತಿ / `5` ಕಂಡುಬಂದಿಲ್ಲ. ಏಜೆಂಟ್‌ಗಳು ಸ್ವಾಭಾವಿಕ-ಭಾಷೆಯ
  ದೋಷಗಳನ್ನು ವಿಶ್ಲೇಷಿಸದೆಯೇ ಈ ಕೋಡ್‌ಗಳ ಮೇಲೆ ಶಾಖೆಗಳನ್ನು ಮಾಡಬಹುದು.
* **ಹೆಡ್‌ಲೆಸ್ ಸಂದರ್ಭಗಳಲ್ಲಿ ಸಂವಾದಾತ್ಮಕ ಪ್ರಾಂಪ್ಟ್‌ಗಳಿಲ್ಲ.** ವಿನಾಶಕಾರಿ ಆದೇಶಗಳಿಗೆ
  `--yes` (ಅಥವಾ `-y`) ನೀಡಿ; ಸಂವಾದಾತ್ಮಕ ಲಾಗಿನ್ ತಪ್ಪಿಸಲು `--api-key` ನೀಡಿ
  ಅಥವಾ `OMI_API_KEY` ಅನ್ನು ಸೆಟ್ ಮಾಡಿ.
* **ಕ್ಷಮಿಸುವ ಮರುಪ್ರಯತ್ನ ವರ್ತನೆ.** `429` ಮತ್ತು `5xx` ಗೋಚರಿಸುವ ಮೊದಲು ಬ್ಯಾಕಾಫ್‌ನೊಂದಿಗೆ
  ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಲಾಗುತ್ತದೆ.

## ದೃಢೀಕರಣ (ಒಮ್ಮೆ, ಮನುಷ್ಯನಿಂದ)

ಬಳಕೆದಾರರು Omi ವೆಬ್ ಆ್ಯಪ್‌ನಿಂದ (`https://app.omi.me` → Developer → API Keys) ಡೆವ್ API
ಕೀಯನ್ನು ಪಡೆದು, ಇವುಗಳಲ್ಲಿ ಒಂದನ್ನು ಆಯ್ಕೆ ಮಾಡುತ್ತಾರೆ:

```bash
omi auth login                          # ಸಂವಾದಾತ್ಮಕ ಅಂಟಿಸುವಿಕೆ; ಕೀ shell ಇತಿಹಾಸದಲ್ಲಿ ಉಳಿಯುವುದಿಲ್ಲ
# ಅಥವಾ
export OMI_API_KEY=omi_dev_...          # ತಾತ್ಕಾಲಿಕ, ಕಂಟೇನರ್-ಸ್ನೇಹಿ
```

## ಏಜೆಂಟ್‌ಗಳು ಹೆಚ್ಚು ಮಾಡುವ ಐದು ಕೆಲಸಗಳು

### 1. ನೆನಪುಗಳನ್ನು ಓದಿ

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. ನೆನಪನ್ನು ರಚಿಸಿ

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. ಸಂಭಾಷಣೆಗಳನ್ನು ಓದಿ

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. ತೆರೆದ ಆಕ್ಷನ್ ಐಟಂಗಳನ್ನು ಓದಿ

```bash
omi action-item list --json --open
```

### 5. ಆಕ್ಷನ್ ಐಟಂ ಪೂರ್ಣಗೊಳಿಸಿ

```bash
omi action-item complete --json a1b2c3d4
```

## ಸ್ಥಳೀಯ ಡೆಸ್ಕ್‌ಟಾಪ್ API

Omi Desktop ತನ್ನ ಸ್ಥಳೀಯ API ಅನ್ನು ಒದಗಿಸಿದಾಗ, ಕ್ಲೌಡ್ ಡೆವ್ API ಬಳಸದೆಯೇ ಏಜೆಂಟ್‌ಗಳು
ಸಾಧನದ ಸ್ಕ್ರೀನ್ ಇತಿಹಾಸ, ಸಾರಾಂಶಗಳು, SQL ಮತ್ತು ಕಾರ್ಯಗಳನ್ನು ಪ್ರಶ್ನಿಸಬಹುದು:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# ಅಥವಾ, ತಾತ್ಕಾಲಿಕ ಸೆಷನ್‌ಗಳಿಗಾಗಿ:
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

ಬಳಕೆದಾರರು ಸ್ಪಷ್ಟವಾಗಿ ಕೇಳಿದಾಗ ಮಾತ್ರ ಕಾರ್ಯಗಳನ್ನು ಪೂರ್ಣಗೊಳಿಸಿ ಅಥವಾ ಅಳಿಸಿ:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` ಸ್ಕ್ರೀನ್‌ಶಾಟ್ ಅನ್ನು ಡಿಸ್ಕ್‌ಗೆ ಬರೆಯುತ್ತದೆ
ಮತ್ತು ಸ್ಕ್ರಿಪ್ಟ್‌ಗಳಿಗಾಗಿ stdout ಗೆ JSON ಅನ್ನು ಮುದ್ರಿಸುತ್ತದೆ. ಸ್ಕ್ರೀನ್‌ಶಾಟ್ ಐಡಿ ಸಾಮಾನ್ಯವಾಗಿ
`local search-screen` ನಿಂದ ಅಥವಾ `screenshots` ಟೇಬಲ್‌ನ ಮೇಲಿನ SQL ನಿಂದ ಬರುತ್ತದೆ. Desktop
`screenshot_pending`, `screenshot_file_missing` ಅಥವಾ `screenshot_chunk_corrupted`
ಮುಂತಾದ ರಚನಾತ್ಮಕ ವೈಫಲ್ಯವನ್ನು ಹಿಂತಿರುಗಿಸಿದರೆ, JSON ಮೋಡ್ stderr ನಲ್ಲಿ `reason`, `hint`
ಮತ್ತು `screenshot_id` ಕ್ಷೇತ್ರಗಳನ್ನು ಸಂರಕ್ಷಿಸುತ್ತದೆ, ಇದರಿಂದ ಏಜೆಂಟ್‌ಗಳು ಹಳೆಯ ಐಡಿಯೊಂದಿಗೆ
ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಬಹುದು ಅಥವಾ ನಿಖರವಾದ ಅಡಚಣೆಯನ್ನು ವರದಿ ಮಾಡಬಹುದು. ಯಶಸ್ವಿ ಔಟ್‌ಪುಟ್‌ಗಳನ್ನು
ವಿಷನ್ ಟೂಲ್‌ಗಳಿಗೆ ಕಳುಹಿಸುವ ಮೊದಲು `file PATH` ನಿಂದ ಪರಿಶೀಲಿಸಿ.

## ಕಾರ್ಯವಿಧಾನ ಉದಾಹರಣೆ: Python ಏಜೆಂಟ್ ಲೂಪ್

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """omi CLI ಅನ್ನು JSON ಮೋಡ್‌ನಲ್ಲಿ ಚಲಾಯಿಸುತ್ತದೆ, ವಿಫಲ ನಿರ್ಗಮನ ಕೋಡ್‌ಗಳಲ್ಲಿ ವಿನಾಯಿತಿ ಎಸೆಯುತ್ತದೆ."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI JSON ಮೋಡ್‌ನಲ್ಲಿ stderr ಗೆ ರಚನಾತ್ಮಕ ದೋಷಗಳನ್ನು ಮುದ್ರಿಸುತ್ತದೆ:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# ಎಲ್ಲಾ ತೆರೆದ ಆಕ್ಷನ್ ಐಟಂಗಳನ್ನು ಓದಿ ಮತ್ತು 30 ದಿನಗಳಿಗಿಂತ ಹಳೆಯವನ್ನು ಪೂರ್ಣಗೊಳಿಸಿ.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## ದರ ಮಿತಿಗಳನ್ನು ನಿರ್ವಹಿಸುವುದು

ನೆನಪುಗಳು: 120/ಗಂಟೆ. ಸಂಭಾಷಣೆಗಳು: 25/ಗಂಟೆ. ಬ್ಯಾಚ್ ರಚನೆಗಳು: 15/ಗಂಟೆ.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # ದರ-ಮಿತಿ
    err = json.loads(result.stderr)
    # err["detail"] ಹೀಗೆ ಕಾಣುತ್ತದೆ: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## ಸಲಹೆಗಳು

* ನಿಮ್ಮ ಏಜೆಂಟ್ ಅನೇಕ Omi ಖಾತೆಗಳನ್ನು ನಿರ್ವಹಿಸಿದರೆ `--profile <name>` ಬಳಸಿ. ಪ್ರತಿ
  ಪ್ರೊಫೈಲ್‌ಗೆ ಅದರದೇ ರುಜುವಾತುಗಳು ಮತ್ತು API ಬೇಸ್ ಇರುತ್ತವೆ.
* ಸ್ಥಳೀಯ ಬ್ಯಾಕೆಂಡ್ ಪರೀಕ್ಷೆಗಾಗಿ `--api-base http://localhost:8080` ಬಳಸಿ.
* ಒಂದು ರನ್‌ಗಾಗಿ ಪ್ರೊಫೈಲ್-ಸ್ಥಳೀಯ Desktop API ಸೆಟ್ಟಿಂಗ್‌ಗಳನ್ನು ಓವರ್‌ರೈಡ್ ಮಾಡಲು
  `OMI_LOCAL_API_URL` ಮತ್ತು `OMI_LOCAL_TOKEN` ಬಳಸಿ.
* ಡೀಬಗ್ ಮಾಡಲು `--verbose` ಬಳಸಿ — ಇದು stderr ಗೆ `METHOD path → status (Ns)`
  ಲಾಗ್ ಮಾಡುತ್ತದೆ, stdout ಅನ್ನು ಪ್ರಭಾವಿಸುವುದಿಲ್ಲ, ಆದ್ದರಿಂದ JSON ಮೋಡ್ ಮಾನ್ಯವಾಗಿರುತ್ತದೆ.
* ಪೈಪ್ ಮೂಲಕ ಸಂಭಾಷಣೆಗೆ ವಿಷಯವನ್ನು ಕಳುಹಿಸಲು `--text -` ಬಳಸಿ:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
