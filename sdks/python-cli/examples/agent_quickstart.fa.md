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

```bash
omi --json local task complete task_1
```
