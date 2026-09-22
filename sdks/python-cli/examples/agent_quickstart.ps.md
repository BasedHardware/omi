# د ایجنټونو لپاره omi-cli

> د LLM-پرمخوړونکو هارنسونو (Claude Code، Cursor، ستاسو خپل بوټونه) لپاره عملي لارښود.

## ولې CLI د ایجنټونو لپاره دوستانه دی

* **باثباته JSON تړون.** `--json` یوازې یو معتبر JSON سند stdout ته ورکوي او
  *یوازې* یو JSON سند — هیڅ پرمختګ پیغامونه نشته، هیڅ سپینر نشته. تېروتنې
  stderr ته د `{"error": "...", "detail": "..."}` په بڼه ځي.
* **باثباته وتلو کوډونه.** `0` بریالی / `1` کارول / `2` تصدیق / `3` سرور /
  `4` د کچې محدودیت / `5` ونه موندل شو. ایجنټونه کولای شي پرته له طبیعي-ژبې
  تېروتنو تحلیل چې د دې کوډونو پر بنسټ څانګه وکړي.
* **په هډلیس شرایطو کې هیڅ متقابل پرامپټ نشته.** ویجاړونکو کمانډونو ته
  `--yes` (یا `-y`) ورکړئ؛ د متقابل ننوتلو سکپ کولو لپاره `--api-key` ورکړئ یا
  `OMI_API_KEY` تنظیم کړئ.
* **د بخښنې وړ بیا هڅې چلند.** `429` او `5xx` د ښکاره کېدو دمخه د بیکاف سره
  بیا هڅه کیږي.

## تصدیق (یو ځل، د انسان لخوا)

کاروونکی د Omi وېب اپلیکیشن (`https://app.omi.me` → Developer → API Keys) څخه
ډیو API کیلي ترلاسه کوي او یا هم:

```bash
omi auth login                          # متقابل پیسټ؛ کیلي د shell په تاریخ کې نه پاتې کیږي
# یا
export OMI_API_KEY=omi_dev_...          # لنډمهاله، کانټینر-دوستانه
```

## هغه پنځه کارونه چې ایجنټونه ډېری کوي

### 1. یادونه ولولئ

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. یوه یادونه جوړه کړئ

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. خبرې اترې ولولئ

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. پرانیستې کړنې توکي ولولئ

```bash
omi action-item list --json --open
```

### 5. یو کړنې توکی بشپړ کړئ

```bash
omi action-item complete --json a1b2c3d4
```

## سیمه ایز Desktop API

کله چې Omi Desktop خپل سیمه ایز API افشا کړي، ایجنټونه کولای شي د کلاوډ ډیو API
په کارولو پرته په وسیله کې د سکرین تاریخ، لنډیزونه، SQL او دندې پوښتنه وکړي:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# یا، د لنډمهاله غونډو لپاره:
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

یوازې هغه وخت دندې بشپړې یا حذف کړئ کله چې کاروونکی په روښانه ډول وغواړي:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` سکرین شاټ ډیسک ته لیکي او لا هم
سکریپټونو لپاره stdout ته JSON چاپوي. د سکرین شاټ ID معمولاً د `local search-screen`
یا د `screenshots` جدول په SQL له لارې راځي. که Desktop د `screenshot_pending`،
`screenshot_file_missing` یا `screenshot_chunk_corrupted` په څیر ساختماني ناکامي
راستانه کړي، JSON موډ stderr کې د `reason`، `hint` او `screenshot_id` ساحې ساتي
ترڅو ایجنټونه وکولای شي زوړ ID بیا هڅه وکړي یا دقیق خنډ راپور کړي. بریالي پایلې د
لید وسیلو ته د سپارلو دمخه د `file PATH` سره تایید کړئ.

## د کار شوی بېلګه: Python ایجنټ لوپ

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """omi CLI په JSON موډ کې غږوئ، د نابریالیتوب وتلو کوډونو باندې استثنا پورته کوي."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI په JSON موډ کې ساختماني تېروتنې stderr ته چاپوي:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# ټول پرانیستې کړنې توکي ولولئ او هر هغه څه چې له 30 ورځو ډېر زاړه وي بشپړ په نښه کړئ.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## د کچې محدودیتونو اداره کول

یادونه: 120/ساعت. خبرې اترې: 25/ساعت. ډله ایز جوړښت: 15/ساعت.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # د کچې محدودیت
    err = json.loads(result.stderr)
    # err["detail"] داسې ښکاري: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## لارښوونې

* که ستاسو ایجنټ ډېر Omi حسابونه اداره کوي `--profile <name>` وکاروئ. هر
  پروفایل خپل اسناد او API بیس لري.
* د سیمه ایز بیکنډ ازموینې لپاره `--api-base http://localhost:8080` وکاروئ.
* د یوې چلونې لپاره د پروفایل-سیمه ایز Desktop API تنظیماتو د بیاکتنې لپاره
  `OMI_LOCAL_API_URL` او `OMI_LOCAL_TOKEN` وکاروئ.
* د ډیبګ لپاره `--verbose` وکاروئ — دا stderr ته `METHOD path → status (Ns)` ثبتوي
  پرته له دې چې stdout اغیزمن کړي، نو JSON موډ معتبر پاتې کیږي.
* د مینځپانګې د خبرو اترو ته د پایپ کولو لپاره `--text -` وکاروئ:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
