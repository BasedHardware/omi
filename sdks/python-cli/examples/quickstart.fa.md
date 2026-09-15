# راهنمای شروع سریع omi-cli (Persian Quickstart)

> راهنمای عملی برای کار با Omi مستقیماً از ترمینال — برای توسعه‌دهندگان و عامل‌های هوش مصنوعی خودکار.

`omi-cli` رابط خط فرمان رسمی برای API توسعه‌دهندگان [Omi](https://omi.me) است. با آن می‌توانید چهار بخش اصلی سیستم را به شکلی ساخت‌یافته و قابل خودکارسازی مدیریت کنید: حافظه‌ها (memories)، گفتگوها (conversations)، کارهای اقدامی (action items) و اهداف (goals).

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **مستندات رسمی:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **کد منبع:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

نام دستورها، گزینه‌ها و پیام‌های برنامه به انگلیسی باقی می‌مانند؛ فقط متن توضیحی این راهنما فارسی است. مرجع اصلی، README انگلیسی است.

---

## ۱. نصب

برای جلوگیری از تداخل وابستگی‌ها و اجرای ابزار در یک محیط جداگانه، استفاده از `pipx` توصیه می‌شود:

```bash
# توصیه‌شده: نصب ایزوله با pipx
pipx install omi-cli

# جایگزین: نصب با pip داخل یک محیط مجازی فعال
pip install omi-cli
```

> **توجه: نام بسته در برابر نام دستور**
> * نام بسته در PyPI **`omi-cli`** است (نام `omi` متعلق به یک بستهٔ نامرتبط است).
> * دستوری که در ترمینال اجرا می‌کنید فقط **`omi`** است.

بررسی کنید که نصب درست انجام شده است:

```bash
omi --version
omi --help
```

اگر ترمینال دستور `omi` را پیدا نکرد، مطمئن شوید محیط مجازی فعال است یا پوشه‌ای که `pipx` فایل‌های اجرایی را در آن می‌گذارد در `PATH` شما قرار دارد.

---

## ۲. احراز هویت (Authentication)

`omi-cli` از دو روش اصلی احراز هویت پشتیبانی می‌کند:

| روش | کاربرد | نمونه |
| :--- | :--- | :--- |
| **کلید API توسعه‌دهنده (`omi_dev_*`)** | اسکریپت‌ها، CI/CD، سرورهای بدون رابط گرافیکی، عامل‌های هوش مصنوعی | `omi auth login --api-key ...` یا `OMI_API_KEY` |
| **ورود با مرورگر (OAuth با Google/Apple)** | ایستگاه‌های کاری محلی و توسعه‌دهندگان | `omi auth login --browser` (Google) / `--provider apple` |

### ورود تعاملی
بدون هیچ گزینه‌ای اجرا کنید تا روش را به‌صورت تعاملی انتخاب کنید:

```bash
omi auth login
# 1) Browser — مرورگر را برای ورود با Google باز می‌کند (برای Apple از `--provider apple` استفاده کنید)
# 2) API key — کلید API را از app.omi.me وارد کنید (ورودی پنهان می‌شود)
```

### ورود مستقیم با مرورگر
```bash
# پیش‌فرض: ورود با Google
omi auth login --browser

# جایگزین: ورود با Apple
omi auth login --browser --provider apple
```

### استفاده از کلید API توسعه‌دهنده
کلید را در [app.omi.me](https://app.omi.me) از مسیر **Developer → API Keys** بسازید:

```bash
# ذخیرهٔ کلید در پروفایل محلی فعال
omi auth login --api-key omi_dev_توکن_واقعی_شما

# یا تعریف به‌صورت متغیر محیطی (مناسب کانتینرها و CI/CD)
export OMI_API_KEY="omi_dev_توکن_واقعی_شما"
```

> `OMI_API_KEY` فقط زمانی استفاده می‌شود که پروفایل فعال کلیدی ذخیره نکرده باشد. اگر قبلاً با `omi auth login` وارد شده‌اید و می‌خواهید متغیر محیطی اعمال شود، ابتدا `omi auth logout` را اجرا کنید.

### بررسی وضعیت احراز هویت
* `omi auth status`: پروفایل فعال و اعتبارنامهٔ پوشیده‌شده را نشان می‌دهد (به‌صورت محلی و بدون اتصال اجرا می‌شود؛ تاریخ انقضا فقط برای توکن‌های OAuth معنا دارد).
* `omi auth whoami`: درخواستی به سرور Omi می‌فرستد تا اعتبار را تأیید کند (به شبکه نیاز دارد).

```bash
omi auth status
omi auth whoami
```

تمدید توکن OAuth بدون ورود دوباره:

```bash
omi auth refresh
```

> `omi auth refresh` فقط برای پروفایل‌هایی که با مرورگر (OAuth) وارد شده‌اند کار می‌کند. برای پروفایل‌های مبتنی بر کلید API چیزی برای تمدید وجود ندارد و دستور با پیام «Nothing to refresh» و کد خروج `1` پایان می‌یابد.

خروج:
```bash
omi auth logout
# اگر OMI_API_KEY در محیط تعریف شده است، آن را هم حذف کنید (Bash/Zsh: `unset OMI_API_KEY`).
```

---

## ۳. دستورهای اصلی

### حافظه‌ها (Memories)
واقعیت‌های ساخت‌یافته و مشاهدات زمینه‌ای که Omi ذخیره کرده است:

```bash
# فهرست حافظه‌ها
omi memory list

# ساخت حافظهٔ جدید با دسته‌بندی
omi memory create "پاسخ‌های فنی کوتاه با مثال پایتون را ترجیح می‌دهم" --category work

# دریافت یک حافظهٔ مشخص با شناسه
omi memory get <MEMORY_ID>
```

### گفتگوها (Conversations)
ضبط‌های صوتی، رونوشت‌ها و مکالمه‌هایی که دستگاه‌های Omi ثبت کرده‌اند:

```bash
# فهرست ۵ گفتگوی اخیر
omi conversation list --limit 5

# جزئیات یک گفتگو همراه با رونوشت کامل
omi conversation get <CONVERSATION_ID> --include-transcript
```

### کارهای اقدامی (Action Items)
کارهایی که به‌صورت خودکار از گفتگوها استخراج شده‌اند:

```bash
# فهرست کارهای باز
omi action-item list --open

# علامت‌گذاری یک کار به‌عنوان انجام‌شده
omi action-item complete <ACTION_ITEM_ID>
```

### اهداف (Goals)
شاخص‌های پیشرفت و اهداف بلندمدت:

```bash
# فهرست اهداف فعال
omi goal list

# ساخت یک هدف عددی جدید
omi goal create "روزانه ۲ لیتر آب بنوش" --type numeric --target 2 --unit liters

# به‌روزرسانی مقدار فعلی یک هدف (شناسه و مقدار جدید)
omi goal progress <GOAL_ID> 1.5
```

---

## ۴. خودکارسازی ساخت‌یافته و خروجی JSON (`--json`)

`omi-cli` برای خودکارسازی در خط لوله‌ها و زنجیرهٔ ابزارها ساخته شده است. گزینهٔ سراسری `--json` خروجی JSON خالص و ماشین‌خوان برمی‌گرداند:

```bash
# فهرست حافظه‌ها به‌صورت JSON و فیلتر با jq
omi --json memory list | jq '.[] | {id, content, category}'

# عنوان گفتگوهای اخیر
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# همهٔ کارهای باز به‌صورت JSON خام
omi --json action-item list --open | jq '.'
```

> **قاعدهٔ مهم نحوی:**
> `--json` یک **گزینهٔ سراسری** است و باید **پیش از** زیردستور بیاید:
> * درست: `omi --json memory list`
> * نادرست: `omi memory list --json`

### صفحه‌بندی
دستورهای `list` از `--limit` و `--offset` پشتیبانی می‌کنند:

```bash
omi --json memory list --limit 50 --offset 50
```

### خروجی گرفتن در فایل
برای اینکه رنگ‌های ANSI یا نویسه‌های کنترلی وارد فایل نشوند، خروجی استاندارد را مستقیماً در پوسته هدایت کنید:

```bash
# خروجی حافظه‌ها در یک فایل JSON تمیز
omi --json memory list > memories.json
```

---

## ۵. کدهای خروج (Exit Codes Contract)

برای مدیریت قابل اعتماد خطا در CI/CD و اسکریپت‌ها، `omi-cli` قرارداد ثابتی از کدهای خروج دارد (ببینید `omi_cli/errors.py`):

| کد | نام | توضیح و نمونه |
| :---: | :--- | :--- |
| `0` | **موفقیت (`EXIT_OK`)** | عملیات بدون خطا انجام شد. |
| `1` | **خطای استفاده (`EXIT_USAGE`)** | خطاهای اعتبارسنجی خودِ omi-cli: گزینه‌های ناسازگار `--browser` و `--api-key`، انتخاب نامعتبر در ورود تعاملی، ورودی خالی از stdin، یا `omi auth refresh` روی پروفایل کلید API. |
| `2` | **خطای احراز هویت (`EXIT_AUTH`)** | اعتبارنامهٔ ناموجود یا نامعتبر، یا نشست منقضی‌شده. توجه: گزینهٔ ناشناخته یا آرگومان جاافتاده هم توسط خودِ Click رد می‌شود و با کد `2` پایان می‌یابد. |
| `3` | **خطای سرور (`EXIT_SERVER`)** | پاسخ HTTP 5xx از سرور Omi یا قطع ارتباط شبکه. |
| `4` | **محدودیت نرخ (`EXIT_RATE_LIMITED`)** | HTTP 429 — درخواست‌های بیش از حد در زمان کوتاه. |
| `5` | **یافت نشد (`EXIT_NOT_FOUND`)** | HTTP 404 — منبع درخواستی (حافظه، گفتگو، کار) وجود ندارد. |

---

## ۶. نمونه‌هایی برای پوسته‌های مختلف

### Bash / Zsh (Linux / macOS)
```bash
# تنظیم کلید API برای این نشست
export OMI_API_KEY="omi_dev_توکن_واقعی_شما"

# اجرای دستور و بررسی کد خروج
omi --json memory list --limit 10
if [ $? -ne 0 ]; then
    echo "خطا در دریافت حافظه‌ها از Omi." >&2
fi
```

### PowerShell (Windows)
```powershell
# تعریف متغیر محیطی در PowerShell
$env:OMI_API_KEY = "omi_dev_توکن_واقعی_شما"

# تبدیل خروجی JSON به شیء PowerShell
$memories = omi --json memory list | ConvertFrom-Json
$memories | Select-Object id, content, category

# بررسی خطا با $LASTEXITCODE
if ($LASTEXITCODE -ne 0) {
    Write-Error "دستور Omi با کد خروج $LASTEXITCODE شکست خورد."
}
```

---

## ۷. اتصال به API محلی دسکتاپ (Omi Desktop)

وقتی Omi Desktop روی دستگاه شما اجرا می‌شود (پورت پیش‌فرض 47778)، می‌توانید بدون عبور از ابر، مستقیماً با زمینهٔ محلی کار کنید:

```bash
# پیکربندی اتصال محلی (برای محافظت از توکن از متغیر محیطی استفاده کنید)
export OMI_LOCAL_API_URL="http://127.0.0.1:47778"
read -r -s -p "توکن Desktop را وارد کنید: " OMI_LOCAL_TOKEN; echo
export OMI_LOCAL_TOKEN

# بررسی وضعیت اتصال محلی
omi --json local status

# جستجو در تاریخچهٔ تصویری صفحه‌نمایش
omi --json local search-screen "گزارش فصلی" --days 7 --app Safari
```

به‌جای متغیرهای محیطی می‌توانید تنظیمات را روی پروفایل ذخیره کنید: `omi local configure --url http://127.0.0.1:47778 --token ...`.

---

## ۸. مدیریت چند پروفایل (Profiles)

با `--profile` به‌راحتی بین حساب شخصی، حساب کاری یا محیط آزمایشی جابه‌جا شوید. تنظیمات در `~/.omi/config.toml` ذخیره می‌شوند. ترتیب اولویت: گزینهٔ `--profile`، سپس متغیر محیطی `OMI_PROFILE`، و در نهایت پروفایل `default`.

```bash
# ساخت و ورود به پروفایل شخصی
omi --profile personal auth login

# ساخت و ورود به پروفایل کاری
omi --profile work auth login

# اجرای دستور با یک پروفایل مشخص
omi --profile work memory list

# انتخاب پروفایل از طریق متغیر محیطی
export OMI_PROFILE=work
omi memory list

# استفاده از یک نقطهٔ پایانی سفارشی برای آزمایش
omi --profile staging --api-base https://api.staging.omi.me memory list
```

---

## ۹. راهنمای امنیتی و بهترین شیوه‌ها

* **کلیدها را در کد ننویسید:** هرگز کلیدهای API (`omi_dev_*`) را در مخزن Git ثبت نکنید. از فایل‌های `.env` که در `.gitignore` هستند یا از ابزارهای مدیریت رمز استفاده کنید.
* **از تاریخچهٔ پوسته محافظت کنید:** روی سرورهای مشترک، کلیدها را به‌صورت آرگومان خط فرمان ندهید؛ از ورود تعاملی یا `OMI_API_KEY` استفاده کنید.
* **دسترسی پوشه را محدود کنید:** در Unix/macOS مطمئن شوید پوشهٔ پیکربندی دسترسی محدود دارد:
  ```bash
  chmod 700 ~/.omi
  chmod 600 ~/.omi/config.toml 2>/dev/null || true
  ```
* **پاک‌سازی نشست:** هنگام برچیدن محیط‌های موقت، متغیر محیطی را حذف کنید:
  ```bash
  unset OMI_API_KEY
  ```
