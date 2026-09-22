# omi-cli برای عامل‌های هوشمند (Agents)

> راهنمای کاربردی برای محیط‌های مبتنی بر مدل‌های زبانی بزرگ LLM (مانند Claude Code، Cursor و ربات‌های اختصاصی شما).

## چرا CLI برای عامل‌ها ایده‌آل است

* **قرارداد JSON پایدار.** گزینه `--json` یک سند JSON معتبر را به `stdout` ارسال می‌کند و *فقط* یک سند JSON — بدون پیام‌های پیشرفت یا نشانگرهای بارگذاری متحرک (spinners). خطاها به `stderr` به صورت `{"error": "...", "detail": "..."}` ارسال می‌شوند.
* **کدهای خروج (Exit Codes) مشخص و پایدار.**
  - `0`: موفقیت (ok)
  - `1`: خطای استفاده (usage)
  - `2`: عدم احراز هویت (auth)
  - `3`: خطای سرور (server)
  - `4`: محدودیت نرخ درخواست (rate limited)
  - `5`: یافت نشد (not found)
  عامل‌ها می‌توانند بدون نیاز به پردازش متون زبان طبیعی، بر اساس این کدها منطق خود را پیاده‌سازی کنند.
* **بدون درخواست تعاملی در محیط‌های Headless.** برای دستورات حذف یا تغییر داده از `--yes` (یا `-y`) استفاده کنید؛ برای رد کردن ورود تعاملی از `--api-key` استفاده کنید یا متغیر محیطی `OMI_API_KEY` را تنظیم نمایید.
* **رفتار تلاش مجدد منعطف.** خطاهای `429` و `5xx` قبل از نمایش عمومی، به طور خودکار با کاهش نرخ نمایی (backoff) مجدداً تلاش می‌شوند.

## احراز هویت (یک‌بار توسط کاربر)

کاربر کلید API توسعه‌دهنده را از وب‌اپلیکیشن Omi دریافت می‌کند:
(`https://app.omi.me` ← Developer ← API Keys) و یکی از دو روش زیر را انتخاب می‌کند:

```bash
omi auth login                          # جای‌گذاری تعاملی؛ کلید در تاریخچه شل ذخیره نمی‌شود
# یا
export OMI_API_KEY=omi_dev_...          # موقت و مناسب محیط‌های کانتینر/داکر
```

## پنج عملیات پرکاربرد عامل‌ها

### ۱. خواندن خاطرات (Memories)

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### ۲. ایجاد یک خاطره

```bash
omi memory create --json "کاربر حالت تاریک (dark mode) را ترجیح می‌دهد" --category lifestyle
```

### ۳. خواندن گفتگوها (Conversations)

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### ۴. خواندن موارد اقدام باز (Action Items)

```bash
omi action-item list --json --open
```

### ۵. علامت‌گذاری یک مورد اقدام به عنوان انجام‌شده

```bash
omi action-item complete --json a1b2c3d4
```

## رابط برنامه‌نویسی محلی دسکتاپ (Local Desktop API)

هنگامی که Omi Desktop رابط محلی خود را فعال می‌کند، عامل‌ها می‌توانند بدون استفاده از API ابری به سابقه صفحه روی دستگاه، خلاصه‌ها، استعلام‌های SQL و وظایف دسترسی داشته باشند:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# یا برای نشست‌های موقت:
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

تکمیل یا حذف وظایف را تنها در صورت درخواست صریح کاربر انجام دهید:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

دستور `omi local screenshot SCREENSHOT_ID --output PATH` اسکرین‌شات را روی دیسک ذخیره کرده و خروجی JSON را در `stdout` برای اسکریپت‌ها چاپ می‌کند. شناسه اسکرین‌شات معمولاً از `local search-screen` یا استعلام SQL روی جدول `screenshots` به دست می‌آید. در صورت بروز خطای ساختاریافته مانند `screenshot_pending`، `screenshot_file_missing` یا `screenshot_chunk_corrupted`، حالت JSON فیلدهای `reason`، `hint` و `screenshot_id` را در `stderr` نگه می‌دارد تا عامل بتواند با شناسه قدیمی‌تر تلاش مجدد کند یا علت دقیق مانع را گزارش دهد. پیش از ارسال خروجی‌ها به ابزارهای بینایی، صحت فایل را با `file PATH` بررسی کنید.

## نمونه عملی: حلقه عامل پایتون (Python Agent Loop)

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """اجرای omi CLI در حالت JSON، همراه با پرتاب استثنا در صورت خطای کد خروج."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # رابط خط فرمان خطاهای ساختاریافته را در حالت JSON به stderr می‌فرستد:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi با کد {result.returncode} خارج شد: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# خواندن تمام موارد اقدام باز و علامت‌گذاری موارد قدیمی‌تر از ۳۰ روز به عنوان انجام‌شده.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## مدیریت محدودیت نرخ درخواست (Rate Limits)

خاطرات: ۱۲۰ درخواست در ساعت. گفتگوها: ۲۵ درخواست در ساعت. ایجاد دسته‌ای: ۱۵ درخواست در ساعت.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # محدودیت نرخ درخواست فرا رسیده است
    err = json.loads(result.stderr)
    # err["detail"] شبیه این است: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## نکات مهم

* اگر عامل شما چندین حساب Omi را مدیریت می‌کند، از `--profile <name>` استفاده کنید. هر پروفایل اطلاعات ورود و آدرس API مستقل دارد.
* از `--api-base http://localhost:8080` برای آزمایش‌های محلی بک‌اند استفاده کنید.
* از `OMI_LOCAL_API_URL` و `OMI_LOCAL_TOKEN` برای بازنویسی تنظیمات Desktop API در یک اجرا استفاده کنید.
* از `--verbose` برای عیب‌یابی استفاده کنید — این گزینه `METHOD path status (Ns)` را بدون تأثیر بر `stdout` به `stderr` می‌فرستد تا خروجی JSON معتبر بماند.
* برای هدایت محتوا به یک گفتگو از طریق pipe، از `--text -` استفاده کنید:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
