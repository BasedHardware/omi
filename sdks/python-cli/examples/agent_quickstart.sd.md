# omi-cli ايجنٽن لاءِ (Sindhi / سنڌي)

> LLM تي ٻڌل هارنيسز لاءِ عملي گائيڊ (Claude Code, Cursor, توهان جا پنهنجا بوٽس).

## CLI ايجنٽ-دوست ڇو آهي (Why the CLI is agent-friendly)

* **مستحڪم JSON معاهدو (Stable JSON contract).** `--json` stdout تي هڪ صحيح JSON دستاويز جاري ڪري ٿو ۽ *صرف* هڪ JSON دستاويز — ڪوبه ترقيءَ جو پيغام يا اسپنر ناهي. غلطيون stderr تي `{"error": "...", "detail": "..."}` طور موڪليون وڃن ٿيون.
* **مستحڪم ايگزٽ ڪوڊ (Stable exit codes).** `0` ٺيڪ / `1` استعمال جي غلطي / `2` تصديق / `3` سرور غلطي / `4` ريٽ لمٽ / `5` نه مليو. ايجنٽ قدرتي ٻوليءَ جي غلطين کي پارس ڪرڻ کان سواءِ انهن تي شاخون ٺاهي سگهن ٿا.
* **هيڊليس مقصدن ۾ ڪو به انٽرايڪٽو پرامپٽ ناهي (No interactive prompts in headless contexts).** نقصانڪار ڪمانڊز لاءِ `--yes` (يا `-y`) پاس ڪريو؛ انٽرايڪٽو لاگ ان کي ڇڏڻ لاءِ `--api-key` پاس ڪريو يا `OMI_API_KEY` سيٽ ڪريو.
* **معاف ڪندڙ ٻيهر ڪوشش جو رويو (Forgiving retry behavior).** `429` ۽ `5xx` غلطيون بيڪ آف سان پاڻمرادو ٻيهر ڪوشش ڪيون وڃن ٿيون.

## تصديق (هڪ دفعو، انسان پاران)

صارف Omi ويب ايپ (`https://app.omi.me` → Developer → API Keys) مان هڪ ڊيولپر API چاٻي حاصل ڪري ٿو:

```bash
omi auth login                          # انٽرايڪٽو پيسٽ؛ چاٻي شيل هسٽري ۾ نٿي رهي
# يا
export OMI_API_KEY=omi_dev_...          # عارضي، ڪنٽينر-دوست
```

## پنج شيون جيڪي ايجنٽ سڀ کان وڌيڪ ڪندا آهن

### 1. ياداشتون پڙهو (Read memories)

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. هڪ ياداشت ٺاهيو (Create a memory)

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. ڳالهه ٻولهه پڙهو (Read conversations)

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. کليل عمل جون شيون پڙهو (Read open action items)

```bash
omi action-item list --json --open
```

### 5. عمل جي شيءِ کي مڪمل نشان لڳايو (Mark an action item done)

```bash
omi action-item complete --json a1b2c3d4
```

## مقامي ڊيسڪ ٽاپ API (Local Desktop API)

جڏهن Omi Desktop پنهنجي مقامي API پيش ڪري ٿو، تڏهن ايجنٽ ڪلائوڊ ڊيو API استعمال ڪرڻ کان سواءِ آن-ڊيوائس اسڪرين هسٽري، ريڪيپ، SQL ۽ ٽاسڪ پڇي سگهن ٿا:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# يا، عارضي سيشن لاءِ:
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

صرف تڏهن ٽاسڪ مڪمل يا ختم ڪريو جڏهن صارف واضع طور تي پڇي:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` اسڪرين شاٽ ڊسڪ تي محفوظ ڪري ٿو ۽ اسڪرپٽس لاءِ stdout تي JSON پرنٽ ڪري ٿو. جيڪڏهن Desktop ساخت واري ناڪامي ڏيکاري ٿو (جهڙوڪ `screenshot_pending`, `screenshot_file_missing`, يا `screenshot_chunk_corrupted`), ته JSON موڊ stderr تي `reason`, `hint`, ۽ `screenshot_id` فيلڊ محفوظ رکي ٿو.

## ڪم ڪندڙ مثال: پائٿون ايجنٽ لوپ (Worked example: Python agent loop)

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """JSON موڊ ۾ omi CLI کي ڪال ڪريو، ناڪام ايگزٽ ڪوڊ تي ايڪسيپشن اٿاريو."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# سڀ کليل ايڪشن آئٽمز پڙهو ۽ جيڪو 30 ڏينهن کان پراڻو هجي ان کي مڪمل نشان لڳايو.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## شرح جون حدون سنڀالڻ (Handling rate limits)

ياداشتون: 120/ڪلاڪ. ڳالهه ٻولهه: 25/ڪلاڪ. بيچ تخليق: 15/ڪلاڪ.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # ريٽ لمٽ
    err = json.loads(result.stderr)
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## تجويزون (Tips)

* جيڪڏهن توهان جو ايجنٽ گهڻا Omi اڪائونٽ هلائي ٿو ته `--profile <name>` استعمال ڪريو.
* مقامي بيڪ اينڊ ٽيسٽنگ لاءِ `--api-base http://localhost:8080` استعمال ڪريو.
* ڊيبگنگ لاءِ `--verbose` استعمال ڪريو — هي stdout کي متاثر ڪرڻ کان سواءِ stderr تي لاگ ڏيکاري ٿو.
* مواد کي گفتگو ۾ پائپ ڪرڻ لاءِ `--text -` استعمال ڪريو:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
