# ایجنٹس کے لیے omi-cli

> LLM سے چلنے والے ایجنٹ ماحول (Claude Code، Cursor، آپ کے اپنے بوٹس) کے لیے عملی رہنما۔

## CLI ایجنٹ کے لیے موزوں کیوں ہے

* **مستحکم JSON معاہدہ۔** `--json` stdout پر ایک درست JSON دستاویز بھیجتا ہے اور
  *صرف* ایک JSON دستاویز — کوئی پیش رفت پیغام نہیں، کوئی اسپنر نہیں۔ غلطیاں
  stderr پر `{"error": "...", "detail": "..."}` کی شکل میں جاتی ہیں۔
* **مستحکم ایکزٹ کوڈز۔** `0` کامیابی / `1` غلط استعمال / `2` تصدیق /
  `3` سرور / `4` ریٹ محدود / `5` نہیں ملا۔ ایجنٹس قدرتی زبان کی غلطیوں کو
  پارس کیے بغیر ان کوڈز پر شرطیں بنا سکتے ہیں۔
* **ہیڈ لیس ماحول میں کوئی متعامل پرامپٹ نہیں۔** تباہ کن کمانڈز کے لیے
  `--yes` (یا `-y`) دیں؛ متعامل لاگ اِن سے بچنے کے لیے `--api-key` دیں
  یا `OMI_API_KEY` سیٹ کریں۔
* **روادار دوبارہ کوشش کا رویہ۔** `429` اور `5xx` سامنے آنے سے پہلے
  بیک آف کے ساتھ دوبارہ کوشش کی جاتی ہے۔

## تصدیق (ایک بار، انسان کے ذریعے)

صارف Omi ویب ایپ (`https://app.omi.me` → Developer → API Keys) سے ڈیو API کلید
حاصل کرتا ہے اور ان میں سے کوئی ایک طریقہ اختیار کرتا ہے:

```bash
omi auth login                          # متعامل پیسٹ؛ کلید shell ہسٹری میں نہیں رہتی
# یا
export OMI_API_KEY=omi_dev_...          # عارضی، کنٹینر کے لیے موزوں
```

## پانچ کام جو ایجنٹ سب سے زیادہ کرتے ہیں

### 1. یادیں پڑھیں

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. یاد بنائیں

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. گفتگوئیں پڑھیں

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. کھلے ایکشن آئٹمز پڑھیں

```bash
omi action-item list --json --open
```

### 5. ایکشن آئٹم مکمل کریں

```bash
omi action-item complete --json a1b2c3d4
```

## لوکل ڈیسک ٹاپ API

جب Omi Desktop اپنا لوکل API ظاہر کرتا ہے، تو ایجنٹس کلاؤڈ ڈیو API استعمال کیے
بغیر ڈیوائس کی اسکرین ہسٹری، خلاصے، SQL اور ٹاسکس سے استفسار کر سکتے ہیں:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# یا، عارضی سیشنز کے لیے:
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

ٹاسکس صرف اسی صورت میں مکمل یا حذف کریں جب صارف واضح طور پر کہے:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` اسکرین شاٹ کو ڈسک پر لکھتا ہے
اور اسکرپٹس کے لیے stdout پر JSON بھی پرنٹ کرتا ہے۔ اسکرین شاٹ آئی ڈی عموماً
`local search-screen` یا `screenshots` ٹیبل پر SQL سے آتی ہے۔ اگر Desktop
`screenshot_pending`، `screenshot_file_missing` یا `screenshot_chunk_corrupted`
جیسی ساختی ناکامی واپس کرے، تو JSON موڈ stderr پر `reason`، `hint` اور
`screenshot_id` فیلڈز محفوظ رکھتا ہے تاکہ ایجنٹس پرانی آئی ڈی کے ساتھ دوبارہ
کوشش کر سکیں یا درست رکاوٹ کی نشان دہی کر سکیں۔ کامیاب آؤٹ پٹ کو وژن ٹولز کو
بھیجنے سے پہلے `file PATH` سے جانچ لیں۔

## عملی مثال: Python ایجنٹ لوپ

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """omi CLI کو JSON موڈ میں چلاتا ہے، ناکام ایکزٹ کوڈز پر استثنا اٹھاتا ہے۔"""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI JSON موڈ میں stderr پر ساختی غلطیاں پرنٹ کرتا ہے:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# تمام کھلے ایکشن آئٹمز پڑھیں اور 30 دن سے پرانے مکمل کریں۔
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## ریٹ حدود سے نمٹنا

یادیں: 120/گھنٹہ۔ گفتگوئیں: 25/گھنٹہ۔ بیچ تخلیقات: 15/گھنٹہ۔

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # ریٹ محدود
    err = json.loads(result.stderr)
    # err["detail"] کچھ ایسا ہوتا ہے: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## تجاویز

* اگر آپ کا ایجنٹ ایک سے زیادہ Omi اکاؤنٹس سنبھالتا ہے تو `--profile <name>`
  استعمال کریں۔ ہر پروفائل کے اپنے اسناد اور API بیس ہوتے ہیں۔
* لوکل بیک اینڈ ٹیسٹنگ کے لیے `--api-base http://localhost:8080` استعمال کریں۔
* ایک رن کے لیے پروفائل کے لوکل Desktop API سیٹنگز اوور رائیڈ کرنے کے لیے
  `OMI_LOCAL_API_URL` اور `OMI_LOCAL_TOKEN` استعمال کریں۔
* ڈیبگنگ کے لیے `--verbose` استعمال کریں — یہ stderr پر
  `METHOD path → status (Ns)` لاگ کرتا ہے، stdout کو متاثر نہیں کرتا، لہٰذا
  JSON موڈ درست رہتا ہے۔
* پائپ کے ذریعے گفتگو میں مواد بھیجنے کے لیے `--text -` استعمال کریں:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
