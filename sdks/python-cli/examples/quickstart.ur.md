# omi-cli فوری آغاز گائیڈ (اردو)

> ٹرمینل سے Omi کے ساتھ کام کرنے کی عملی گائیڈ۔ انسانوں اور AI ایجنٹس — دونوں کے لیے موزوں۔

`omi-cli` [Omi Developer API](https://docs.omi.me/doc/developer/cli/introduction) کا باضابطہ کمانڈ لائن انٹرفیس ہے۔
یہ آپ کو Omi کے چار بنیادی ذرائع — یاداتیں (memories)، مکالمات (conversations)، ایکشن آئٹمز (action items) اور اہداف (goals) — مؤثر طریقے سے منظم کرنے اور اسکرپٹ کے قابل بناتا ہے۔

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **باضابطہ دستاویزات:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **سورس کوڈ:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

> **نوٹ:** [examples/README.md](README.md) میں انگریزی README بطور بنیادی حوالہ (authoritative) برقرار ہے۔ یہ گائیڈ اردو میں ادارتی ترجمہ ہے۔

---

## 1. انسٹالیشن

توصیہ شدہ طریقہ `pipx` ہے، کیونکہ یہ انحصارات (dependencies) کو الگ رکھتا ہے۔

```bash
# توصیہ شدہ: pipx کے ذریعے انسٹال کریں
pipx install omi-cli

# یا pip استعمال کریں
pip install omi-cli
```

> **اہم: پیکج کے نام اور کمانڈ کے نام میں فرق**
> * انسٹال ہونے والے Python پیکج کا نام **`omi-cli`** ہے (صرف `omi` پیکج ایک غیر متعلقہ پیکج ہے)۔
> * انسٹالیشن کے بعد ٹرمینل میں چلائی جانے والی کمانڈ کا نام **`omi`** ہے۔

انسٹالیشن کے بعد، ورژن اور مدد چیک کریں:

```bash
omi --version
omi --help
```

---

## 2. تصدیق (Authentication)

`omi-cli` تصدیق کے دو طریقے سپورٹ کرتا ہے۔

| طریقہ | بنیادی استعمال | کمانڈ کی مثال |
| :--- | :--- | :--- |
| **ڈویلپر API کی (`omi_dev_*`)** | CI/CD، آٹومیشن اسکرپٹس، AI ایجنٹس | `omi auth login --api-key ...` یا ماحول کا متغیر |
| **براؤزر OAuth (Google/Apple)** | ڈویلپر کا PC / لیپ ٹاپ | `omi auth login --browser` |

### انٹرایکٹو لاگ اِن
بغیر کسی آپشن کے چلائیں تاکہ براؤزر لاگ اِن یا API کی درج کروانے میں سے انتخاب کیا جا سکے:

```bash
omi auth login
# 1) Browser — Google یا Apple اکاؤنٹ سے لاگ اِن کریں (انسانوں کے لیے)
# 2) API key — app.omi.me سے ڈویلپر کی پیسٹ کریں (ایجنٹس/CI کے لیے)
```

### براہ راست براؤزر کے ذریعے لاگ اِن
```bash
omi auth login --browser
```

### API کی استعمال کرنا
[app.omi.me](https://app.omi.me) کے سیکشن "Developer → API Keys" سے ڈویلپر کی حاصل کریں، پھر اسے سیٹ کریں:

```bash
# کمانڈ کے ذریعے سیٹ کریں
omi auth login --api-key omi_dev_...

# یا ماحول کے متغیر کے ذریعے (CI/CD اور کنٹینرز کے لیے بہترین)
export OMI_API_KEY=omi_dev_...
```

### تصدیقی حالت چیک کرنا
* `omi auth status`: مقامی طور پر محفوظ شدہ تصدیقی پروفائل، ماسک شدہ ٹوکن اور ختم ہونے کی تاریخ دکھاتا ہے (آف لائن کام کرتا ہے)۔
* `omi auth whoami`: تصدیق کی ایک اصل درخواست Omi سرور کو بھیج کر یقینی بناتا ہے کہ اسناد درست ہیں (نیٹ ورک کنکشن درکار ہے)۔

```bash
omi auth status
omi auth whoami
```

لاگ آؤٹ کے لیے:
```bash
omi auth logout
```

---

## 3. بنیادی استعمال

آپ Omi کے چار بنیادی ذرائع کو فہرست اور منظم کر سکتے ہیں۔

### یاداتیں (Memories)
نظام کی سیکھی ہوئی حقیقتیں اور معلومات منظم کریں۔

```bash
# یادات کی فہرست بنائیں
omi memory list

# نئی یاد بنائیں
omi memory create "The user prefers dark mode" --category lifestyle

# کسی مخصوص یاد کی تفصیلات دیکھیں
omi memory get <MEMORY_ID>
```

### مکالمات (Conversations)
پہننے والے ڈیوائس یا ایپ سے حاصل شدہ آڈیو/ٹیکسٹ مکالمات کی تاریخ۔

```bash
# 5 تازہ ترین مکالمات حاصل کریں
omi conversation list --limit 5

# مکالمے کی تفصیلات اور ٹرانسکرپٹ دیکھیں
omi conversation get <CONVERSATION_ID> --include-transcript
```

### ایکشن آئٹمز (Action Items)
مکالمات سے خودکار طور پر نکالے گئے کام اور فالو اپ آئٹمز۔

```bash
# صرف غیر مکمل ایکشن آئٹمز کی فہرست
omi action-item list --open

# ایکشن آئٹم کو مکمل شدہ کے طور پر نشان زد کریں
omi action-item complete <ACTION_ITEM_ID>
```

### اہداف (Goals)
اپنے اہداف اور پیش رفت کو ٹریک کریں۔

```bash
# اہداف کی فہرست
omi goal list
```

---

## 4. اسکرپٹنگ اور JSON آؤٹ پٹ (`--json`)

`omi-cli` بطور فطری JSON آؤٹ پٹ سپورٹ کرتا ہے۔ `jq` یا Python اسکرپٹ کے ساتھ استعمال کرتے وقت `--json` کو **گلوبل آپشن** کے طور پر رکھیں — یعنی **سب کمانڈ سے پہلے**۔

```bash
# JSON میں یادات کی فہرست حاصل کریں اور id اور مواد نکالیں
omi --json memory list | jq '.[] | {id, content, category}'

# 5 تازہ ترین مکالمات کے عنوانات حاصل کریں
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# غیر مکمل ایکشن آئٹمز کی فہرست
omi --json action-item list --open | jq '.'
```

> **اہم:** `--json` لازمی طور پر `memory` یا `conversation` جیسی سب کمانڈ سے **پہلے** رکھا جائے۔
> * درست: `omi --json memory list`
> * غلط: `omi memory list --json`

---

## 5. ایگزٹ کوڈز (Exit Codes)

واضح ایگزٹ کوڈز اسکرپٹس اور CI میں خرابیوں کی ہینڈلنگ آسان بناتے ہیں۔

| ایگزٹ کوڈ | مطلب | تفصیل |
| :---: | :--- | :--- |
| `0` | کامیابی | کمانڈ بغیر کسی خرابی کے مکمل ہوئی |
| `1` | استعمال کی خرابی | غلط فلیگ، نامکمل آرگومنٹس، وغیرہ |
| `2` | تصدیقی خرابی | لاگ اِن نہیں، غلط API کی، یا ختم شدہ ٹوکن |
| `3` | سرور کی خرابی | 5xx جواب، کنکشن ٹائم آؤٹ، نیٹ ورک کی ناکامی |
| `4` | ریٹ کی حد | 429 Too Many Requests |
| `5` | ذریعہ نہیں ملا | 404 Not Found (دیا گیا ID موجود نہیں) |

---

## 6. شیل کے مطابق ماحول کے متغیر کی سیٹ اپ مثالیں

### Bash / Zsh (Linux / macOS)
```bash
# API کی سیٹ کریں
export OMI_API_KEY="omi_dev_your_real_key_here"

# فہرست حاصل کریں
omi --json memory list --limit 10
```

### PowerShell (Windows)
```powershell
# API کی سیٹ کریں
$env:OMI_API_KEY = "omi_dev_your_real_key_here"

# PowerShell میں JSON کی پارسنگ کی مثال
(omi --json memory list | ConvertFrom-Json) | Select-Object id, content
```

---

## 7. لوکل Desktop API کے ساتھ انٹیگریشن

اگر Omi ڈیسک ٹاپ ایپ چل رہی ہو، تو آپ کلاؤڈ API سے گزرے بغیر مقامی اسکرین ہسٹری اور SQL ڈیٹابیس سے براہ راست سوال کر سکتے ہیں۔

```bash
# مقامی API کا مقصد سیٹ کریں
omi local configure --url http://127.0.0.1:47778 --token YOUR_DESKTOP_TOKEN

# کنکشن کی حالت چیک کریں
omi --json local status

# اسکرین ہسٹری تلاش کریں
omi --json local search-screen "قیمت پلان" --days 7 --app Safari
```

---

## 8. پروفائل فیچر (Profiles)

کئی اکاؤنٹس یا ماحول (مثلاً پروڈکشن اور ٹیسٹنگ) استعمال کرنے کے لیے `--profile` آپشن استعمال کریں۔ سیٹنگز `~/.omi/config.toml` میں محفوظ ہوتی ہیں۔

```bash
# ذاتی پروفائل کے لیے لاگ اِن
omi --profile personal auth login

# کام/ڈیویلپمنٹ پروفائل کے لیے لاگ اِن
omi --profile work auth login

# مخصوص پروفائل کے ساتھ کمانڈ چلائیں
omi --profile work memory list
```
