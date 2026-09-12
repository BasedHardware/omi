# omi-cli تیز آغاز گائیڈ (اردو)

> ٹرمینل سے Omi کے ساتھ تعامل کے لیے عملی گائیڈ۔ انسانوں اور AI ایجنٹوں دونوں کے لیے موزوں۔

`omi-cli` [Omi](https://omi.me) کے ڈویلپر APIs کے ساتھ تعامل کے لیے سرکاری کمانڈ لائن انٹرفیس ہے۔ یہ Omi کے چار بنیادی وسائل — **یادیں، گفتگو، ایکشن آئٹمز اور اہداف** — کو موثر اور اسکرپٹ ایبل طریقے سے سنبھالتا ہے۔

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **سرکاری دستاویزات:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **سورس کوڈ:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. انسٹالیشن

تجویز کردہ انسٹالیشن طریقہ انحصاریات کو الگ کرنے کے لیے `pipx` استعمال کرنا ہے۔

```bash
# تجویز کردہ: pipx کے ساتھ انسٹال کریں
pipx install omi-cli

# متبادل: pip استعمال کریں
pip install omi-cli
```

> **اہم: پیکج کے نام اور کمانڈ کے نام کے درمیان فرق**
> * انسٹال کردہ Python پیکج **`omi-cli`** نام سے ہے (اسٹینڈ ا لون `omi` پیکج ایک مختلف، غیر متعلقہ پیکج ہے)۔
> * انسٹالیشن کے بعد ٹرمینل میں قابل عمل کمانڈ کا نام **`omi`** ہے۔

انسٹالیشن کے بعد ورژن اور مدد کی جانچ کریں۔

```bash
omi --version
omi --help
```

---

## 2. تصدیق (Authentication)

`omi-cli` دو تصدیقی طریقے سپورٹ کرتا ہے۔

| طریقہ | تجویز کردہ استعمال | مثال کمانڈ |
| :--- | :--- | :--- |
| **ڈویلپر API کلید (`omi_dev_*`)** | CI/CD، خودکار اسکرپٹس، AI ایجنٹس | `omi auth login --api-key ...` یا ماحول متغیر |
| **براؤزر OAuth (Google/Apple)** | ڈویلپر PC / لیپ ٹاپ | `omi auth login --browser` |

### انٹرایکٹو لاگ ان
آپشنز کے بغیر، آپ سے براؤزر لاگ ان اور API کلید ان پٹ کے درمیان انتخاب کرنے کو کہا جائے گا۔

```bash
omi auth login
# 1) براؤزر — اپنے Google یا Apple اکاؤنٹ سے لاگ ان کریں (انسانوں کے لیے)
# 2) API کلید — app.omi.me سے ڈویلپر کلید پیسٹ کریں (ایجنٹس/CI کے لیے)
```

### براہ راست براؤزر کے ذریعے لاگ ان
```bash
omi auth login --browser
```

### API کلید کا استعمال
[app.omi.me](https://app.omi.me) پر **Developer → API Keys** سے ڈویلپر کلید حاصل کریں، پھر اسے سیٹ کریں۔

```bash
# کمانڈ کے ذریعے سیٹ کریں
omi auth login --api-key omi_dev_...

# یا ماحول متغیر کے ذریعے (CI/CD یا کنٹینرز کے لیے مثالی)
export OMI_API_KEY=omi_dev_...
```

### تصدیقی حیثیت کی جانچ
* `omi auth status`: مقامی پروفائل، ماسک شدہ ٹوکن اور ختم ہونے کی تاریخ دکھاتا ہے (آف لائن کام کرتا ہے)۔
* `omi auth whoami`: Omi سرور پر حقیقی تصدیقی درخواست بھیجتا ہے (نیٹ ورک کنکشن ضروری ہے)۔

```bash
omi auth status
omi auth whoami
```

لاگ آؤٹ کرنے کے لیے:
```bash
omi auth logout
```

---

## 3. بنیادی استعمال

آپ Omi کے چار بنیادی وسائل کی فہرست اور انتظام کر سکتے ہیں۔

### یادیں (Memories)
سسٹم نے جو حقائق اور علم سیکھا ہے اس کا انتظام کریں۔

```bash
# تمام یادوں کی فہرست
omi memory list

# نئی یاد بنائیں
omi memory create "صارف ڈارک موڈ کو ترجیح دیتا ہے" --category lifestyle

# کسی مخصوص یاد کی تفصیلات دکھائیں
omi memory get <MEMORY_ID>
```

### گفتگو (Conversations)
پہننے کے قابل آلہ یا ایپ کے ذریعے حاصل کردہ گفتگو کی آڈیو یا متنی تاریخ۔

```bash
# آخری 5 گفتگو حاصل کریں
omi conversation list --limit 5

# گفتگو کی تفصیلات اور ٹرانسکرپٹ دکھائیں
omi conversation get <CONVERSATION_ID> --include-transcript
```

### ایکشن آئٹمز (Action Items)
گفتگو سے خودکار طور پر نکالے گئے کام یا فالو اپ آئٹمز۔

```bash
# صرف کھلے ایکشن آئٹمز کی فہرست
omi action-item list --open

# ایکشن آئٹم کو مکمل کے طور پر نشان زد کریں
omi action-item complete <ACTION_ITEM_ID>
```

### اہداف (Goals)
ان اہداف کا انتظام کریں جن کی پیش رفت کو ٹریک کیا جاتا ہے۔

```bash
# تمام اہداف کی فہرست
omi goal list
```

---

## 4. اسکرپٹ پروسیسنگ اور JSON آؤٹ پٹ (`--json`)

`omi-cli` مقامی طور پر JSON آؤٹ پٹ کو سپورٹ کرتا ہے۔ `jq` یا Python اسکرپٹس کے ساتھ مل کر، **عالمی آپشن** `--json` کو ذیلی کمانڈ سے پہلے رکھا جانا چاہیے۔

```bash
# JSON میں یادوں کی فہرست حاصل کریں اور ID اور مواد نکالیں
omi --json memory list | jq '.[] | {id, content, category}'

# آخری 5 گفتگو کے عنوانات حاصل کریں
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# کھلے ایکشن آئٹمز کی فہرست
omi --json action-item list --open | jq '.[] | {id, title, due_at}'

# اہداف کی فہرست
omi --json goal list | jq '.[] | {id, title, progress: .progress_percent}'
```

---

## 5. سیشن کی تشخیص

فوری مسئلہ حل کرنے کے لیے ان دو کمانڈز کو جوڑوں میں استعمال کریں۔

```bash
# 1) پہلے مقامی ترتیب کی جانچ کریں
omi auth status

# 2) Omi سرور کے ساتھ تصدیق کریں
omi auth whoami

# 3) اگر ضروری ہو تو لاگ ان دوبارہ شروع کریں
omi auth login
```

---

## 6. بہترین طریقے

* **اسکرپٹس میں `--json` استعمال کریں:** آزاد متن کو پارس کرنے سے گریز کریں؛ ہمیشہ منظم JSON آؤٹ پٹ پر بھروسہ کریں۔
* **`pipx` کے ساتھ ماحول کو الگ کریں:** دوسرے Python پیکجوں کے ساتھ انحصاری تنازعات سے بچتا ہے۔
* **API کلید شیئر نہ کریں:** `omi_dev_*` کلیدیں مکمل اکاؤنٹ تک رسائی فراہم کرتی ہیں — انہیں سیکرٹ مینیجر یا ماحول متغیرات میں محفوظ کریں۔
* **مشترکہ آلات سے لاگ آؤٹ کریں:** مشترکہ مشینوں پر سیشن کے بعد `omi auth logout` استعمال کریں۔

---

## 7. مسئلہ حل

| علامت | ممکنہ وجہ | حل |
| :--- | :--- | :--- |
| `command not found: omi` | PATH میں pipx bin ڈائریکٹری نہیں ہے | `pipx ensurepath` چلائیں اور ٹرمینل دوبارہ شروع کریں |
| `401 Unauthorized` | API کلید غلط یا ختم ہو گئی | app.omi.me پر نئی کلید بنائیں اور اپ ڈیٹ کریں |
| `connection refused` | Omi سرور تک کوئی نیٹ ورک رسائی نہیں | انٹرنیٹ کنکشن اور پراکسی سیٹنگز کی جانچ کریں |
| کنفیگریشن فائلوں پر `permission denied` | کنفیگریشن ڈائریکٹری قابل تحریر نہیں ہے | `~/.config/omi` کی اجازتوں کی جانچ کریں |

---

## 8. فوری لنکس

* سورس ریپوزٹری: [github.com/BasedHardware/omi](https://github.com/BasedHardware/omi)
* مکمل دستاویزات: [docs.omi.me](https://docs.omi.me)
* مسائل اور معاونت: [github.com/BasedHardware/omi/issues](https://github.com/BasedHardware/omi/issues)
* Discord کمیونٹی: Omi ہوم پیج کے ذریعے دعوت نامہ دستیاب ہے