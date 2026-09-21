# omi-cli សម្រាប់ភ្នាក់ងារ (Khmer / ភាសាខ្មែរ)

> ការណែនាំជាក់ស្តែងសម្រាប់ប្រព័ន្ធដែលដំណើរការដោយ LLM (Claude Code, Cursor, បូតផ្ទាល់ខ្លួនរបស់អ្នក)។

## ហេតុអ្វីបានជា CLI ងាយស្រួលសម្រាប់ភ្នាក់ងារ (Why the CLI is agent-friendly)

* **កិច្ចសន្យា JSON ដែលមានស្ថេរភាព (Stable JSON contract)។** `--json` បញ្ចេញឯកសារ JSON ត្រឹមត្រូវទៅកាន់ stdout ហើយ *មានតែ* ឯកសារ JSON ប៉ុណ្ណោះ — គ្មានសារវឌ្ឍនភាព គ្មានរូបវិល។ កំហុសបញ្ជូនទៅ stderr ជា `{"error": "...", "detail": "..."}`។
* **កូដចាកចេញដែលមានស្ថេរភាព (Stable exit codes)។** `0` ជោគជ័យ / `1` កំហុសនៃការប្រើប្រាស់ / `2` កំហុសផ្ទៀងផ្ទាត់ភាពត្រឹមត្រូវ / `3` កំហុសម៉ាស៊ីនបម្រើ / `4` កំណត់អត្រា (rate limited) / `5` រកមិនឃើញ។ ភ្នាក់ងារអាចសម្រេចចិត្តតាមកូដទាំងនេះដោយមិនបាច់ញែកសារភាសាធម្មជាតិ។
* **គ្មានការសួរឆ្លើយឆ្លងក្នុងបរិបទ headless (No interactive prompts in headless contexts)។** បញ្ជូន `--yes` (ឬ `-y`) សម្រាប់ពាក្យបញ្ជាលុប ឬ កែប្រែ; បញ្ជូន `--api-key` ឬ កំណត់ `OMI_API_KEY` ដើម្បីរំលងការចូលប្រើអន្តរកម្ម។
* **ឥរិយាបថសាកល្បងឡើងវិញដោយស្វ័យប្រវត្តិ (Forgiving retry behavior)។** កំហុស `429` និង `5xx` ត្រូវបានសាកល្បងឡើងវិញដោយស្វ័យប្រវត្តិជាមួយ backoff មុនពេលបង្ហាញកំហុស។

## ការផ្ទៀងផ្ទាត់ភាពត្រឹមត្រូវ (Auth - តែម្តងគត់, ដោយមនុស្ស)

អ្នកប្រើប្រាស់ទទួលបាន dev API key ពីគេហទំព័រ Omi (`https://app.omi.me` → Developer → API Keys) ហើយជ្រើសរើសវិធីណាមួយ:

```bash
omi auth login                          # បិទភ្ជាប់អន្តរកម្ម; key មិនស្ថិតក្នុងប្រវត្តិ shell ទេ
# ឬ
export OMI_API_KEY=omi_dev_...          # បណ្តោះអាសន្ន សមស្របសម្រាប់ container
```

## រឿង ៥ យ៉ាងដែលភ្នាក់ងារធ្វើញឹកញាប់បំផុត (The five things agents do most)

### 1. អានការចងចាំ (Read memories)

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. បង្កើតការចងចាំ (Create a memory)

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. អានការសន្ទនា (Read conversations)

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. អានកិច្ចការដែលមិនទាន់រួចរាល់ (Read open action items)

```bash
omi action-item list --json --open
```

### 5. សម្គាល់កិច្ចការថាបានបញ្ចប់ (Mark an action item done)

```bash
omi action-item complete --json a1b2c3d4
```

## Desktop API មូលដ្ឋាន (Local Desktop API)

នៅពេលដែល Omi Desktop បើកដំណើរការ API មូលដ្ឋានរបស់វា ភ្នាក់ងារអាចសាកសួរប្រវត្តិអេក្រង់នៅលើឧបករណ៍ សេចក្តីសង្ខេប SQL និងកិច្ចការនានាដោយមិនបាច់ប្រើប្រាស់ cloud dev API ឡើយ:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# ឬ, សម្រាប់សម័យបណ្តោះអាសន្ន:
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

បញ្ចប់ ឬ លុបកិច្ចការតែនៅពេលដែលអ្នកប្រើប្រាស់ស្នើសុំយ៉ាងច្បាស់លាស់ប៉ុណ្ណោះ:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` នឹងសរសេររូបថតអេក្រង់ទៅក្នុងថាស ហើយនៅតែបោះពុម្ព JSON ទៅកាន់ stdout សម្រាប់ស្គ្រីប។ ជាទូទៅ ID រូបថតអេក្រង់បានមកពី `local search-screen` ឬ SQL លើតារាង `screenshots`។ ប្រសិនបើ Desktop ត្រឡប់កំហុសដែលមានរចនាសម្ព័ន្ធដូចជា `screenshot_pending`, `screenshot_file_missing`, ឬ `screenshot_chunk_corrupted` នោះទម្រង់ JSON នឹងរក្សាវាល `reason`, `hint`, និង `screenshot_id` នៅលើ stderr ដើម្បីឱ្យភ្នាក់ងារអាចសាកល្បងឡើងវិញជាមួយ ID ចាស់ ឬ រាយការណ៍ពីបញ្ហាជាក់លាក់បាន។ ផ្ទៀងផ្ទាត់លទ្ធផលជោគជ័យជាមួយ `file PATH` មុនពេលបញ្ជូនទៅកាន់ឧបករណ៍ vision។

## ឧទាហរណ៍ជាក់ស្តែង: Python agent loop

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Invoke the omi CLI in JSON mode, raising on non-success exit codes."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # The CLI prints structured errors to stderr in JSON mode:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Read all open action items and mark anything older than 30 days complete.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## ការគ្រប់គ្រង Rate Limits (Handling rate limits)

ការចងចាំ: 120/ម៉ោង។ ការសន្ទនា: 25/ម៉ោង។ បង្កើតជាក្រុម: 15/ម៉ោង។

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## គន្លឹះមានប្រយោជន៍ (Tips)

* ប្រើប្រាស់ `--profile <name>` ប្រសិនបើភ្នាក់ងាររបស់អ្នកគ្រប់គ្រងគណនី Omi ច្រើន។ កម្រងព័ត៌មាននីមួយៗមានលិខិតសម្គាល់ និង API base ផ្ទាល់ខ្លួន។
* ប្រើប្រាស់ `--api-base http://localhost:8080` សម្រាប់ការធ្វើតេស្ត backend ក្នុងម៉ាស៊ីន។
* ប្រើប្រាស់ `OMI_LOCAL_API_URL` និង `OMI_LOCAL_TOKEN` ដើម្បីបដិសេធការកំណត់ Desktop API មូលដ្ឋានសម្រាប់ដំណើរការមួយលើក។
* ប្រើប្រាស់ `--verbose` សម្រាប់ការកែកំហុស (debugging) — វានឹងកត់ត្រា `METHOD path → status (Ns)` ទៅកាន់ stderr ដោយមិនប៉ះពាល់ដល់ stdout ដូច្នេះទម្រង់ JSON នៅតែដំណើរការបានត្រឹមត្រូវ។
* សម្រាប់ការបញ្ជូនមាតិកាចូលក្នុងការសន្ទនា (pipe) សូមប្រើ `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
