# اے آئی ایجنٹس کے لیے omi-cli

> بڑے لینگویج ماڈل پر مبنی ماحول کے لیے عملی رہنمائی (Claude Code، Cursor، اور کسٹم بوٹس)۔

## یہ CLI ایجنٹس کے لیے کیوں موزوں ہے

* **مستحکم JSON معاہدہ:** `--json` فلیگ stdout پر درست JSON دستاویزات آؤٹ پٹ کرتا ہے اور *صرف* JSON — بغیر کسی اسٹیٹس میسج یا لوڈنگ اسپنر کے۔ خرابیاں stderr پر `{"error": "...", "detail": "..."}` فارمیٹ میں بھیجی جاتی ہیں۔
* **مستحکم ایگزٹ کوڈز:** `0` کامیابی / `1` استعمال کی خرابی / `2` تصدیق کی ناکامی / `3` سرور کی خرابی / `4` شرح کی حد سے تجاوز / `5` نہیں ملا۔ ایجنٹ کسی قدرتی زبان کو پارس کیے بغیر براہ راست ایگزٹ کوڈز کے ذریعے برانچنگ کر سکتے ہیں۔
* **ہیڈ لیس موڈ میں کوئی انٹرایکٹو پرامپٹ نہیں:** نقصان دہ احکامات کے لیے `--yes` (یا `-y`) دیں؛ براؤزر لاگ ان سے بچنے کے لیے `--api-key` پاس کریں یا `OMI_API_KEY` سیٹ کریں۔
* **خودکار دوبارہ کوشش کا رویہ:** غلطی واپس کرنے سے پہلے `429` اور `5xx` ردعمل خود بخود تاخیر کے ساتھ دوبارہ کوشش کیے جاتے ہیں۔

## تصدیق (صارف کی طرف سے ایک بار)

صارف Omi ویب ایپ سے ڈویلپر API کلید حاصل کرتا ہے
(`https://app.omi.me` → Developer → API Keys)، پھر چلاتا ہے:

```bash
omi auth login                          # چسپاں کریں؛ شیل ہسٹری میں محفوظ نہیں ہوتا
# یا
export OMI_API_KEY=omi_dev_...          # عارضی، کنٹینرز اور CI/CD کے لیے بہترین
```

## ایجنٹس کے پانچ سب سے عام آپریشنز

### ۱۔ یادیں پڑھنا (Memories)

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### ۲۔ نئی یاد بنانا

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### ۳۔ گفتگو پڑھنا

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### ۴۔ حل طلب کام پڑھنا (Action Items)

```bash
omi action-item list --json --open
```

### ۵۔ کام کی تکمیل کا نشان لگانا

```bash
omi action-item complete --json a1b2c3d4
```

## مقامی ڈیسک ٹاپ API (Local Desktop API)

جب Omi Desktop مقامی API کو فعال کرتا ہے، تو ایجنٹس کلاؤڈ کو کال کیے بغیر مقامی طور پر اسکرین ہسٹری اور کاموں کو تلاش کر سکتے ہیں:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# یا عارضی سیشن کے لیے:
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

صرف اسی صورت میں کام مکمل یا حذف کریں جب صارف واضح طور پر درخواست کرے:

صرف اسی صورت میں کام مکمل یا حذف کریں جب صارف واضح طور پر درخواست کرے:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` اسکرین شاٹ کو ڈسک پر محفوظ کرتا ہے اور اسکرپٹس کے لیے stdout پر JSON پرنٹ کرتا ہے۔ اسکرین شاٹ کی ID عام طور پر `local search-screen` یا `screenshots` ٹیبل پر SQL کے ذریعے حاصل ہوتی ہے۔ اگر Desktop کوئی ساختی خرابی واپس کرے جیسے `screenshot_pending`، `screenshot_file_missing`، یا `screenshot_chunk_corrupted`، تو JSON موڈ stderr پر `reason`، `hint`، اور `screenshot_id` فیلڈز کو برقرار رکھتا ہے تاکہ ایجنٹس پرانی ID کے ساتھ دوبارہ کوشش کر سکیں یا اصل رکاوٹ کی اطلاع دے سکیں۔ وژن ٹولز کو پاس کرنے سے پہلے `file PATH` کے ساتھ کامیاب آؤٹ پٹ کی توثیق کریں۔

## عملی مثال: پائتھن (Python) ایجنٹ لوپ

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

## شرح کی حد کا انتظام (Handling rate limits)

یادیں: 120 فی گھنٹہ۔ گفتگو: 25 فی گھنٹہ۔ بیچ تخلیق: 15 فی گھنٹہ۔

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## مفید مشورے (Tips)

* اگر آپ کا ایجنٹ متعدد Omi اکاؤنٹس چلاتا ہے تو `--profile <name>` استعمال کریں۔ ہر پروفائل کی اپنی اسناد اور API بیس ہوتی ہے۔
* لوکل بیک اینڈ ٹیسٹنگ کے لیے `--api-base http://localhost:8080` استعمال کریں۔
* ایک ہی رن کے لیے پروفائل لوکل ڈیسک ٹاپ API سیٹنگز کو اوور رائیڈ کرنے کے لیے `OMI_LOCAL_API_URL` اور `OMI_LOCAL_TOKEN` استعمال کریں۔
* ڈیبگنگ کے لیے `--verbose` استعمال کریں — یہ stdout کو متاثر کیے بغیر stderr پر `METHOD path → status (Ns)` لاگ کرتا ہے، لہذا JSON موڈ درست رہتا ہے۔
* گفتگو میں مواد کو پائپ کرنے کے لیے، `--text -` استعمال کریں:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
