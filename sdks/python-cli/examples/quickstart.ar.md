# omi-cli — دليل البدء السريع بالعربية

> دليل عملي للعمل مع Omi من الطرفية. مناسب للإنسان ولوكيل الذكاء الاصطناعي على حد سواء.

`omi-cli` هو واجهة سطر الأوامر الرسمية لواجهة برمجة التطبيقات الخاصة بالمطوّرين في [Omi](https://omi.me).
يوفّر وصولاً سريعاً وقابلاً للبرمجة بالسكربتات إلى الكيانات الأربعة الرئيسية في Omi:
الذكريات (memories)، والمحادثات (conversations)، وعناصر العمل (action items)، والأهداف (goals).

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **التوثيق:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **الشيفرة المصدرية:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. التثبيت

الطريقة الموصى بها هي `pipx`: إذ تُثبّت الأداة في بيئة معزولة،
فلا تتعارض اعتمادياتها مع مشاريعك.

```bash
# موصى به: التثبيت عبر pipx
pipx install omi-cli

# أو عبر pip
pip install omi-cli
```

> **مهم: اسم الحزمة يختلف عن اسم الأمر.**
> * الحزمة التي تُثبَّت هي **`omi-cli`** (أما الحزمة المنفصلة `omi` فهي مشروع آخر لا علاقة له بهذا).
> * بعد التثبيت يُشغَّل الأمر **`omi`**.

تحقّق من نجاح التثبيت:

```bash
omi --version
omi --help
```

---

## 2. تسجيل الدخول

يدعم `omi-cli` طريقتين لتسجيل الدخول.

| الطريقة | متى تناسب | الأمر |
| :--- | :--- | :--- |
| **مفتاح المطوّر (`omi_dev_*`)** | CI/CD، السكربتات، وكلاء الذكاء الاصطناعي | `omi auth login --api-key ...` أو متغيّر بيئة |
| **تسجيل الدخول عبر المتصفح (Google/Apple)** | العمل على جهازك الشخصي | `omi auth login --browser` |

### تسجيل دخول تفاعلي

من دون أي رايات، يسألك الأمر بنفسه عن طريقة الدخول:

```bash
omi auth login
# 1) Browser — دخول عبر Google أو Apple (مريح للإنسان)
# 2) API key — لصق مفتاح المطوّر من app.omi.me (مريح للوكلاء وCI)
```

عند اختيار المفتاح يُخفى الإدخال، فلا يبقى المفتاح في سجل الطرفية.

### مباشرة عبر المتصفح

```bash
omi auth login --browser
```

### عبر مفتاح المطوّر

تحصل على المفتاح من [app.omi.me](https://app.omi.me) في قسم **Developer → API Keys**.

```bash
# حفظ المفتاح في الإعدادات
omi auth login --api-key omi_dev_...

# أو تمريره عبر البيئة — وهو الخيار الأفضل لـ CI/CD والحاويات
export OMI_API_KEY=omi_dev_...
```

يُستعمل متغيّر `OMI_API_KEY` عندما لا يحتوي الملف الشخصي النشط على مفتاح محفوظ،
لذا في الحاوية لا حاجة لكتابة أي شيء على القرص. وإذا كان المفتاح محفوظاً
في الملف الشخصي، فله الأولوية على متغيّر البيئة.

### التحقق من تسجيل الدخول

أمران يجيبان عن سؤالين مختلفين، ولا ينبغي الخلط بينهما:

* `omi auth status` — ما هو مخزَّن **محلياً**: الملف الشخصي، المفتاح المُخفى، الصلاحية.
  يعمل من دون شبكة.
* `omi auth whoami` — اتصال **بخادم Omi**: يتحقق من أن الخادم يقبل
  المفتاح فعلاً. يتطلب شبكة.

```bash
omi auth status    # فحص محلي، دون اتصال
omi auth whoami    # فحص على الخادم
```

تحديث مفتاح قاربت صلاحيته على الانتهاء دون إعادة تسجيل الدخول:

```bash
omi auth refresh
```

تسجيل الخروج:

```bash
omi auth logout
```

---

## 3. الأوامر الأساسية

### الذكريات (memories)

حقائق ومعارف حفظها النظام عنك.

```bash
# قائمة الذكريات
omi memory list

# إنشاء ذكرى جديدة
omi memory create "المستخدم يفضّل السمة الداكنة" --category lifestyle

# عرض ذكرى محددة
omi memory get <MEMORY_ID>
```

### المحادثات (conversations)

سجل الكلام والنص من الجهاز أو من التطبيق.

```bash
# آخر 5 محادثات
omi conversation list --limit 5

# محادثة كاملة مع التفريغ النصي
omi conversation get <CONVERSATION_ID> --include-transcript
```

### عناصر العمل (action items)

مهام استخلصها Omi من المحادثات.

```bash
# غير المنجزة فقط
omi action-item list --open

# تعليم عنصر كمنجَز
omi action-item complete <ACTION_ITEM_ID>
```

### الأهداف (goals)

```bash
# قائمة الأهداف
omi goal list

# تسجيل قيمة تقدّم جديدة (يلزم كلا الوسيطين: الهدف والقيمة)
omi goal progress <GOAL_ID> 25

# سجل التغييرات
omi goal history <GOAL_ID>
```

---

## سؤال بلغة طبيعية (`ask`)

أمر مستقل في المستوى الأعلى: يطرح سؤالاً بلغة طبيعية،
وتُبنى الإجابة من محادثاتك أنت.

```bash
omi ask "ما الذي قررته بشأن الانتقال"
omi --json ask "ما المهام التي وعدت بإنجازها هذا الأسبوع"
```

---

## 4. JSON والسكربتات (`--json`)

يستطيع `omi-cli` إخراج JSON قابل للقراءة آلياً. الراية `--json` **عامة**،
لذا توضع **قبل** الأمر الفرعي.

```bash
# الذكريات: استخراج id والنص والفئة
omi --json memory list | jq '.[] | {id, content, category}'

# عناوين أحدث المحادثات
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# عناصر العمل غير المنجزة
omi --json action-item list --open | jq '.'
```

> **خطأ شائع.** تأتي `--json` قبل الأمر الفرعي وليس بعده.
> * الصحيح: `omi --json memory list`
> * الخاطئ: `omi memory list --json`

في وضع `--json` لا يصل إلى المخرجات القياسية شيء سوى JSON نفسه —
ويمكن الاعتماد على ذلك في السكربتات.

---

## 5. رموز الخروج

الرموز ثابتة، لذا يمكن التفريع عليها في السكربتات وCI.

| الرمز | المعنى | متى يحدث |
| :---: | :--- | :--- |
| `0` | نجاح | اكتمل الأمر |
| `1` | خطأ في الاستدعاء | راية غير صحيحة، وسيط ناقص |
| `2` | خطأ في الوصول | لم يتم تسجيل الدخول، المفتاح غير صحيح أو منتهي |
| `3` | خطأ في الخادم | استجابة 5xx، انتهاء مهلة، انقطاع الاتصال |
| `4` | طلبات كثيرة جداً | 429 Too Many Requests |
| `5` | غير موجود | 404، المعرّف المحدد غير موجود |

مثال على الفحص في Bash:

```bash
if omi --json auth whoami > /dev/null 2>&1; then
  echo "المفتاح يعمل"
else
  code=$?
  [ "$code" -eq 2 ] && echo "يلزم تسجيل الدخول مجدداً"
  [ "$code" -eq 3 ] && echo "الخادم غير متاح، أعد المحاولة لاحقاً"
fi
```

---

## 6. متغيّرات البيئة

### Bash / Zsh (Linux, macOS)

```bash
export OMI_API_KEY="omi_dev_مفتاحك"

omi --json memory list --limit 10
```

لكي يُحمَّل المفتاح في الجلسات الجديدة، أضف السطر إلى `~/.bashrc` أو `~/.zshrc`.

### PowerShell (Windows)

```powershell
$env:OMI_API_KEY = "omi_dev_مفتاحك"

# تحليل JSON بواسطة PowerShell
(omi --json memory list | ConvertFrom-Json) | Select-Object id, content
```

للإعداد الدائم:

```powershell
[Environment]::SetEnvironmentVariable("OMI_API_KEY", "omi_dev_مفتاحك", "User")
```

---

## 7. تطبيق Omi Desktop المحلي

إذا كان تطبيق Omi المكتبي يعمل، فيمكن الوصول إلى جزء من البيانات مباشرةً
من دون المرور بالسحابة.

```bash
# تحديد عنوان الـ API المحلي
omi local configure --url http://127.0.0.1:47778 --token الرمز_الخاص_بك

# التحقق من أنه يستجيب
omi --json local status

# البحث في سجل الشاشة
omi --json local search-screen "التعرفة" --days 7 --app Safari

# لقطة شاشة حسب المعرّف
omi --json local screenshot 123 --output /tmp/omi-shot.jpg

# استعلام SQL حر على قاعدة البيانات المحلية
omi --json local sql "SELECT appName, COUNT(*) FROM screenshots GROUP BY appName"
```

ترتيب العمل: أولاً `local status`، ثم `local tools` — لمعرفة الأدوات
المتاحة ومعاملاتها — وبعدها فقط الاستدعاءات.

---

## 8. الملفات الشخصية

إذا كان لديك أكثر من حساب أو بيئة، افصل بينها بالملفات الشخصية.
تُحفظ الإعدادات في `~/.omi/config.toml`.

```bash
# تسجيل الدخول إلى الملف الشخصي
omi --profile personal auth login

# تسجيل الدخول إلى ملف العمل
omi --profile work auth login

# تنفيذ أمر في ملف شخصي محدد
omi --profile work memory list
```

عرض الإعدادات نفسها وتعديلها:

```bash
# ما هو مُعدّ حالياً
omi config show

# أين يقع ملف الإعدادات
omi config path

# تغيير قيمة
omi config set api_base https://api.omi.me
```

---

## 9. الخطوة التالية

* [`agent_quickstart.md`](./agent_quickstart.md) — كيفية ربط `omi-cli` بوكيل ذكاء اصطناعي.
* [`shell_examples.sh`](./shell_examples.sh) — أمثلة shell جاهزة.
* [توثيق Omi](https://docs.omi.me/doc/developer/cli/introduction) — المرجع الكامل للأوامر.
