# omi-cli — اردو فوری آغاز گائیڈ

> ٹرمینل سے Omi کے ساتھ کام کرنے کے لیے ایک عملی گائیڈ۔ انسانوں اور AI ایجنٹوں دونوں کے لیے۔

`omi-cli`، [Omi](https://omi.me) ڈیولپر API کا سرکاری کمانڈ لائن کلائنٹ ہے۔
یہ Omi کے چار بنیادی وسائل — یادداشتیں، گفتگو، عمل کی اشیاء، اور اہداف — تک تیز اور اسکرپٹ کے قابل رسائی دیتا ہے۔

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **دستاویزات:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **سورس کوڈ:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. تنصیب

تجویز کردہ طریقہ `pipx` ہے: یہ ٹول کو الگ تھلگ ماحول میں انسٹال کرتا ہے،
تاکہ اس کی انحصاریاں آپ کے منصوبوں سے متصادم نہ ہوں۔

```bash
# تجویز کردہ: pipx کے ذریعے انسٹال کریں
pipx install omi-cli

# یا pip کے ذریعے
pip install omi-cli
```

> **اہم: پیکج کا نام اور کمانڈ کا نام مختلف ہیں۔**
> * انسٹال ہونے والا پیکج **`omi-cli`** ہے (الگ پیکج `omi` ایک غیر متعلقہ دوسرا منصوبہ ہے)۔
> * انسٹالیشن کے بعد چلائی جانے والی کمانڈ **`omi`** ہے۔

یہ یقینی بنائیں کہ سب کچھ کام کر رہا ہے:

```bash
omi --version
omi --help
```

---

## 2. تصدیق

`omi-cli` لاگ ان کے دو طریقے سپورٹ کرتا ہے۔

| طریقہ | کس کے لیے موزوں | کمانڈ |
| :--- | :--- | :--- |
| **ڈیولپر کلید (`omi_dev_*`)** | CI/CD، اسکرپٹس، AI ایجنٹس | `omi auth login --api-key ...` یا ماحول متغیر |
| **براؤزر لاگ ان (Google/Apple)** | اپنے کمپیوٹر پر کام | `omi auth login --browser` |

### انٹرایکٹو لاگ ان

بغیر کسی آپشن کے چلائیں تو یہ پوچھے گا کہ کون سا طریقہ استعمال کرنا ہے۔

```bash
omi auth login
# 1) Browser — Google یا Apple سے لاگ ان (انسانوں کے لیے)
# 2) API key — app.omi.me سے ڈیولپر کلید چسپاں کریں (ایجنٹ/CI کے لیے)
```

کلید منتخب کرنے پر ان پٹ چھپا دیا جاتا ہے تاکہ کلید ٹرمینل کی ہسٹری میں محفوظ نہ ہو۔

### براؤزر سے براہ راست لاگ ان

```bash
omi auth login --browser
```

### ڈیولپر کلید سے لاگ ان

کلید [app.omi.me](https://app.omi.me) پر **Developer → API Keys** سے حاصل کریں۔

```bash
# کلید کو کنفیگریشن میں محفوظ کریں
omi auth login --api-key omi_dev_...

# یا ماحول کے ذریعے دیں — CI/CD اور کنٹینرز کے لیے بہتر
export OMI_API_KEY=omi_dev_...
```

`OMI_API_KEY` ماحول متغیر اس وقت استعمال ہوتا ہے جب فعال پروفائل میں کوئی کلید
محفوظ نہ ہو؛ اس لیے کنٹینر میں ڈسک پر کچھ لکھنے کی ضرورت نہیں۔ اگر پروفائل میں
پہلے سے کلید ہے تو وہ ماحول متغیر پر فوقیت رکھتی ہے۔

### رسائی کی تصدیق کریں

دو کمانڈ مختلف سوالوں کے جواب دیتی ہیں، انہیں الجھائیے نہ:

* `omi auth status` — **مقامی طور پر** کیا محفوظ ہے: پروفائل، چھپی کلید، میعاد ختم ہونے کی تاریخ۔
  نیٹ ورک کی ضرورت نہیں۔
* `omi auth whoami` — **Omi سرور** پر درخواست: تصدیق کرتا ہے کہ کلید واقعی قبول ہوتی ہے۔
  نیٹ ورک درکار ہے۔

```bash
omi auth status    # مقامی جانچ، آف لائن
omi auth whoami    # سرور جانچ
```

ختم ہونے والے ٹوکن کو دوبارہ لاگ ان کیے بغیر تازہ کریں — یہ کمانڈ صرف
**براؤزر/OAuth سیشنز** کے لیے ہے۔ API کلید (`omi_dev_*`) سے تصدیق شدہ پروفائل کے لیے
`omi auth refresh` استعمال کی خامی (کوڈ 1) کے ساتھ ناکام ہوتا ہے: تازہ کرنے کے لیے
کوئی ٹوکن نہیں — ضرورت ہو تو Omi ویب ایپ میں کلید بدلیں:

```bash
omi auth refresh
```

لاگ آؤٹ:

```bash
omi auth logout
```

---

## 3. بنیادی کمانڈز

### یادداشتیں (memories)

وہ حقائق اور علم جو سسٹم نے آپ کے بارے میں یاد رکھے ہیں۔

```bash
# یادداشتوں کی فہرست
omi memory list

# نئی بنائیں
omi memory create "صارف ڈارک موڈ کو ترجیح دیتا ہے" --category lifestyle

# ایک مخصوص دیکھیں
omi memory get <MEMORY_ID>
```

### گفتگو (conversations)

ڈیوائس یا ایپ سے آواز اور متن کی ہسٹری۔

```bash
# حالیہ 5 گفتگوئیں
omi conversation list --limit 5

# ٹرانسکرپٹ سمیت مکمل گفتگو
omi conversation get <CONVERSATION_ID> --include-transcript
```

### عمل کی اشیاء (action items)

وہ کام جو Omi نے گفتگو سے اخذ کیے ہیں۔

```bash
# صرف کھلی ہوئیں
omi action-item list --open

# مکمل کے طور پر نشان لگائیں
omi action-item complete <ACTION_ITEM_ID>
```

### اہداف (goals)

```bash
# اہداف کی فہرست
omi goal list

# نئی پیش رفت کی قیمت درج کریں (دونوں آرگیومینٹس درکار ہیں: ہدف اور قیمت)
omi goal progress <GOAL_ID> 25

# تبدیلیوں کی ہسٹری
omi goal history <GOAL_ID>
```

---

## قدرتی زبان میں پوچھیں (`ask`)

ایک الگ ٹاپ لیول کمانڈ: یہ قدرتی زبان میں سوال لیتی ہے،
اور جواب آپ کی گفتگو سے بناتی ہے۔

```bash
omi ask "میں نے منتقلی کے بارے میں کیا فیصلہ کیا؟"
omi --json ask "اس ہفتے کون سی عمل کی اشیاء مکمل کرنے کا وعدہ کیا؟"
```

---

## 4. JSON اور اسکرپٹ (`--json`)

`omi-cli` مشین پڑھنے کے قابل JSON نکال سکتی ہے۔ `--json` آپشن **گلوبل** ہے
لہٰذا یہ سب کمانڈ سے **پہلے** رکھا جانا چاہیے۔

```bash
# یادداشتیں: id، متن اور زمرہ نکالیں
omi --json memory list | jq '.[] | {id, content, category}'

# حالیہ گفتگو کے عنوانات
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# کھلی عمل کی اشیاء
omi --json action-item list --open | jq '.'
```

> **عام غلطی.** `--json` سب کمانڈ سے پہلے آتا ہے، بعد میں نہیں۔
> * درست: `omi --json memory list`
> * غلط: `omi memory list --json`

`--json` موڈ میں انسان کے لیے پیش رفت کے پیغامات اور اسپنر ختم ہو جاتے ہیں —
stdout پر صرف ایک درست JSON دستاویز ہوتی ہے۔ خرابیاں
`{"error": "...", "detail": "..."}` کی صورت میں stderr پر جاتی ہیں۔

---

## 5. خروجی کوڈز

اسکرپٹ میں فیصلہ کرنے کے لیے مستحکم خروجی کوڈز۔

| کوڈ | مطلب |
| :--- | :--- |
| `0` | کامیاب |
| `1` | استعمال کی خامی (غلط فلیگ، لازمی آرگیومینٹ غائب) |
| `2` | تصدیق ناکام — لاگ ان درکار |
| `3` | سرور/نیٹ ورک خامی |
| `4` | ریٹ لمیٹ — کچھ دیر بعد دوبارہ کوشش کریں |
| `5` | وسیلہ نہیں ملا |

```bash
if ! omi memory get "$MEMO_ID" --json > /tmp/m.json; then
  code=$?
  case $code in
    2) omi auth login --browser ;;
    5) echo "وہ یادداشت موجود نہیں" ;;
    *) echo "خرابی $code" ;;
  esac
fi
```

---

## 6. پروفائلز اور کنفیگریشن

اگر آپ کے پاس متعدد اکاؤنٹس یا ماحول ہیں تو انہیں پروفائلز سے الگ کریں۔
ترتیبات `~/.omi/config.toml` میں محفوظ ہوتی ہیں۔

```bash
# ذاتی پروفائل میں لاگ ان
omi --profile personal auth login

# کام کے پروفائل میں لاگ ان
omi --profile work auth login

# کسی مخصوص پروفائل میں کمانڈ چلائیں
omi --profile work memory list
```

استعمال ہونے والا پروفائل اس ترتیب سے طے ہوتا ہے: `--profile` آپشن (یا `-p`)
سب پر فوقیت رکھتا ہے؛ پھر `OMI_PROFILE` ماحول متغیر؛ پھر `~/.omi/config.toml`
میں فعال پروفائل؛ اور آخر میں `default` پروفائل بطور فالبیک۔

خود کنفیگریشن دیکھیں اور بدلیں:

```bash
# ابھی کیا سیٹ ہے
omi config show

# کنفیگریشن فائل کہاں ہے
omi config path

# قیمت بدلیں
omi config set api_base https://api.omi.me
```

---

## 7. اگلے اقدامات

* [`agent_quickstart.md`](./agent_quickstart.md) — `omi-cli` کو AI ایجنٹ سے جوڑنے کا طریقہ۔
* [`shell_examples.sh`](./shell_examples.sh) — تیار شیل مثالیں۔
* [Omi دستاویزات](https://docs.omi.me/doc/developer/cli/introduction) — مکمل کمانڈ حوالہ۔
