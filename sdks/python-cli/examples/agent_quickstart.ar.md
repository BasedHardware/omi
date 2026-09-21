# omi-cli للوكلاء الذكيين (Agents)

> دليل عملي للبيئات المعتمدة على النماذج اللغوية الكبيرة LLM (مثل Claude Code، Cursor، والبوتات الخاصة بك).

## لماذا يُعد سطر الأوامر (CLI) ملائماً للوكلاء الذكيين

* **صيغة JSON ثابتة وموثوقة.** يُخرج الخيار `--json` مستند JSON صالحاً إلى `stdout` ومستند JSON **فقط** — دون رسائل تقدم أو مؤشرات تحميل متحركة (spinners). بينما تُرسل الأخطاء إلى `stderr` بالصيغة: `{"error": "...", "detail": "..."}`.
* **رموز خروج (Exit Codes) محددة وثابتة.** 
  - `0`: نجاح (ok)
  - `1`: خطأ في الاستخدام (usage)
  - `2`: فشل المصادقة (auth)
  - `3`: خطأ في الخادم (server)
  - `4`: تجاوز حد الطلبات (rate limited)
  - `5`: غير موجود (not found)
  تستطيع البرمجيات والوكلاء بناء تفرعات وشروط منطقية بناءً على هذه الرموز دون الحاجة لتحليل نصوص الأخطاء البشرية.
* **لا يطلب مدخلات تفاعلية في البيئات غير المرئية (Headless).** استخدم `--yes` (أو `-y`) للعمليات التي تحذف أو تعدل البيانات، واستخدم `--api-key` أو عيّن المتغير `OMI_API_KEY` لتخطي خطوة تسجيل الدخول التفاعلية.
* **إعادة محاولة مرنة وتلقائية.** الأخطاء من نوع `429` و `5xx` تتم إعادة محاولتها تلقائياً مع تراجع زمني (backoff) قبل إظهارها.

## المصادقة (تُجرى مرة واحدة بواسطة المستخدم)

يحصل المستخدم على مفتاح API للمطورين من تطبيق Omi على الويب:
(`https://app.omi.me` ← Developer ← API Keys) ثم يختار إحدى الطريقتين:

```bash
omi auth login                          # لصق تفاعلي؛ لا يظهر المفتاح في سجل سطر الأوامر (shell history)
# أو
export OMI_API_KEY=omi_dev_...          # مؤقت ومناسب لبيئات الحاويات (Containers/Docker)
```

## أكثر 5 مهام يقوم بها الوكلاء الذكيون

### 1. قراءة الذكريات (Memories)

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. إنشاء ذكرى جديدة

```bash
omi memory create --json "المستخدم يفضل الوضع الليلي (dark mode)" --category lifestyle
```

### 3. قراءة المحادثات (Conversations)

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. قراءة عناصر الإجراء المفتوحة (Action Items)

```bash
omi action-item list --json --open
```

### 5. تحديد عنصر إجراء كمكتمل

```bash
omi action-item complete --json a1b2c3d4
```

## واجهة برمجة التطبيقات المحلية لسطح المكتب (Local Desktop API)

عندما يُتيح تطبيق Omi Desktop واجهته المحلية، يمكن للوكلاء الاستعلام عن سجل الشاشة على الجهاز، والملخصات، واستعلامات SQL، والمهام دون استهلاك واجهة API السحابية:

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

لا تقم بإكمال أو حذف المهام إلا إذا طلب المستخدم ذلك صراحةً:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

الأمر `omi local screenshot SCREENSHOT_ID --output PATH` يحفظ لقطة الشاشة على القرص مع طباعة مخرجات JSON إلى `stdout` للسكربتات. عادةً ما يتم الحصول على معرف لقطة الشاشة (Screenshot ID) من `local search-screen` أو عبر استعلام SQL على جدول `screenshots`. في حال أرجع تطبيق Desktop خطأ هيكلياً مثل `screenshot_pending` أو `screenshot_file_missing` أو `screenshot_chunk_corrupted`، فإن وضع JSON يحافظ على حقول `reason` و `hint` و `screenshot_id` عبر `stderr` حتى يتمكن الوكيل من إعادة المحاولة بمعرف أقدم أو توضيح سبب المشكلة بدقة. تأكد دائماً من صحة الملف الناتج عبر `file PATH` قبل تمريره إلى نماذج الرؤية الحاسوبية (Vision Models).

## مثال عملي: حلقة تشغيل الوكيل بلغة بايثون (Python Agent Loop)

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """استدعاء omi CLI في وضع JSON، وإطلاق استثناء عند فشل رمز الخروج."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # يطبع سطر الأوامر الأخطاء الهيكلية إلى stderr في وضع JSON:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# قراءة جميع عناصر الإجراء المفتوحة ووضع علامة مكتمل على ما يزيد عمره عن 30 يوماً.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## التعامل مع حدود معدل الطلبات (Rate Limits)

- الذكريات (Memories): 120 طلب في الساعة.
- المحادثات (Conversations): 25 طلب في الساعة.
- الإنشاء الجماعي (Batch creates): 15 طلب في الساعة.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # تم بلوغ حد الطلبات (rate limited)
    err = json.loads(result.stderr)
    # err["detail"] يكون على شكل: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## نصائح هامة

* استخدم `--profile <name>` إذا كان وكيلك يدير عدة حسابات Omi. يمتلك كل ملف تعريف بيانات اعتماد ونقطة نهاية API خاصة به.
* استخدم `--api-base http://localhost:8080` لاختبارات الواجهة الخلفية المحلية.
* استخدم `OMI_LOCAL_API_URL` و `OMI_LOCAL_TOKEN` لتجاوز إعدادات Desktop API للملف الشخصي في جلسة تشغيل واحدة.
* استخدم `--verbose` للتصحيح والتشخيص - حيث يسجل `METHOD path status (Ns)` إلى `stderr` دون التأثير على `stdout`، ليبقى تدفق JSON سليماً.
* لتمرير محتوى إلى محادثة عبر الأنابيب (piping)، استخدم `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
