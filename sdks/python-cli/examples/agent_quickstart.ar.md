# omi-cli للوكلاء البرمجيين (Agents)

> دليل عملي للأدوات المدارة بواسطة نماذج اللغة الكبيرة (Claude Code، Cursor، وبرمجيات البوت الخاصة بك).

## لماذا يعتبر CLI مناسباً للوكلاء البرمجيين

* **عقد JSON مستقر.** يُخرج الخيار `--json` مستند JSON صالحاً إلى stdout
  *فقط* — بدون رسائل تقدم أو مؤشرات تحميل. تخرج الأخطاء إلى
  stderr بتنسيق `{"error": "...", "detail": "..."}`.
* **رموز خروج مستقرة.** `0` نجاح / `1` خطأ في الاستخدام / `2` خطأ مصادقة / `3` خطأ في الخادم / `4` تجاوز معدل الطلبات / `5` غير موجود. يمكن للوكلاء التفرع بناءً على هذه الرموز دون الحاجة لتحليل نصوص اللغة الطبيعية.
* **لا توجد مطالبات تفاعلية في البيئات الآلية.** مرر `--yes` (أو `-y`) للأوامر
  ذات التأثير المباشر؛ مرر `--api-key` أو اضبط `OMI_API_KEY` لتجاوز تسجيل الدخول التفاعلي.
* **سلوك إعادة محاولة مرن.** تتم إعادة محاولة رموز الخطأ `429` و `5xx` تلقائياً مع فترة تراجع
  قبل إرجاع الخطأ.

## المصادقة (مرة واحدة، بواسطة الإنسان)

يحصل المستخدم على مفتاح API للمطورين من تطبيق ويب Omi
(`https://app.omi.me` → Developer → API Keys) ويختار أحد الأمرين:

```bash
omi auth login                          # لصق تفاعלי; لا يُحفظ المفتاح في سجل الأوامر
# أو
export OMI_API_KEY=omi_dev_...          # مؤقت، ملائم لبيئات الحاويات
```

## الأشياء الخمسة الأكثر استخداماً من قبل الوكلاء

### 1. قراءة الذكريات

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

### 4. قراءة المهام المفتوحة

```bash
omi action-item list --json --open
```

### 5. تحديد مهمة كمكتملة

```bash
omi action-item complete --json a1b2c3d4
```

## واجهة برمجة تطبيقات سطح المكتب المحلية (Desktop API)

عندما يوفر Omi Desktop واجهة برمجة التطبيقات المحلية، يمكن للوكلاء الاستعلام عن سجل الشاشة،
والملخصات، وSQL والمهام دون استخدام واجهة السحابة:

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

لا تقم بإنهاء المهام أو حذفها إلا عندما يطلب المستخدم ذلك صراحة:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

يكتب الأمر `omi local screenshot SCREENSHOT_ID --output PATH` لقطة الشاشة على
القرص ويستمر في إخراج JSON إلى stdout للنصوص البرمجية. يأتي معرّف لقطة الشاشة عادةً
من `local search-screen` أو استعلام SQL عبر جدول `screenshots`. إذا أرجع تطبيق Desktop
خطأ مهيكلاً مثل `screenshot_pending` أو `screenshot_file_missing`
أو `screenshot_chunk_corrupted`، يحتفظ وضع JSON بالحقول `reason` و `hint` و
`screenshot_id` في stderr ليتمكن الوكلاء من إعادة المحاولة بمعرّف أقدم أو الإبلاغ
عن العائق بدقة. تحقق من المخرجات الناجحة باستخدام `file PATH` قبل تمريرها لنماذج الرؤية.

## مثال عملي: حلقة عمل الوكيل بلغة Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """استدعاء omi CLI في وضع JSON مع رفع استثناء عند رموز الخطأ."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # يطبع CLI أخطاء مهيكلة إلى stderr في وضع JSON:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# قراءة جميع المهام المفتوحة وتحديد ما هو أقدم من 30 يوماً كمكتمل.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## التعامل مع قيود معدל الطلبات (rate limits)

الذكريات: 120/ساعة. المحادثات: 25/ساعة. الإنشاء المجمع: 15/ساعة.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # تم تجاوز الحد
    err = json.loads(result.stderr)
    # تظهر قيمة err["detail"] كالتالي: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## نصائح هامة

* استخدم `--profile <الاسم>` إذا كان وكيلك يدير حسابات Omi متعددة. يمتلك كل
  ملف شخصي بيانات اعتماده الخاصة وعنوان API الأساسي.
* استخدم `--api-base http://localhost:8080` لاختبار الواجهات الخلفية محلياً.
* استخدم `OMI_LOCAL_API_URL` و `OMI_LOCAL_TOKEN` لتجاوز إعدادات Desktop API المحلية
  لملف التعريف لتشغيل فردي.
* استخدم `--verbose` للتصحيح — يسجل `METHOD path → status (Ns)` في stderr
  دون التأثير على stdout، مما يحافظ على صحة وضع JSON.
* لتمرير محتوى إلى محادثة عبر الأنابيب (pipe)، استخدم `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
