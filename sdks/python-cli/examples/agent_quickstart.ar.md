# omi-cli للوكلاء

> دليل عملي لمشغّلات مدعومة بنماذج اللغة الكبيرة (Claude Code، Cursor، روبوتاتك الخاصة).

## لماذا CLI ملائم للوكلاء

* **عقد JSON مستقر.** `--json` يكتب مستند JSON صالحًا إلى stdout و*فقط* JSON — لا رسائل تقدم ولا مؤشرات دوّارة. تُرسل الأخطاء إلى stderr كـ `{"error": "...", "detail": "..."}`.
* **رموز خروج مستقرة.** `0` نجاح / `1` استخدام / `2` مصادقة / `3` خادم / `4` rate limited / `5` غير موجود. يمكن للوكلاء التفريع عليها دون تحليل أخطاء باللغة الطبيعية.
* **لا مطالبات تفاعلية في السياقات بلا واجهة.** مرّر `--yes` (أو `-y`) للأوامر المدمّرة؛ مرّر `--api-key` أو عيّن `OMI_API_KEY` لتخطّي تسجيل الدخول التفاعلي.
* **سلوك إعادة محاولة متسامح.** `429` و`5xx` تُعاد محاولتها بتراجع قبل أن تظهر.

## المصادقة (مرة واحدة، بواسطة الإنسان)

يحصل المستخدم على مفتاح API للمطوّر من تطبيق Omi على الويب
(`https://app.omi.me` ← Developer ← API Keys) ثم:

```bash
omi auth login                          # لصق تفاعلي؛ المفتاح ليس في سجل الصدفة
# # أو
export OMI_API_KEY=omi_dev_...          # مؤقت، ملائم للحاويات
```

## الأشياء الخمسة التي يفعلها الوكلاء غالبًا

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

### 4. قراءة عناصر العمل المفتوحة

```bash
omi action-item list --json --open
```

### 5. وضع علامة منجز على عنصر عمل

```bash
omi action-item complete --json a1b2c3d4
```

## واجهة Desktop المحلية

عندما يعرض Omi Desktop واجهته البرمجية المحلية، يمكن للوكلاء الاستعلام عن
سجل الشاشة على الجهاز والملخصات وSQL والمهام دون استخدام واجهة السحابة للمطورين:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# # أو، للجلسات المؤقتة:
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

أكمل المهام أو احذفها فقط عندما يطلب المستخدم بوضوح:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` يكتب لقطة الشاشة إلى
القرص وما زال يطبع JSON إلى stdout للنصوص البرمجية. معرّف لقطة الشاشة يأتي عادةً
من `local search-screen` أو SQL على جدول `screenshots`. إذا أعاد Desktop فشلًا
منظمًا مثل `screenshot_pending` أو `screenshot_file_missing` أو
`screenshot_chunk_corrupted`، يحافظ وضع JSON على حقول `reason` و`hint` و
`screenshot_id` في stderr حتى يستطيع الوكيل إعادة محاولة معرّف أقدم أو الإبلاغ
عن المانع الدقيق. تحقق من المخرجات الناجحة بـ`file PATH` قبل تمريرها إلى أدوات الرؤية.

## مثال منفّذ: حلقة وكيل Python

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

# اقرأ كل عناصر العمل المفتوحة وأكمل ما هو أقدم من 30 يومًا.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## التعامل مع حدود المعدل

الذكريات: 120/ساعة. المحادثات: 25/ساعة. الإنشاءات المجمّعة: 15/ساعة.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] يبدو هكذا: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## نصائح

* استخدم `--profile <name>` إذا كان الوكيل يدير عدة حسابات Omi. لكل ملف
  شخصي بيانات اعتماد وقاعدة API خاصة به.
* استخدم `--api-base http://localhost:8080` لاختبار الواجهة الخلفية محليًا.
* استخدم `OMI_LOCAL_API_URL` و`OMI_LOCAL_TOKEN` لتجاوز إعدادات Desktop API
  الخاصة بالملف الشخصي لتشغيل واحد.
* استخدم `--verbose` للتصحيح — يسجّل `METHOD path → status (Ns)` إلى stderr
  دون التأثير على stdout، فيبقى وضع JSON صالحًا.
* لتمرير محتوى إلى محادثة، استخدم `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
