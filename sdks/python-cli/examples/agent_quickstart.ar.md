# omi-cli للوكلاء البرمجيين

> دليل عملي للبيئات الموجهة بنماذج اللغة الكبيرة (Claude Code، Cursor، وبرامج البوت المخصصة).

## لماذا تناسب واجهة سطر الأوامر (CLI) الوكلاء البرمجيين

* **عقد JSON مستقر.** يُخرج الخيار `--json` وثيقة JSON صالحة إلى stdout و*فقط* وثيقة JSON — لا رسائل تقدم ولا مؤشرات تحميل دوارة (spinners). الأخطاء تذهب إلى stderr بصيغة `{"error": "...", "detail": "..."}`.
* **رموز خروج مستقرة.** `0` نجاح / `1` خطأ في الاستخدام / `2` فشل المصادقة / `3` خطأ في الخادم / `4` تجاوز حد الطلبات (rate limited) / `5` غير موجود. يمكن للوكلاء التفريع بناءً على هذه الرموز دون الحاجة إلى معالجة رسائل الأخطاء باللغة الطبيعية.
* **لا توجد مطالبات تفاعلية في بيئات العمل غير المرئية (Headless).** مرّر `--yes` (أو `-y`) للأوامر التدميرية؛ مرّر `--api-key` أو اضبط متغير البيئة `OMI_API_KEY` لتخطي تسجيل الدخول التفاعلي.
* **سلوك إعادة محاولة مرن.** تتم إعادة محاولة الأخطاء `429` و `5xx` تلقائيًا مع تراجع أسي (exponential backoff) قبل رفع الخطأ.

## المصادقة (لمرة واحدة، بواسطة المستخدم)

يحصل المستخدم على مفتاح API للمطورين من تطبيق Omi على الويب (`https://app.omi.me` → Developer → API Keys) ويقوم بأحد الإجراءين:

```bash
omi auth login                          # لصق تفاعلي؛ لا يتم حفظ المفتاح في سجل الصدفة (shell)
# أو
export OMI_API_KEY=omi_dev_...          # مؤقت ومناسب للحاويات
```

## أكثر 5 عمليات يقوم بها الوكلاء البرمجيون

### 1. قراءة الذكريات

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. إنشاء ذكرى

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. قراءة المحادثات

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. قراءة عناصر الإجراءات المفتوحة

```bash
omi action-item list --json --open
```

### 5. تحديد عنصر إجراء كمكتمل

```bash
omi action-item complete --json a1b2c3d4
```

## واجهة برمجة تطبيقات سطح المكتب المحلية

عندما تتيح Omi Desktop واجهة برمجة التطبيقات المحلية، يمكن للوكلاء الاستعلام عن سجل الشاشة والملخصات وSQL والمهام على الجهاز دون استخدام واجهة برمجة التطبيقات السحابية:

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

لا تقم بإكمال أو حذف المهام إلا عندما يطلب المستخدم ذلك صراحةً:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

يقوم الأمر `omi local screenshot SCREENSHOT_ID --output PATH` بحفظ لقطة الشاشة على القرص مع الاستمرار في طباعة JSON إلى stdout للبرامج النصية. يتم الحصول على معرف لقطة الشاشة عادةً من `local search-screen` أو استعلام SQL في جدول `screenshots`. إذا أرجع تطبيق Desktop فشلاً مهيكلاً مثل `screenshot_pending` أو `screenshot_file_missing` أو `screenshot_chunk_corrupted`، فإن وضع JSON يحافظ على حقول `reason` و `hint` و `screenshot_id` في stderr حتى يتمكن الوكلاء من إعادة المحاولة بمعرف أقدم أو الإبلاغ عن العائق الدقيق. تحقق من المخرجات الناجحة باستخدام `file PATH` قبل تمريرها إلى أدوات الرؤية.

## مثال تطبيقي: حلقة وكيل بايثون

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """استدعاء omi CLI في وضع JSON، ورفع استثناء عند رموز الخروج غير الناجحة."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # يطبع CLI أخطاء منظمة إلى stderr في وضع JSON:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# قراءة كافة عناصر الإجراءات المفتوحة وتحديد ما يزيد عمره عن 30 يومًا كمكتمل.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## معالجة حدود الطلبات

الذكريات: 120/ساعة. المحادثات: 25/ساعة. الإنشاء المتعدد: 15/ساعة.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # تم الوصول إلى الحد المسموح للطلبات
    err = json.loads(result.stderr)
    # err["detail"] يبدو مثل: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## نصائح وإرشادات

* استخدم `--profile <name>` إذا كان وكيلك يدير حسابات Omi متعددة. يحتوي كل ملف تعريف على بيانات اعتماد خاصة ونقطة نهاية API منفصلة.
* استخدم `--api-base http://localhost:8080` لاختبار الواجهة الخلفية محليًا.
* استخدم `OMI_LOCAL_API_URL` و `OMI_LOCAL_TOKEN` لتجاوز إعدادات Desktop API المحلية لملف التعريف لتشغيل واحد.
* استخدم `--verbose` لتصحيح الأخطاء — يسجل `METHOD path → status (Ns)` في stderr دون التأثير على stdout، مما يحافظ على صحة وضع JSON.
* لتمرير المحتوى عبر الأنابيب إلى محادثة، استخدم `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
