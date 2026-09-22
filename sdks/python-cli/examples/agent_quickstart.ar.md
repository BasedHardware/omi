# omi-cli لعملاء الذكاء الاصطناعي (AI Agents)

> دليل عملي للبيئات التي تقودها نماذج اللغة الكبيرة (Claude Code، Cursor، والبوتات المخصصة).

## لماذا يُعد الـ CLI صديقاً لعملاء الذكاء الاصطناعي

* **عقد JSON ثابت:** يُخرج علم `--json` مستندات JSON صالحة إلى stdout و*فقط* JSON — دون أي رسائل حالة أو دوائر تحميل. يتم إرسال الأخطاء إلى stderr بصيغة `{"error": "...", "detail": "..."}`.
* **رموز خروج ثابتة ومستقرة:** `0` نجاح / `1` خطأ في الاستخدام / `2` فشل المصادقة / `3` خطأ في الخادم / `4` تجاوز حد الطلبات / `5` غير موجود. يمكن للوكيل التفرع البرمجي مباشرة بناءً على رمز الخروج دون الحاجة لتحليل نصوص لغوية.
* **بدون مطالبات تفاعلية في وضع التشغيل الآلي (Headless):** مرر `--yes` (أو `-y`) للأوامر الحساسة؛ مرر `--api-key` أو عيّن المتغير `OMI_API_KEY` لتخطي تسجيل الدخول عبر المتصفح.
* **إعادة المحاولة التلقائية:** يتم التعامل مع ردود `429` و `5xx` بإعادة المحاولة تلقائياً مع تراجع أسي قبل الإخفاق.

## المصادقة (لمرة واحدة من قبل المستخدم)

يحصل المستخدم على مفتاح API للمطورين من تطبيق الويب Omi
(`https://app.omi.me` → Developer → API Keys)، ثم يقوم بتشغيل:

```bash
omi auth login                          # لصق تفاعلي؛ لا يُحفظ المفتاح في سجل الأوامر
# أو
export OMI_API_KEY=omi_dev_...          # مؤقت، مثالي للحاويات و CI/CD
```

## العمليات الخمس الأكثر شيوعاً للوكلاء

### 1. قراءة الذكريات (Memories)

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. إنشاء ذكرى جديدة

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. قراءة المحادثات

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. قراءة المهام المطلوبة (Action Items)

```bash
omi action-item list --json --open
```

### 5. إتمام مهمة

```bash
omi action-item complete --json a1b2c3d4
```

## واجهة برمجة تطبيقات سطح المكتب المحلية (Local Desktop API)

عندما يفعّل تطبيق Omi Desktop الواجهة المحلية، يمكن للوكيل الاستعلام عن سجل الشاشة، الملخصات، ومهام SQL محلياً دون الحاجة للاتصال بالسحابة:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# أو للجلسات المؤقتة:
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

أكمل أو احذف المهام فقط عندما يطلب المستخدم ذلك صراحة:

```bash
omi --json local task complete task_1
```
