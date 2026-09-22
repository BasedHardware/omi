# ايجنٽن لاءِ omi-cli

> LLM تي هلندڙ سسٽمز (Claude Code, Cursor, توهان جا ذاتي بوٽس) لاءِ عملي رهنمائي.

## ڇو CLI ايجنٽن لاءِ آسان ۽ سازگار آهي

* **مستقل JSON معاهدو.** `--json` معيار مطابق stdout ڏانهن هڪ صحيح JSON دستاويز ۽
  *صرف* JSON دستاويز موڪلي ٿو — ڪوبه پيش رفت جو پيغام يا لوڊنگ واري متحرڪ تصوير ناهي. غلطيون
  stderr ڏانهن `{"error": "...", "detail": "..."}` طور موڪليون وڃن ٿيون.
* **مستقل نڪرڻ جا ڪوڊ (exit codes).** `0` ڪامياب / `1` استعمال جي غلطي / `2` تصديق جي غلطي /
  `3` سرور جي غلطي / `4` درخواستن جي حد (rate limited) / `5` نه مليو. ايجنٽ قدرتي ٻوليءَ جي
  غلطين جو تجزيو ڪرڻ کان سواءِ سڌو سنئون انهن ڪوڊن جي بنياد تي فيصلو ڪري سگهن ٿا.
* **هيڊ لیس (headless) ماحول ۾ ڪي به پڇا ڳاڇا وارا سوال نه.** تبديلي ڪندڙ ڪمانڊن سان
  `--yes` (يا `-y`) ڏيو؛ باهمي لاگ اِن کي ڇڏڻ لاءِ `--api-key` پاس ڪريو يا `OMI_API_KEY` سيٽ ڪريو.
* **خودڪار ٻيهر ڪوشش وارو رويو.** `429` ۽ `5xx` غلطيون اسڪرين تي ظاهر ٿيڻ کان اڳ وڌندڙ
  وقتي وقفي (backoff) سان پاڻمرادو ٻيهر ڪوشش ڪيون وڃن ٿيون.

## تصديق (صرف هڪ ڀيرو، انسان پاران)

صارف Omi ويب ايپليڪيشن مان ڊولپر API ڪي حاصل ڪري ٿو
(`https://app.omi.me` → Developer → API Keys) ۽ هيٺين مان هڪ چونڊي ٿو:

```bash
omi auth login                          # باهمي پيسٽ؛ ڪي شيل هسٽري ۾ رڪارڊ نٿي ٿئي
# يا
export OMI_API_KEY=omi_dev_...          # عارضي، ڪنٽينرن لاءِ سازگار
```

## پنج بنيادي ڪم جيڪي ايجنٽ اڪثر ڪندا آهن

### 1. يادگيريون پڙهڻ

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. يادگيري ٺاهڻ

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. ڳالهيون پڙهڻ

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. کليل ڪم پڙهڻ

```bash
omi action-item list --json --open
```

### 5. ڪم مڪمل طور نشان لڳائڻ

```bash
omi action-item complete --json a1b2c3d4
```

## مقامي ڊيسڪ ٽاپ API (Local Desktop API)

جڏهن Omi Desktop پنهنجي مقامي API کي چالو ڪري ٿو، ته ايجنٽ ڪلائوڊ ڊولپر API استعمال ڪرڻ
کان سواءِ ڊوائيس اندر اسڪرين جي تاريخ، خلاصا، SQL ڊيٽا ۽ ڪم پڇي سگهن ٿا:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# يا عارضي سيشنز لاءِ:
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

ڪمن کي صرف تڏهن مڪمل يا ختم ڪريو جڏهن صارف واضع طور تي گهر ڪري:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` اسڪرين شاٽ ڊسڪ تي لکي ٿو ۽ اسڪرپٽن
لاءِ stdout تي JSON موڪلڻ جاري رکي ٿو. اسڪرين شاٽ جي سڃاڻپ عام طور تي `local search-screen`
يا `screenshots` ٽيبل تي SQL سوال مان ملي ٿي. جيڪڏهن Desktop ڪا بناوٽي غلطي موڪلي ٿو جيئن ته
`screenshot_pending`, `screenshot_file_missing` يا `screenshot_chunk_corrupted`، ته JSON
موڊ stderr ۾ `reason`, `hint` ۽ `screenshot_id` فيلڊ محفوظ رکي ٿو، جنهن سان ايجنٽ پراڻي ID
سان ٻيهر ڪوشش ڪري سگهن ٿا يا رڪاوٽ کي واضع بيان ڪري سگهن ٿا. ڪامياب نتيجن کي تصويري اوزارن
ڏانهن موڪلڻ کان اڳ `file PATH` سان چڪاسيو.

## عملي مثال: Python ايجنٽ جو دائرو

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """omi CLI کي JSON موڊ ۾ هلائي ٿو، ناڪام ايگزٽ ڪوڊن تي غلطي ظاهر ڪري ٿو."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI JSON موڊ ۾ stderr ڏانهن بناوٽي غلطيون موڪلي ٿو:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# سڀ کليل ڪم پڙهو ۽ جيڪي 30 ڏينهن کان پراڻا هجن انهن کي مڪمل طور نشان لڳايو.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## درخواستن جي حدن کي سنڀالڻ (Rate Limits)

يادگيريون: 120/ڪلاڪ. ڳالهيون: 25/ڪلاڪ. گڏيل ٺاهڻ: 15/ڪلاڪ.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # حد کان وڌيڪ درخواستون
    err = json.loads(result.stderr)
    # err["detail"] هيئن هوندو: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## مفيد ترڪيبون

* جيڪڏهن توهان جو ايجنٽ هڪ کان وڌيڪ Omi کاتا هلائي ٿو، ته `--profile <name>` استعمال ڪريو.
  هر پروفائل جو پنهنجو ذاتي لاگ اِن ڊيٽا ۽ API بنياد هوندو آهي.
* مقامي سرور ٽيسٽنگ لاءِ `--api-base http://localhost:8080` استعمال ڪريو.
* هڪ دفعي هلائڻ لاءِ مقامي Desktop API سيٽنگن کي تبديل ڪرڻ واسطي `OMI_LOCAL_API_URL` ۽
  `OMI_LOCAL_TOKEN` استعمال ڪريو.
* غلطي دور ڪرڻ (debugging) لاءِ `--verbose` استعمال ڪريو — هي stdout تي اثرانداز ٿيڻ
  کان سواءِ stderr تي `METHOD path → status (Ns)` نوٽ ڪري ٿو، تنهنڪري JSON موڊ صحيح رهي ٿو.
* ڳالهه ٻولهه اندر مواد موڪلڻ لاءِ `--text -` استعمال ڪريو:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
