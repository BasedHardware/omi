# omi-cli សម្រាប់ភ្នាក់ងារ (Agents)

> ការណែនាំជាក់ស្តែងសម្រាប់ប្រព័ន្ធដែលជំរុញដោយ LLM (Claude Code, Cursor, bot ផ្ទាល់ខ្លួនរបស់អ្នក)។

## ហេតុអ្វីបានជា CLI ងាយស្រួលសម្រាប់ភ្នាក់ងារ

* **កិច្ចសន្យា JSON មានស្ថេរភាព។** `--json` បញ្ចេញឯកសារ JSON ត្រឹមត្រូវទៅកាន់ stdout
  ហើយមាន *តែ* ឯកសារ JSON ប៉ុណ្ណោះ — គ្មានសារដំណើរការ គ្មានចលនាវិលឡើយ។ កំហុសទៅកាន់
  stderr ជាទម្រង់ `{"error": "...", "detail": "..."}`។
* **លេខកូដចេញ (exit codes) មានស្ថេរភាព។** `0` ជោគជ័យ / `1` ការប្រើប្រាស់ខុស / `2` ការផ្ទៀងផ្ទាត់ /
  `3` កំហុសម៉ាស៊ីនបម្រើ / `4` លើសកំណត់សំណើ (rate limited) / `5` រកមិនឃើញ។ ភ្នាក់ងារអាចបែងចែក
  តាមលេខកូដទាំងនេះដោយមិនចាំបាច់ញែកកំហុសភាសាធម្មជាតិឡើយ។
* **គ្មានសារសួរអន្តរកម្មនៅក្នុងបរិបទ headless។** បញ្ជូន `--yes` (ឬ `-y`) ទៅពាក្យបញ្ជាដែលផ្លាស់ប្តូរទិន្នន័យ;
  បញ្ជូន `--api-key` ឬកំណត់ `OMI_API_KEY` ដើម្បីរំលងការចូលអន្តរកម្ម។
* **យន្តការសាកល្បងឡើងវិញដោយស្វ័យប្រវត្តិ។** កំហុស `429` និង `5xx` ត្រូវបានសាកល្បងឡើងវិញដោយការបន្ថយល្បឿន
  (backoff) មុនពេលបង្ហាញឡើង។

## ការផ្ទៀងផ្ទាត់ (ម្តងគត់ ដោយមនុស្ស)

អ្នកប្រើប្រាស់ទទួលបាន developer API key ពីកម្មវិធីគេហទំព័រ Omi
(`https://app.omi.me` → Developer → API Keys) ហើយជ្រើសរើស៖

```bash
omi auth login                          # បិទភ្ជាប់អន្តរកម្ម; សោមិនស្ថិតនៅក្នុងប្រវត្តិសែលទេ
# ឬ
export OMI_API_KEY=omi_dev_...          # បណ្តោះអាសន្ន ងាយស្រួលសម្រាប់ container
```

## រឿងប្រាំយ៉ាងដែលភ្នាក់ងារធ្វើញឹកញាប់បំផុត

### 1. អានការចងចាំ

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. បង្កើតការចងចាំ

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. អានការសន្ទនា

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. អានកិច្ចការដែលមិនទាន់រួចរាល់

```bash
omi action-item list --json --open
```

### 5. កំណត់សម្គាល់កិច្ចការថារួចរាល់

```bash
omi action-item complete --json a1b2c3d4
```

## API មូលដ្ឋានលើកុំព្យូទ័រ (Local Desktop API)

នៅពេល Omi Desktop បើកដំណើរការ API មូលដ្ឋានរបស់វា ភ្នាក់ងារអាចសាកសួរប្រវត្តិអេក្រង់លើឧបករណ៍
សេចក្តីសង្ខេប SQL និងកិច្ចការដោយមិនចាំបាច់ប្រើ cloud developer API ឡើយ៖

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# ឬសម្រាប់សម័យបណ្តោះអាសន្ន៖
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

បំពេញ ឬលុបកិច្ចការតែនៅពេលដែលអ្នកប្រើប្រាស់ស្នើសុំយ៉ាងច្បាស់លាស់ប៉ុណ្ណោះ៖

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` សរសេររូបថតអេក្រង់ទៅក្នុងថាស និងនៅតែបង្ហាញ
JSON ទៅ stdout សម្រាប់ស្គ្រីប។ លេខសម្គាល់រូបថតអេក្រង់ជាទូទៅបានមកពី `local search-screen` ឬ
សំណួរ SQL លើតារាង `screenshots`។ ប្រសិនបើ Desktop ត្រឡប់ការបរាជ័យដែលមានរចនាសម្ព័ន្ធដូចជា
`screenshot_pending`, `screenshot_file_missing` ឬ `screenshot_chunk_corrupted` នោះទម្រង់ JSON
រក្សាទុកវាល `reason`, `hint` និង `screenshot_id` នៅលើ stderr ដូច្នេះភ្នាក់ងារអាចសាកល្បងលេខសម្គាល់ចាស់ឡើងវិញ
ឬរាយការណ៍ពីឧបសគ្គជាក់លាក់។ ផ្ទៀងផ្ទាត់លទ្ធផលជោគជ័យជាមួយ `file PATH` មុនពេលបញ្ជូនទៅឧបករណ៍មើលរូបភាព។

## ឧទាហរណ៍ជាក់ស្តែង៖ វដ្តភ្នាក់ងារ Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """ហៅ omi CLI ក្នុងទម្រង់ JSON ដោយបង្កើតកំហុសលើលេខកូដមិនជោគជ័យ។"""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI បង្ហាញកំហុសដែលមានរចនាសម្ព័ន្ធទៅ stderr ក្នុងទម្រង់ JSON៖
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# អានកិច្ចការដែលបើកទាំងអស់ ហើយសម្គាល់កិច្ចការដែលលើសពី 30 ថ្ងៃថារួចរាល់។
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## ការគ្រប់គ្រងដែនកំណត់សំណើ (Rate Limits)

ការចងចាំ៖ 120/ម៉ោង។ ការសន្ទនា៖ 25/ម៉ោង។ ការបង្កើតជាបណ្តុំ៖ 15/ម៉ោង។

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # លើសដែនកំណត់សំណើ
    err = json.loads(result.stderr)
    # err["detail"] មានទម្រង់ដូចជា: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## គន្លឹះមានប្រយោជន៍

* ប្រើ `--profile <name>` ប្រសិនបើភ្នាក់ងាររបស់អ្នកគ្រប់គ្រងគណនី Omi ច្រើន។
  កម្រងព័ត៌មាននីមួយៗមានព័ត៌មានសម្ងាត់ និងមូលដ្ឋាន API ផ្ទាល់ខ្លួន។
* ប្រើ `--api-base http://localhost:8080` សម្រាប់ការធ្វើតេស្តផ្នែកខាងក្រោយក្នុងស្រុក។
* ប្រើ `OMI_LOCAL_API_URL` និង `OMI_LOCAL_TOKEN` ដើម្បីជំនួសការកំណត់ API លើតុក្នុងស្រុកសម្រាប់មួយដង។
* ប្រើ `--verbose` សម្រាប់ការបំបាត់កំហុស — វាកត់ត្រា `METHOD path → status (Ns)` ទៅកាន់ stderr
  ដោយមិនប៉ះពាល់ដល់ stdout ដូច្នេះទម្រង់ JSON នៅតែត្រឹមត្រូវ។
* សម្រាប់ការបញ្ជូនមាតិកាទៅក្នុងការសន្ទនា សូមប្រើ `--text -`៖
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
