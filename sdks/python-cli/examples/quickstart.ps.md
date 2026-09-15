# د omi-cli د چټک پیل لارښود (Pashto Quickstart)

> د ترمینل څخه مستقیم له Omi سره د کار کولو عملي لارښود — د پراختیا کوونکو او خپلواکو AI اجنټانو لپاره.

`omi-cli` د [Omi](https://omi.me) د پراختیا کوونکي API لپاره رسمي کمانډ-لاین انټرفیس دی. دا تاسو ته اجازه درکوي چې د سیسټم څلور اصلي برخې په منظم او اتومات کېدونکي ډول اداره کړئ: یادونه (memories)، خبرې اترې (conversations)، د عمل توکي (action items) او موخې (goals).

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **رسمي اسناد:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **سرچینه کوډ:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

د کمانډونو نومونه، اختیارونه او د پروګرام پیغامونه په انګلیسي پاتې کېږي؛ یوازې د دې لارښود توضیحي متن په پښتو دی. اصلي مرجع انګلیسي README دی.

---

## ۱. نصبول

د انحصار (dependency) له ټکرونو څخه د ژغورنې او د CLI په جلا چاپېریال کې د چلولو لپاره `pipx` وړاندیز کېږي:

```bash
# وړاندیز شوی: له pipx سره جلا نصب
pipx install omi-cli

# بدیل: د فعال Python مجازي چاپېریال دننه له pip سره
pip install omi-cli
```

> **یادونه: د بسته نوم په مقابل کې د کمانډ نوم**
> * په PyPI کې د بستې نوم **`omi-cli`** دی (`omi` نوم یوې غیر اړوندې بستې پورې اړه لري).
> * هغه کمانډ چې تاسو یې په ترمینل کې چلوئ یوازې **`omi`** دی.

تایید کړئ چې نصب کار کوي:

```bash
omi --version
omi --help
```

که ترمینل `omi` ونه موندي، ډاډ ترلاسه کړئ چې مجازي چاپېریال فعال دی یا هغه فولډر چې `pipx` په کې اجرا کېدونکي فایلونه ږدي ستاسو په `PATH` کې دی.

---

## ۲. هویت تصدیق (Authentication)

`omi-cli` د هویت تصدیق دوه اصلي طریقې ملاتړ کوي:

| طریقه | د کارونې ځای | بېلګه |
| :--- | :--- | :--- |
| **د پراختیا کوونکي API کیلي (`omi_dev_*`)** | سکریپټونه، CI/CD، بې‌سکرینه سرورونه، AI اجنټان | `omi auth login --api-key ...` یا `OMI_API_KEY` |
| **د براوزر OAuth (Google/Apple)** | ځایي کاري سټیشنونه او پراختیا کوونکي | `omi auth login --browser` (Google) / `--provider apple` |

### متقابل ننوتل
د طریقې د متقابل ټاکلو لپاره پرته له کوم فلاګ څخه یې وچلوئ:

```bash
omi auth login
# 1) Browser — د Google ننوتلو لپاره براوزر پرانیزي (د Apple لپاره `--provider apple` وکاروئ)
# 2) API key — له app.omi.me څخه API کیلي پیسټ کړئ (ننوتنه پټه ښودل کېږي)
```

### د براوزر له لارې مستقیم ننوتل
```bash
# تلواله: د Google ننوتل
omi auth login --browser

# بدیل: د Apple ننوتل
omi auth login --browser --provider apple
```

### د پراختیا کوونکي API کیلي کارول
په [app.omi.me](https://app.omi.me) کې د **Developer → API Keys** لاندې یوه کیلي جوړه کړئ:

```bash
# کیلي په فعال ځایي پروفایل کې خوندي کړئ
omi auth login --api-key omi_dev_ستاسو_اصلي_ټوکن

# یا یې د چاپېریال متغیر په توګه وټاکئ (د کانټینرونو او CI/CD لپاره غوره)
export OMI_API_KEY="omi_dev_ستاسو_اصلي_ټوکن"
```

> `OMI_API_KEY` یوازې هغه وخت کارول کېږي چې فعال پروفایل کومه خوندي شوې کیلي ونه لري. که تاسو مخکې له `omi auth login` سره ننوتلي یاست او غواړئ چې د چاپېریال متغیر اغېز وکړي، لومړی `omi auth logout` وچلوئ.

### د هویت تصدیق حالت کتل
* `omi auth status`: فعال پروفایل او پټ شوی اعتبارنامه ښیي (په ځایي/آفلاین ډول چلېږي؛ د پای نېټه یوازې د OAuth ټوکنونو لپاره ده).
* `omi auth whoami`: د اعتبار د تایید لپاره Omi سرور ته غوښتنه لېږي (شبکې ته اړتیا لري).

```bash
omi auth status
omi auth whoami
```

د OAuth ټوکن تازه کول پرته له بیا ننوتلو:

```bash
omi auth refresh
```

> `omi auth refresh` یوازې د هغو پروفایلونو لپاره کار کوي چې د براوزر (OAuth) له لارې ننوتلي دي. د API کیلي پر بنسټ پروفایلونو لپاره د تازه کولو لپاره هیڅ نشته او کمانډ د «Nothing to refresh» پیغام او د وتلو کوډ `1` سره پای ته رسېږي.

وتل:
```bash
omi auth logout
# که OMI_API_KEY په چاپېریال کې ټاکل شوی وي، هغه هم لرې کړئ (Bash/Zsh: `unset OMI_API_KEY`).
```

---

## ۳. اصلي کمانډونه

### یادونه (Memories)
منظم حقایق او شرایطي مشاهدې چې Omi زېرمه کړي دي:

```bash
# یادونه لیست کړئ
omi memory list

# له کټګورۍ سره نوی یاد جوړ کړئ
omi memory create "د Python بېلګو سره لنډ تخنیکي ځوابونه غوره ګڼم" --category work

# له ID سره یو ځانګړی یاد ترلاسه کړئ
omi memory get <MEMORY_ID>
```

### خبرې اترې (Conversations)
غږیز ثبتونه، لیکل شوي متنونه او هغه خبرې چې د Omi وسایلو ثبت کړي دي:

```bash
# وروستۍ ۵ خبرې اترې لیست کړئ
omi conversation list --limit 5

# د یوې خبرې اترې جزئیات د بشپړ متن سره ترلاسه کړئ
omi conversation get <CONVERSATION_ID> --include-transcript
```

### د عمل توکي (Action Items)
هغه کارونه چې له خبرو اترو څخه په اتومات ډول ایستل شوي دي:

```bash
# خلاص د عمل توکي لیست کړئ
omi action-item list --open

# یو د عمل توکی د بشپړ شوي په توګه نښه کړئ
omi action-item complete <ACTION_ITEM_ID>
```

### موخې (Goals)
د پرمختګ شاخصونه او اوږدمهاله موخې:

```bash
# فعالې موخې لیست کړئ
omi goal list

# نوې شمېرنیزه موخه جوړه کړئ
omi goal create "هره ورځ ۲ لیټره اوبه وڅښئ" --type numeric --target 2 --unit liters

# د موخې اوسنی ارزښت تازه کړئ (ID او نوی ارزښت)
omi goal progress <GOAL_ID> 1.5
```

---

## ۴. منظم اتومات کول او JSON محصول (`--json`)

`omi-cli` په پایپ‌لاینونو او د وسایلو ځنځیرونو کې د اتومات کولو لپاره جوړ شوی دی. نړیوال `--json` فلاګ پاک او ماشین-لوستونکی JSON بېرته راګرځوي:

```bash
# یادونه د JSON په توګه لیست کړئ او له jq سره یې فلټر کړئ
omi --json memory list | jq '.[] | {id, content, category}'

# د وروستیو خبرو اترو سرلیکونه ترلاسه کړئ
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# ټول خلاص د عمل توکي په خام JSON کې وګورئ
omi --json action-item list --open | jq '.'
```

> **مهمه ګرامري قاعده:**
> `--json` یو **نړیوال اختیار** دی او باید له فرعي کمانډ څخه **مخکې** کېښودل شي:
> * سم: `omi --json memory list`
> * ناسم: `omi memory list --json`

### پاڼه بندي (Pagination)
د `list` کمانډونه `--limit` او `--offset` ملاتړ کوي:

```bash
omi --json memory list --limit 50 --offset 50
```

### فایل ته صادرول
د دې لپاره چې ANSI رنګونه یا کنټرول توري فایل ککړ نه کړي، stdout مستقیم په شېل کې ولېږدوئ:

```bash
# یادونه مستقیم یو پاک JSON فایل ته صادر کړئ
omi --json memory list > memories.json
```

---

## ۵. د وتلو کوډونه (Exit Codes Contract)

په CI/CD او سکریپټونو کې د باوري تېروتنې اداره کولو لپاره، `omi-cli` د وتلو کوډونو یو سخت تړون تعقیبوي (وګورئ `omi_cli/errors.py`):

| کوډ | نوم | توضیح او بېلګه |
| :---: | :--- | :--- |
| `0` | **بریالیتوب (`EXIT_OK`)** | عملیات پرته له تېروتنې بشپړ شو. |
| `1` | **د کارونې تېروتنه (`EXIT_USAGE`)** | د omi-cli خپلې د اعتبار تېروتنې: ناسازګار `--browser` او `--api-key`، په متقابل ننوتلو کې ناسم انتخاب، له stdin څخه تش ورودي، یا د API کیلي پروفایل پر `omi auth refresh`. |
| `2` | **د هویت تصدیق تېروتنه (`EXIT_AUTH`)** | ورک یا ناسم اعتبارنامه، یا پای ته رسېدلی سیشن. یادونه: ناپېژندل شوی فلاګ یا ورک استدلال هم د Click له خوا رد کېږي او له کوډ `2` سره وځي. |
| `3` | **د سرور تېروتنه (`EXIT_SERVER`)** | د Omi سرور څخه HTTP 5xx یا د شبکې پرېکېدل. |
| `4` | **د کچې محدودیت (`EXIT_RATE_LIMITED`)** | HTTP 429 — په لنډ وخت کې ډېرې غوښتنې. |
| `5` | **ونه موندل شو (`EXIT_NOT_FOUND`)** | HTTP 404 — غوښتل شوې سرچینه (یاد، خبرې اترې، د عمل توکی) شتون نه لري. |

---

## ۶. د مختلفو شېلونو لپاره بېلګې

### Bash / Zsh (Linux / macOS)
```bash
# د دې سیشن لپاره API کیلي وټاکئ
export OMI_API_KEY="omi_dev_ستاسو_اصلي_ټوکن"

# کمانډ وچلوئ او د وتلو کوډ وګورئ
omi --json memory list --limit 10
if [ $? -ne 0 ]; then
    echo "له Omi څخه د یادونو په ترلاسه کولو کې تېروتنه." >&2
fi
```

### PowerShell (Windows)
```powershell
# په PowerShell کې د چاپېریال متغیر تعریف کړئ
$env:OMI_API_KEY = "omi_dev_ستاسو_اصلي_ټوکن"

# د JSON محصول مستقیم PowerShell آبجکټ ته واړوئ
$memories = omi --json memory list | ConvertFrom-Json
$memories | Select-Object id, content, category

# له $LASTEXITCODE سره د تېروتنې کتنه
if ($LASTEXITCODE -ne 0) {
    Write-Error "د Omi کمانډ د وتلو کوډ $LASTEXITCODE سره ناکام شو."
}
```

---

## ۷. د ځایي ډیسکټاپ API ادغام (Omi Desktop)

کله چې Omi Desktop ستاسو په ماشین کې چلېږي (تلواله پورټ 47778)، تاسو کولی شئ پرته له کلاوډ څخه د تېرېدو مستقیم له ځایي شرایطو سره کار وکړئ:

```bash
# د ځایي API اړیکه تنظیم کړئ (د ټوکن د ساتنې لپاره د چاپېریال متغیرونه وکاروئ)
export OMI_LOCAL_API_URL="http://127.0.0.1:47778"
read -r -s -p "د Desktop ټوکن دننه کړئ: " OMI_LOCAL_TOKEN; echo
export OMI_LOCAL_TOKEN

# د ځایي اړیکې حالت تایید کړئ
omi --json local status

# په ځایي سکرین تاریخچه کې لټون وکړئ
omi --json local search-screen "ربعوار راپور" --days 7 --app Safari
```

د چاپېریال متغیرونو پر ځای تاسو کولی شئ تنظیمات په پروفایل کې خوندي کړئ: `omi local configure --url http://127.0.0.1:47778 --token ...`.

---

## ۸. د څو پروفایلونو اداره (Profiles)

د شخصي حساب، کاري پروفایل یا ازموینې چاپېریال ترمنځ د اسانه بدلون لپاره `--profile` وکاروئ. تنظیمات په `~/.omi/config.toml` کې خوندي کېږي. د لومړیتوب ترتیب: د `--profile` فلاګ، بیا د `OMI_PROFILE` چاپېریال متغیر، او په پای کې `default` پروفایل.

```bash
# شخصي پروفایل جوړ کړئ او ورننوځئ
omi --profile personal auth login

# کاري پروفایل جوړ کړئ او ورننوځئ
omi --profile work auth login

# له ځانګړي پروفایل سره کمانډ وچلوئ
omi --profile work memory list

# پروفایل د چاپېریال متغیر له لارې وټاکئ
export OMI_PROFILE=work
omi memory list

# د ازموینې لپاره دودیز پای ټکی وکاروئ
omi --profile staging --api-base https://api.staging.omi.me memory list
```

---

## ۹. امنیتي لارښوونې او غوره کړنې

* **کیلۍ په کوډ کې مه لیکئ:** هیڅکله API کیلۍ (`omi_dev_*`) Git ذخیره ته کمېټ مه کوئ. هغه `.env` فایلونه وکاروئ چې په `.gitignore` کې دي، یا خوندي د رازونو مدیران.
* **د شېل تاریخچه وساتئ:** پر شریکو سرورونو کیلۍ د کمانډ-لاین د ښکاره استدلال په توګه مه لېږدوئ؛ متقابل ننوتل یا `OMI_API_KEY` وکاروئ.
* **د فولډر اجازې محدودې کړئ:** په Unix/macOS کې ډاډ ترلاسه کړئ چې د تنظیماتو فولډر محدودې اجازې لري:
  ```bash
  chmod 700 ~/.omi
  chmod 600 ~/.omi/config.toml 2>/dev/null || true
  ```
* **د سیشن پاکول:** د لنډمهاله چاپېریالونو د لرې کولو پر مهال، د چاپېریال متغیر لرې کول مه هېروئ:
  ```bash
  unset OMI_API_KEY
  ```
