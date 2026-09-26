# omi-cli للوكلاء البرمجيين (Agents)

> دليل عملي للأطر التي تقودها نماذج اللغة الكبيرة (Claude Code، Cursor، والبوتات الخاصة بك).

## لماذا تعد واجهة CLI مناسبة للوكلاء

* **عقد JSON ثابت ومستقر.** يُخرج الخيار `--json` وثيقة JSON صالحة إلى stdout و
  *فقط* وثيقة JSON — بدون رسائل تقدم أو مؤشرات تحميل متحركة. تذهب الأخطاء إلى
  stderr بتنسيق `{"error": "...", "detail": "..."}`.
* **رموز خروج ثابتة ومحددة.** `0` نجاح / `1` خطأ في الاستخدام / `2` فشل المصادقة / `3` خطأ في الخادم / `4` تجاوز
  حد المعدل (rate limited) / `5` غير موجود. يمكن للوكلاء التفرع بناءً على هذه الرموز دون الحاجة إلى معالجة أخطاء اللغة الطبيعية.
* **لا توجد مطالبات تفاعلية في بيئات العمل التلقائية (headless).** مرر `--yes` (أو `-y`)
  للأوامر التي تقوم بالحذف أو التعديل؛ مرر `--api-key` أو عيّن `OMI_API_KEY` لتخطي
  تسجيل الدخول التفاعلي.
* **سلوك إعادة محاولة مرن ومتسامح.** الأخطاء من النوع `429` و `5xx` تتم إعادة محاولتها تلقائيًا مع تأخير أسي
  قبل إظهار الخطأ.

## المصادقة (لمرة واحدة، بواسطة المستخدم)

يحصل المستخدم على مفتاح API للمطورين من تطبيق الويب Omi
(`https://app.omi.me` → Developer → API Keys) ويقوم بأحد الإجرائين:

```bash
omi auth login                          # لصق تفاعلي؛ لا يظهر المفتاح في سجل الطرفية
# أو
export OMI_API_KEY=omi_dev_...          # مؤقت ومناسب للحاويات (containers)
```

## أكثر خمسة أشياء ينفذها الوكلاء

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

## واجهة Desktop API المحلية

عندما يتيح تطبيق Omi Desktop واجهته البرمجية المحلية، يمكن للوكلاء الاستعلام عن سجل
الشاشة على الجهاز والملخصات واستعلامات SQL والمهام دون استهلاك واجهة السحابة للمطورين:

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

لا تقم بإكمال أو حذف المهام إلا عندما يطلب المستخدم ذلك بوضوح:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

الأمر `omi local screenshot SCREENSHOT_ID --output PATH` يكتب لقطة الشاشة إلى
القرص ويستمر في طباعة مخرجات JSON إلى stdout للسكربتات. عادة ما يأتي معرّف لقطة الشاشة
من `local search-screen` أو استعلام SQL على جدول `screenshots`. إذا أرجع Desktop
فشلاً مهيكلاً مثل `screenshot_pending` أو `screenshot_file_missing` أو
`screenshot_chunk_corrupted`، يحتفظ وضع JSON بحقول `reason` و `hint` و
`screenshot_id` على stderr حتى يتمكن الوكلاء من إعادة المحاولة بمعرّف أقدم أو الإبلاغ عن
العائق الدقيق. تحقق من نجاح الملفات باستخدام `file PATH` قبل تمريرها إلى أدوات الرؤية.

## مثال تطبيقي: حلقة وكيل بايثون (Python agent loop)

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """استدعاء CLI الخاص بـ omi في وضع JSON، وإطلاق استثناء في حال الرموز غير الصفرية."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # يطبع CLI أخطاء منظمة في stderr في وضع JSON:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"انتهى omi بالرمز {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# قراءة جميع المهام المفتوحة وتحديد أي مهمة أقدم من 30 يومًا كمكتملة.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## التعامل مع حدود المعدل (Rate Limits)

الذكريات: 120/ساعة. المحادثات: 25/ساعة. الإنشاءات الجماعية: 15/ساعة.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # تم الوصول إلى حد المعدل
    err = json.loads(result.stderr)
    # حقل err["detail"] يبدو كالتالي: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## نصائح وإرشادات

* استخدم `--profile <name>` إذا كان وكيلك يدير حسابات متعددة في Omi. كل
  ملف شخصي لديه بيانات اعتماده ومسار API الخاص به.
* استخدم `--api-base http://localhost:8080` لاختبار الواجهة الخلفية المحلية.
* استخدم `OMI_LOCAL_API_URL` و `OMI_LOCAL_TOKEN` لتجاوز إعدادات Desktop API
  المحلية للملف الشخصي لتشغيل لمرة واحدة.
* استخدم `--verbose` لتصحيح الأخطاء — يسجل `METHOD path → status (Ns)` على stderr
  دون التأثير على stdout، وبالتالي يظل وضع JSON صالحًا.
* لتمرير المحتوى عبر الأنابيب (pipes) إلى محادثة، استخدم `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
