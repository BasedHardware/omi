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

```bash
omi --json local task complete task_1
```
