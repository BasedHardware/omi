# omi-cli برای عامل‌ها

> راهنمای عملی برای harnessهای هدایت‌شده با LLM (Claude Code، Cursor، بات‌های خودتان).

## چرا CLI برای عامل‌ها مناسب است

* **قرارداد JSON پایدار.** `--json` یک سند JSON معتبر به stdout و *فقط* یک سند
  JSON صادر می‌کند — بدون پیام پیشرفت، بدون اسپینر. خطاها به stderr به شکل
  `{"error": "...", "detail": "..."}` می‌روند.
* **کدهای خروج پایدار.** `0` خوب / `1` استفاده / `2` auth / `3` سرور /
  `4` محدودیت نرخ / `5` یافت نشد. عامل‌ها می‌توانند بدون تجزیه خطاهای زبان
  طبیعی روی این‌ها انشعاب کنند.
* **بدون پرامپت تعاملی در زمینه‌های headless.** `--yes` (یا `-y`) را به دستورات
  مخرب بدهید؛ `--api-key` یا `OMI_API_KEY` را تنظیم کنید تا ورود تعاملی رد شود.
* **رفتار تلاش‌مجدد بخشنده.** `429` و `5xx` قبل از ظاهرشدن با backoff تکرار می‌شوند.

## Auth (یک بار، توسط انسان)

کاربر یک کلید dev API از اپلیکیشن وب Omi می‌گیرد
(`https://app.omi.me` → Developer → API Keys) و یا:

```bash
omi auth login                          # چسباندن تعاملی; کلید در تاریخچه shell نمی‌ماند
# یا
export OMI_API_KEY=omi_dev_...          # زودگذر، ایده‌آل برای کانتینرها
```

## پنج کاری که عامل‌ها بیشتر انجام می‌دهند

### 1. خواندن حافظه‌ها

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. ساخت یک حافظه

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. خواندن مکالمه‌ها

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. خواندن موارد عمل باز

```bash
omi action-item list --json --open
```

### 5. علامت‌گذاری یک مورد عمل به‌عنوان انجام‌شده

```bash
omi action-item complete --json a1b2c3d4
```

## API محلی Desktop

وقتی Omi Desktop API محلی خود را در معرض قرار می‌دهد، عامل‌ها می‌توانند تاریخچه
صفحه‌نمایش دستگاه، خلاصه‌ها، SQL و وظایف را بدون استفاده از API dev ابری پرس‌وجو کنند:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# یا، برای سشن‌های زودگذر:
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

فقط وقتی کاربر واضح می‌خواهد، وظایف را کامل یا حذف کنید:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` اسکرین‌شات را روی دیسک
می‌نویسد و همچنان JSON را برای اسکریپت‌ها به stdout چاپ می‌کند. شناسه اسکرین‌شات
معمولاً از `local search-screen` یا SQL روی جدول `screenshots` می‌آید. اگر Desktop
شکست ساختاریافته‌ای مانند `screenshot_pending`، `screenshot_file_missing` یا
`screenshot_chunk_corrupted` برگرداند، حالت JSON فیلدهای `reason`، `hint` و
`screenshot_id` را در stderr حفظ می‌کند تا عامل‌ها بتوانند شناسه قدیمی‌تری را
دوباره امتحان کنند یا انسداد دقیق را گزارش دهند. خروجی‌های موفق را با `file PATH`
قبل از انتقال به ابزارهای بینایی اعتبارسنجی کنید.

## مثال کاربردی: حلقه عامل در Python

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

## مدیریت محدودیت‌های نرخ

حافظه‌ها: 120/ساعت. مکالمه‌ها: 25/ساعت. ایجاد دسته‌ای: 15/ساعت.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## نکته‌ها

* از `--profile <name>` استفاده کنید اگر عامل شما چند حساب Omi را مدیریت می‌کند.
  هر پروفایل اعتبارنامه و base API خودش را دارد.
* از `--api-base http://localhost:8080` برای تست‌های backend محلی استفاده کنید.
* از `OMI_LOCAL_API_URL` و `OMI_LOCAL_TOKEN` برای لغو تنظیمات API محلی Desktop
  پروفایل برای یک اجرا استفاده کنید.
* از `--verbose` برای دیباگ استفاده کنید — `METHOD path → status (Ns)` را به
  stderr بدون تأثیر بر stdout ثبت می‌کند، پس حالت JSON معتبر می‌ماند.
* برای pipe کردن محتوا به یک مکالمه، از `--text -` استفاده کنید:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
