# ابزار omi-cli برای عامل‌های هوش مصنوعی (AI Agents)

> راهنمای عملی برای محیط‌های مبتنی بر مدل‌های زبانی بزرگ (Claude Code، Cursor، و ربات‌های سفارشی).

## چرا CLI برای عامل‌ها بهینه‌سازی شده است

* **قرارداد پایدار JSON:** پرچم `--json` خروجی را به صورت اسناد معتبر JSON در stdout و *تنها* JSON چاپ می‌کند — بدون پیام وضعیت یا نماد بارگذاری. خطاها به صورت `{"error": "...", "detail": "..."}` به stderr ارسال می‌شوند.
* **کدهای خروج پایدار:** `0` موفقیت / `1` خطای استفاده / `2` خطای احراز هویت / `3` خطای سرور / `4` محدودیت درخواست / `5` یافت نشد. عامل می‌تواند بدون نیاز به تجزیه زبان طبیعی مستقیماً بر اساس کد خروج تصمیم‌گیری کند.
* **بدون درخواست تعاملی در حالت Headless:** برای دستورات برگشت‌ناپذیر از `--yes` (یا `-y`) استفاده کنید؛ برای رد کردن ورود مرورگر از `--api-key` یا متغیر `OMI_API_KEY` استفاده کنید.
* **تلاش مجدد خودکار:** پاسخ‌های `429` و `5xx` قبل از اعلام خطا، به طور خودکار با تأخیر تصاعدی مجدداً ارسال می‌شوند.

## احراز هویت (یک‌بار توسط کاربر)

کاربر کلید API توسعه‌دهنده را از برنامه تحت وب Omi دریافت می‌کند
(`https://app.omi.me` → Developer → API Keys)، سپس اجرا می‌کند:

```bash
omi auth login                          # جای‌گذاری تعاملی؛ در تاریخچه شل ذخیره نمی‌شود
# یا
export OMI_API_KEY=omi_dev_...          # موقت، مناسب برای کانتینرها و CI/CD
```

## پنج عملیات پرکاربرد عامل‌ها

### ۱. خواندن حافظه‌ها (Memories)

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### ۲. ایجاد حافظه جدید

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### ۳. خواندن گفتگوها

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### ۴. خواندن موارد اقدام (Action Items)

```bash
omi action-item list --json --open
```

### ۵. علامت‌گذاری اتمام کار

```bash
omi action-item complete --json a1b2c3d4
```

## رابط برنامه‌نویسی دسکتاپ محلی (Local Desktop API)

هنگامی که Omi Desktop رابط محلی را فعال می‌کند، عامل می‌تواند بدون تماس با ابر، تاریخچه صفحه، خلاصه‌ها و وظایف را جستجو کند:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# یا برای جلسات موقت:
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

فقط در صورتی که کاربر صریحاً درخواست کند، وظایف را تکمیل یا حذف کنید:

فقط در صورتی که کاربر صریحاً درخواست کند، وظایف را تکمیل یا حذف کنید:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

دستور `omi local screenshot SCREENSHOT_ID --output PATH` تصویر صفحه را بر روی دیسک ذخیره می‌کند و همچنان JSON را برای اسکریپت‌ها در stdout چاپ می‌کند. شناسه تصویر معمولاً از طریق `local search-screen` یا پرس‌وجوی SQL بر روی جدول `screenshots` به دست می‌آید. اگر نسخه دسکتاپ خطای ساختاریافته‌ای مانند `screenshot_pending`، `screenshot_file_missing` یا `screenshot_chunk_corrupted` بازگرداند، حالت JSON فیلدهای `reason`، `hint` و `screenshot_id` را در stderr حفظ می‌کند تا عامل‌ها بتوانند شناسه قدیمی‌تری را امتحان کنند یا مانع دقیق را گزارش دهند. پیش از ارسال تصویر به ابزارهای بینایی، خروجی موفق را با `file PATH` اعتبارسنجی کنید.

## مثال کاربردی: حلقه عامل پایتون (Python)

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

# Read all open action items and mark anything older than 30 days complete.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## مدیریت محدودیت نرخ درخواست (Handling rate limits)

حافظه‌ها: ۱۲۰ در ساعت. گفتگوها: ۲۵ در ساعت. ایجاد دسته‌ای: ۱۵ در ساعت.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## نکات کاربردی (Tips)

* اگر عامل شما چندین حساب Omi را مدیریت می‌کند، از `--profile <name>` استفاده کنید. هر نمایه دارای اعتبار و آدرس پایه API اختصاصی خود است.
* برای آزمایش با بک‌اند محلی از `--api-base http://localhost:8080` استفاده کنید.
* برای بازنویسی تنظیمات محلی Desktop API برای یک اجرای خاص، از `OMI_LOCAL_API_URL` و `OMI_LOCAL_TOKEN` استفاده کنید.
* برای خطایابی از پرچم `--verbose` استفاده کنید — این پرچم `METHOD path → status (Ns)` را بدون تأثیر بر stdout در stderr چاپ می‌کند تا فرمت JSON معتبر بماند.
* برای ارسال داده به مکالمه از طریق pipe، از `--text -` استفاده کنید:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
