# ལས་ཚབ་ (Agents) གི་དོན་ལུ་ omi-cli

> LLM གིས་བཀོལ་སྤྱོད་འབད་མི་རིམ་ལུགས་ (Claude Code, Cursor, ཁྱོད་རའི་བོཊ་ཚུ་) གི་དོན་ལུ་ ལག་ལེན་དངོས་ཀྱི་ལམ་སྟོན།

## ག་ཅི་སྦེ་ CLI འདི་ ལས་ཚབ་ཚུ་གི་དོན་ལུ་ འོས་འབབ་ཡོདཔ་སྨོ

* **བརྟན་ཏོག་ཏོ་ཡོད་པའི་ JSON ཆིངས་ཡིག** `--json` གིས་ stdout ལུ་ ནུས་ཅན་ JSON ཡིག་ཆ་ཅིག་དང་
  JSON ཡིག་ཆ་ *རྐྱངམ་ཅིག་* ཕྱིར་བཏོན་འབདཝ་ཨིན — ཡར་རྒྱས་ཀྱི་འཕྲིན་དོན་དང་ སྐོར་ར་རྐྱབ་མི་ཨེ་ནི་མེ་ཤཱན་མེད།
  འཛོལ་བ་ཚུ་ stderr ལུ་ `{"error": "...", "detail": "..."}` སྦེ་འགྱོཝ་ཨིན།
* **བརྟན་ཏོག་ཏོ་ཡོད་པའི་ ཕྱིར་ཐོན་ཨང་རྟགས་ (exit codes)།** `0` ལེགས་ཤོམ / `1` ལག་ལེན་འཛོལ་བ / `2` ངོས་འཛིན /
  `3` སར་བར་འཛོལ་བ / `4` ཞུ་བ་ཚད་ལས་བརྒལ་བ (rate limited) / `5` མ་ཐོབ། ལས་ཚབ་ཚུ་གིས་
  རང་བཞིན་སྐད་ཡིག་གི་འཛོལ་བ་ཚུ་ དབྱེ་ཞིབ་མ་འབད་བར་ ཨང་རྟགས་འདི་ཚུ་ལུ་གཞི་བཞག་སྟེ་ ཐག་གཅོད་འབད་ཚུགས།
* **headless གནས་སྟངས་ནང་ ཕན་ཚུན་འབྲེལ་བའི་དྲི་བ་མེདཔ།** འགྱུར་བཅོས་འབད་མི་བཀོད་རྒྱ་ཚུ་ལུ་
  `--yes` (ཡང་ན་ `-y`) བྱིན; ཕན་ཚུན་འབྲེལ་བའི་ནང་འཛུལ་སྤང་ནིའི་དོན་ལུ་ `--api-key` བྱིན་ ཡང་ན་ `OMI_API_KEY` གཞི་སྒྲིག་འབད།
* **ལོག་འབད་རྩོལ་བསྐྱེད་ནིའི་གནས་སྟངས།** `429` དང་ `5xx` འཛོལ་བ་ཚུ་ མ་སྟོན་པའི་ཧེ་མ་
  རིམ་གྱིས་བསྒུག་སྟེ་ (backoff) རང་བཞིན་གྱིས་ ལོག་འབད་རྩོལ་བསྐྱེདཔ་ཨིན།

## ངོས་འཛིན་བདེན་དཔྱད (མི་གིས་ ཚར་གཅིག་རྐྱངམ་ཅིག་འབད་ནི)

ལག་ལེན་པ་གིས་ Omi ཝེབ་གློག་རིམ་ནང་ལས་ བཟོ་སྐྲུན་པའི་ API ལྡེ་མིག་ལེན་ཏེ་
(`https://app.omi.me` → Developer → API Keys) གཤམ་གསལ་ཚུ་ལས་ གཅིག་གདམ་ཁ་རྐྱབ་ཨིན:

```bash
omi auth login                          # ཕན་ཚུན་འབྲེལ་བའི་སྦྱར་ནི; ལྡེ་མིག་ shell བྱུང་རབས་ནང་མི་ལུས
# ཡང་ན
export OMI_API_KEY=omi_dev_...          # གནས་སྐབས་ཀྱི, container ལུ་འོས་འབབ་ཡོདཔ
```

## ལས་ཚབ་ཚུ་གིས་ མང་ཤོས་འབད་མི་ དོན་ཚན་ལྔ

### 1. དྲན་ཚུལ་ཚུ་ལྷག་ནི

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. དྲན་ཚུལ་གསར་བཟོ་འབད་ནི

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. ཁ་བཤད་ཚུ་ལྷག་ནི

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. ཁ་ཕྱེ་ཡོད་པའི་ ལས་འགུལ་ཚུ་ལྷག་ནི

```bash
omi action-item list --json --open
```

### 5. ལས་འགུལ་ཅིག་ མཇུག་བསྡུ་ཡོདཔ་སྦེ་ རྟགས་བཀལ་ནི

```bash
omi action-item complete --json a1b2c3d4
```

## ཉེ་གནས་ ཌེཀསི་ཊོཔ་ API (Local Desktop API)

Omi Desktop གིས་ ཁོང་རའི་ ཉེ་གནས་ API འདི་ ལྕོགས་ཅན་བཟོཝ་ད་ ལས་ཚབ་ཚུ་གིས་ སྤྲིན་ཚོགས་ API
ལག་ལེན་མ་འཐབ་པར་ ཅ་ཆས་ནང་འཁོད་ཀྱི་ གསལ་ཞལ་བྱུང་རབས, བཅུད་དོན, SQL གནས་སྡུད་ དང་ ལས་འགུལ་ཚུ་ འདྲི་རྩད་འབད་ཚུགས:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# ཡང་ན་ གནས་སྐབས་ཀྱི་དོན་ལུ་:
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

ལག་ལེན་པ་གིས་ གསལ་ཏོག་ཏོ་སྦེ་ ཞུ་བ་འབདཝ་ད་རྐྱངམ་ཅིག་ ལས་འགུལ་ཚུ་ མཇུག་བསྡུ་ ཡང་ན་ བཏོན་གཏང་:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` གིས་ གསལ་ཞལ་པར་འདི་ ཌིཀསི་ནང་འབྲིཝ་ཨིནམ་དང་
ཡིག་ཚགས་ཚུ་གི་དོན་ལུ་ stdout ལུ་ JSON ཕྱིར་བཏོན་འབད་དེ་རང་ལུསཔ་ཨིན། གསལ་ཞལ་པར་གྱི་ ID འདི་
སྤྱིར་བཏང་ `local search-screen` ཡང་ན་ `screenshots` ཐིག་ཁྲམ་ལས་ SQL འདྲི་རྩད་ཐོག་ལས་ཐོབཔ་ཨིན།
གལ་སྲིད་ Desktop གིས་ `screenshot_pending`, `screenshot_file_missing` ཡང་ན་ `screenshot_chunk_corrupted`
བཟུམ་མའི་ བཀོད་སྒྲིག་ཅན་གྱི་མ་འགྲུབ་པ་སླར་ལོག་འབད་བ་ཅིན་ JSON ཐབས་ལམ་གྱིས་ stderr ཐོག་ལུ་ `reason`, `hint`
དང་ `screenshot_id` ས་སྒོ་ཚུ་ ཉར་ཚགས་འབདཝ་ཨིན, དེ་གིས་སྦེ་ ལས་ཚབ་ཚུ་གིས་ ID རྙིངམ་ཐོག་ལས་ ལོག་འབད་རྩོལ་བསྐྱེད་ཚུགས།
གྲུབ་འབྲས་ལེགས་ཤོམ་ཚུ་ མཐོང་སྣང་ལག་ཆས་ལུ་མ་བཏང་པའི་ཧེ་མ་ `file PATH` ཐོག་ལས་ བདེན་དཔྱད་འབད།

## ལག་ལེན་གྱི་དཔེ: Python ལས་ཚབ་འཁོར་རིམ

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """JSON ཐབས་ལམ་ཐོག་ omi CLI ལུ་བོས་ཏེ་ མ་འགྲུབ་པའི་སྐབས་ འཛོལ་བ་སྟོན།"""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI གིས་ JSON ཐབས་ལམ་ནང་ stderr ལུ་ བཀོད་སྒྲིག་ཅན་གྱི་འཛོལ་བ་སྟོན:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# ཁ་ཕྱེ་ཡོད་པའི་ལས་འགུལ་ཚུ་ལྷག་སྟེ་ ཉིནམ་ ༣༠ ལས་ལྷག་མི་ཚུ་ མཇུག་བསྡུ་ཡོདཔ་སྦེ་ རྟགས་བཀལ།
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## ཞུ་བའི་ཚད་འཛིན (Rate Limits)

དྲན་ཚུལ: ༡༢༠/ཆུ་ཚོད། ཁ་བཤད: ༢༥/ཆུ་ཚོད། རུ་ཁག་གསར་བཟོ: ༡༥/ཆུ་ཚོད།

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # ཚད་ལས་བརྒལ་སོང་ཡོདཔ
    err = json.loads(result.stderr)
    # err["detail"] འདི་བཟུམ་སྦེ་འོང: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## ཕན་ཐོགས་ཅན་གྱི་ བསླབ་བྱ་ཚུ

* ཁྱོད་ཀྱི་ལས་ཚབ་ཀྱིས་ Omi རྩིས་ཁྲ་མང་རབས་ཅིག་འཛིན་སྐྱོང་འབདཝ་ཨིན་པ་ཅིན་ `--profile <name>` ལག་ལེན་འཐབ།
  གསལ་སྡུད་རེ་རེ་ལུ་ རང་སོའི་ངོས་འཛིན་དཔང་ཡིག་དང་ API ཡོད།
* ཉེ་གནས་ རྒྱབ་སྐྱོར་བརྟག་ཞིབ་ཀྱི་དོན་ལུ་ `--api-base http://localhost:8080` ལག་ལེན་འཐབ།
* ཚར་གཅིག་འཁོར་བསྐྱོད་འབད་ནིའི་དོན་ལུ་ `OMI_LOCAL_API_URL` དང་ `OMI_LOCAL_TOKEN` ལག་ལེན་འཐབ་སྟེ་
  གསལ་སྡུད་ཀྱི་ ཉེ་གནས་ Desktop API གཞི་སྒྲིག་ཚུ་ མེདཔ་བཟོ།
* འཛོལ་བ་སེལ་ནིའི་དོན་ལུ་ `--verbose` ལག་ལེན་འཐབ — དེ་གིས་ stdout ལུ་ཐོ་ཕོག་མེད་པར་ stderr ལུ་
  `METHOD path → status (Ns)` ཐོ་བཀོད་འབདཝ་ལས་ JSON ཐབས་ལམ་འདི་ ནུས་ཅན་སྦེ་རང་ལུསཔ་ཨིན།
* ཁ་བཤད་ནང་ལུ་ ནང་དོན་ཚུ་ མཐུད་ནིའི་དོན་ལུ་ `--text -` ལག་ལེན་འཐབ:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
