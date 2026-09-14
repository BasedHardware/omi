# omi-cli အမြန်စတင်လမ်းညွှန် (Burmese Quickstart)

> Terminal မှ Omi ကို တိုက်ရိုက်အသုံးပြုရန် လက်တွေ့လမ်းညွှန် — developer များနှင့် အလိုအလျောက် AI agent များအတွက်။

`omi-cli` သည် [Omi](https://omi.me) ၏ developer API အတွက် တရားဝင် command-line interface ဖြစ်သည်။ စနစ်၏ အဓိကအစိတ်အပိုင်း လေးခုကို စနစ်တကျနှင့် အလိုအလျောက်လုပ်ဆောင်နိုင်သော နည်းလမ်းဖြင့် စီမံနိုင်သည် — မှတ်ဉာဏ်များ (memories)၊ စကားဝိုင်းများ (conversations)၊ လုပ်ဆောင်ရန်အချက်များ (action items) နှင့် ရည်မှန်းချက်များ (goals)။

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **တရားဝင်စာရွက်စာတမ်း:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Source code:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

Command အမည်များ၊ option များနှင့် program ၏ message များကို အင်္ဂလိပ်ဘာသာဖြင့်သာ ထားရှိသည်။ ဤလမ်းညွှန်၏ ရှင်းလင်းချက်စာသားကိုသာ မြန်မာဘာသာဖြင့် ရေးထားသည်။ အင်္ဂလိပ် README သည် အဓိကရည်ညွှန်းချက်ဖြစ်သည်။

---

## ၁။ တပ်ဆင်ခြင်း

Dependency ပဋိပက္ခများကို ရှောင်ရှားပြီး CLI ကို သီးခြားပတ်ဝန်းကျင်တွင် လည်ပတ်ရန် `pipx` ကို အကြံပြုပါသည် —

```bash
# အကြံပြုချက်: pipx ဖြင့် သီးခြားတပ်ဆင်ခြင်း
pipx install omi-cli

# အခြားနည်းလမ်း: active ဖြစ်နေသော Python virtual environment အတွင်း pip ဖြင့်
pip install omi-cli
```

> **သတိပြုရန်: Package အမည်နှင့် Command အမည်**
> * PyPI ရှိ package အမည်မှာ **`omi-cli`** ဖြစ်သည် (`omi` ဟူသော အမည်သည် မသက်ဆိုင်သော package တစ်ခု ဖြစ်သည်)။
> * Terminal တွင် လည်ပတ်ရမည့် command မှာ **`omi`** သာ ဖြစ်သည်။

တပ်ဆင်မှု အောင်မြင်ကြောင်း စစ်ဆေးပါ —

```bash
omi --version
omi --help
```

Terminal က `omi` ကို ရှာမတွေ့ပါက virtual environment active ဖြစ်နေခြင်း သို့မဟုတ် `pipx` က executable များထည့်သော directory သည် `PATH` တွင် ပါဝင်ခြင်း ရှိမရှိ စစ်ဆေးပါ။

---

## ၂။ အထောက်အထားစိစစ်ခြင်း (Authentication)

`omi-cli` သည် အဓိက authentication နည်းလမ်း နှစ်မျိုးကို ထောက်ပံ့သည် —

| နည်းလမ်း | အသုံးပြုရန်နေရာ | ဥပမာ |
| :--- | :--- | :--- |
| **Developer API key (`omi_dev_*`)** | Script များ၊ CI/CD၊ headless server များ၊ AI agent များ | `omi auth login --api-key ...` သို့မဟုတ် `OMI_API_KEY` |
| **Browser OAuth (Google/Apple)** | Local workstation များနှင့် developer များ | `omi auth login --browser` (Google) / `--provider apple` |

### Interactive login
နည်းလမ်းကို interactive ရွေးချယ်ရန် flag မပါဘဲ လည်ပတ်ပါ —

```bash
omi auth login
# 1) Browser — Google login အတွက် browser ကို ဖွင့်သည် (Apple အတွက် `--provider apple` သုံးပါ)
# 2) API key — app.omi.me မှ API key ကို paste လုပ်ပါ (ထည့်သွင်းမှုကို ဖုံးကွယ်ထားသည်)
```

### Browser ဖြင့် တိုက်ရိုက် login
```bash
# Default: Google login
omi auth login --browser

# အခြားရွေးချယ်စရာ: Apple login
omi auth login --browser --provider apple
```

### Developer API key အသုံးပြုခြင်း
[app.omi.me](https://app.omi.me) တွင် **Developer → API Keys** အောက်၌ key တစ်ခု ဖန်တီးပါ —

```bash
# Key ကို active local profile တွင် သိမ်းဆည်းပါ
omi auth login --api-key omi_dev_သင့်_အမှန်တကယ်_token

# သို့မဟုတ် environment variable အဖြစ် သတ်မှတ်ပါ (container နှင့် CI/CD အတွက် အကောင်းဆုံး)
export OMI_API_KEY="omi_dev_သင့်_အမှန်တကယ်_token"
```

> `OMI_API_KEY` ကို active profile တွင် သိမ်းထားသော key မရှိမှသာ အသုံးပြုသည်။ `omi auth login` ဖြင့် ယခင်က login ဝင်ထားပြီး environment variable ကို အသက်ဝင်စေလိုပါက `omi auth logout` ကို အရင်လည်ပတ်ပါ။

### Authentication အခြေအနေ စစ်ဆေးခြင်း
* `omi auth status` — active profile နှင့် ဖုံးကွယ်ထားသော credential ကို ပြသသည် (local/offline လည်ပတ်သည်၊ သက်တမ်းကုန်ဆုံးရက်သည် OAuth token များအတွက်သာ ဖြစ်သည်)။
* `omi auth whoami` — Credential ခိုင်လုံမှုကို အတည်ပြုရန် Omi server သို့ တောင်းဆိုမှု ပို့သည် (network လိုအပ်သည်)။

```bash
omi auth status
omi auth whoami
```

ပြန်လည် login မဝင်ဘဲ OAuth token ကို refresh လုပ်ခြင်း —

```bash
omi auth refresh
```

> `omi auth refresh` သည် browser (OAuth) ဖြင့် login ဝင်ထားသော profile များအတွက်သာ အလုပ်လုပ်သည်။ API key အခြေခံ profile များတွင် refresh လုပ်စရာ မရှိသဖြင့် command သည် «Nothing to refresh» ဟူသော message နှင့် exit code `1` ဖြင့် ပြီးဆုံးသည်။

Logout —
```bash
omi auth logout
# OMI_API_KEY ကို environment တွင် သတ်မှတ်ထားပါက ၎င်းကိုလည်း ဖယ်ရှားပါ (Bash/Zsh: `unset OMI_API_KEY`)။
```

---

## ၃။ အဓိက command များ

### မှတ်ဉာဏ်များ (Memories)
Omi သိမ်းဆည်းထားသော စနစ်တကျအချက်အလက်များနှင့် အခြေအနေဆိုင်ရာ မှတ်ချက်များ —

```bash
# မှတ်ဉာဏ်များကို စာရင်းပြပါ
omi memory list

# Category ဖြင့် မှတ်ဉာဏ်အသစ် ဖန်တီးပါ
omi memory create "Python ဥပမာများပါသော တိုတောင်းသည့် နည်းပညာအဖြေများကို ပိုနှစ်သက်သည်" --category work

# ID ဖြင့် သီးခြားမှတ်ဉာဏ်တစ်ခုကို ယူပါ
omi memory get <MEMORY_ID>
```

### စကားဝိုင်းများ (Conversations)
Omi စက်ပစ္စည်းများက မှတ်တမ်းတင်ထားသော အသံဖမ်းချက်များ၊ transcript များနှင့် စကားပြောဆိုမှုများ —

```bash
# နောက်ဆုံး စကားဝိုင်း ၅ ခုကို စာရင်းပြပါ
omi conversation list --limit 5

# Transcript အပြည့်အစုံ ပါဝင်သော စကားဝိုင်းတစ်ခု၏ အသေးစိတ်ကို ယူပါ
omi conversation get <CONVERSATION_ID> --include-transcript
```

### လုပ်ဆောင်ရန်အချက်များ (Action Items)
စကားဝိုင်းများမှ အလိုအလျောက် ထုတ်ယူထားသော လုပ်ငန်းများ —

```bash
# မပြီးသေးသော action item များကို စာရင်းပြပါ
omi action-item list --open

# Action item တစ်ခုကို ပြီးစီးကြောင်း အမှတ်အသားပြုပါ
omi action-item complete <ACTION_ITEM_ID>
```

### ရည်မှန်းချက်များ (Goals)
တိုးတက်မှုညွှန်းကိန်းများနှင့် ရေရှည်ရည်မှန်းချက်များ —

```bash
# Active ရည်မှန်းချက်များကို စာရင်းပြပါ
omi goal list

# ကိန်းဂဏန်း ရည်မှန်းချက်အသစ် ဖန်တီးပါ
omi goal create "နေ့စဉ် ရေ ၂ လီတာ သောက်ရန်" --type numeric --target 2 --unit liters

# ရည်မှန်းချက်တစ်ခု၏ လက်ရှိတန်ဖိုးကို update လုပ်ပါ (ID နှင့် တန်ဖိုးအသစ်)
omi goal progress <GOAL_ID> 1.5
```

---

## ၄။ စနစ်တကျ automation နှင့် JSON output (`--json`)

`omi-cli` ကို pipeline များနှင့် toolchain များတွင် automation အတွက် တည်ဆောက်ထားသည်။ Global `--json` flag သည် သန့်ရှင်းပြီး machine-readable JSON ကို ပြန်ပေးသည် —

```bash
# မှတ်ဉာဏ်များကို JSON အဖြစ် စာရင်းပြပြီး jq ဖြင့် စစ်ထုတ်ပါ
omi --json memory list | jq '.[] | {id, content, category}'

# နောက်ဆုံးစကားဝိုင်းများ၏ ခေါင်းစဉ်များကို ယူပါ
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# မပြီးသေးသော action item အားလုံးကို raw JSON ဖြင့် ကြည့်ပါ
omi --json action-item list --open | jq '.'
```

> **အရေးကြီးသော syntax စည်းမျဉ်း —**
> `--json` သည် **global option** ဖြစ်ပြီး subcommand ၏ **ရှေ့တွင်** ထားရမည် —
> * မှန်: `omi --json memory list`
> * မှား: `omi memory list --json`

### စာမျက်နှာခွဲခြင်း (Pagination)
`list` command များသည် `--limit` နှင့် `--offset` ကို ထောက်ပံ့သည် —

```bash
omi --json memory list --limit 50 --offset 50
```

### ဖိုင်သို့ export လုပ်ခြင်း
ANSI အရောင်များ သို့မဟုတ် control character များ ဖိုင်ထဲ မဝင်စေရန် shell တွင် stdout ကို တိုက်ရိုက် redirect လုပ်ပါ —

```bash
# မှတ်ဉာဏ်များကို သန့်ရှင်းသော JSON ဖိုင်သို့ တိုက်ရိုက် export လုပ်ပါ
omi --json memory list > memories.json
```

---

## ၅။ Exit code များ (Exit Codes Contract)

CI/CD နှင့် script များတွင် ယုံကြည်စိတ်ချရသော error ကိုင်တွယ်မှုအတွက် `omi-cli` သည် တင်းကျပ်သော exit code စာချုပ်ကို လိုက်နာသည် (`omi_cli/errors.py` ကို ကြည့်ပါ) —

| Code | အမည် | ရှင်းလင်းချက်နှင့် ဥပမာ |
| :---: | :--- | :--- |
| `0` | **အောင်မြင် (`EXIT_OK`)** | လုပ်ဆောင်ချက် error မရှိဘဲ ပြီးစီးသည်။ |
| `1` | **အသုံးပြုမှု error (`EXIT_USAGE`)** | omi-cli ၏ ကိုယ်ပိုင် validation error များ — အတူသုံး၍မရသော `--browser` နှင့် `--api-key`၊ interactive login တွင် မမှန်ကန်သော ရွေးချယ်မှု၊ stdin မှ ဗလာ input၊ သို့မဟုတ် API key profile တွင် `omi auth refresh`။ |
| `2` | **Authentication error (`EXIT_AUTH`)** | Credential မရှိခြင်း သို့မဟုတ် မမှန်ကန်ခြင်း၊ သို့မဟုတ် session သက်တမ်းကုန်ခြင်း။ သတိပြုရန် — မသိသော flag သို့မဟုတ် ပျောက်နေသော argument ကို Click ကိုယ်တိုင်က ပယ်ချပြီး code `2` ဖြင့် ထွက်သည်။ |
| `3` | **Server error (`EXIT_SERVER`)** | Omi server မှ HTTP 5xx သို့မဟုတ် network ပြတ်တောက်မှု။ |
| `4` | **Rate limit (`EXIT_RATE_LIMITED`)** | HTTP 429 — အချိန်တိုအတွင်း တောင်းဆိုမှု အလွန်များခြင်း။ |
| `5` | **ရှာမတွေ့ (`EXIT_NOT_FOUND`)** | HTTP 404 — တောင်းဆိုထားသော resource (မှတ်ဉာဏ်၊ စကားဝိုင်း၊ action item) မရှိပါ။ |

---

## ၆။ Shell အမျိုးမျိုးအတွက် ဥပမာများ

### Bash / Zsh (Linux / macOS)
```bash
# ဤ session အတွက် API key သတ်မှတ်ပါ
export OMI_API_KEY="omi_dev_သင့်_အမှန်တကယ်_token"

# Command လည်ပတ်ပြီး exit code စစ်ဆေးပါ
omi --json memory list --limit 10
if [ $? -ne 0 ]; then
    echo "Omi မှ မှတ်ဉာဏ်များ ယူရာတွင် error ဖြစ်သည်။" >&2
fi
```

### PowerShell (Windows)
```powershell
# PowerShell တွင် environment variable သတ်မှတ်ပါ
$env:OMI_API_KEY = "omi_dev_သင့်_အမှန်တကယ်_token"

# JSON output ကို PowerShell object အဖြစ် တိုက်ရိုက်ပြောင်းပါ
$memories = omi --json memory list | ConvertFrom-Json
$memories | Select-Object id, content, category

# $LASTEXITCODE ဖြင့် error စစ်ဆေးပါ
if ($LASTEXITCODE -ne 0) {
    Write-Error "Omi command သည် exit code $LASTEXITCODE ဖြင့် မအောင်မြင်ပါ။"
}
```

---

## ၇။ Local Desktop API ချိတ်ဆက်ခြင်း (Omi Desktop)

Omi Desktop သည် သင့်စက်တွင် လည်ပတ်နေပါက (default port 47778) cloud ကို မဖြတ်ဘဲ local context နှင့် တိုက်ရိုက် အလုပ်လုပ်နိုင်သည် —

```bash
# Local API ချိတ်ဆက်မှုကို configure လုပ်ပါ (token ကို ကာကွယ်ရန် environment variable သုံးပါ)
export OMI_LOCAL_API_URL="http://127.0.0.1:47778"
read -r -s -p "Desktop token ထည့်ပါ: " OMI_LOCAL_TOKEN; echo
export OMI_LOCAL_TOKEN

# Local ချိတ်ဆက်မှု အခြေအနေကို အတည်ပြုပါ
omi --json local status

# Local screen history တွင် ရှာဖွေပါ
omi --json local search-screen "သုံးလပတ် အစီရင်ခံစာ" --days 7 --app Safari
```

Environment variable များအစား ဆက်တင်များကို profile တွင် သိမ်းနိုင်သည် — `omi local configure --url http://127.0.0.1:47778 --token ...`။

---

## ၈။ Profile များစွာ စီမံခြင်း (Profiles)

ကိုယ်ပိုင်အကောင့်၊ အလုပ် profile သို့မဟုတ် စမ်းသပ်ပတ်ဝန်းကျင်တို့အကြား လွယ်ကူစွာ ပြောင်းလဲရန် `--profile` ကို သုံးပါ။ ဆက်တင်များကို `~/.omi/config.toml` တွင် သိမ်းဆည်းသည်။ ဦးစားပေးအစီအစဉ် — `--profile` flag၊ ထို့နောက် `OMI_PROFILE` environment variable၊ နောက်ဆုံး `default` profile။

```bash
# ကိုယ်ပိုင် profile ဖန်တီးပြီး login ဝင်ပါ
omi --profile personal auth login

# အလုပ် profile ဖန်တီးပြီး login ဝင်ပါ
omi --profile work auth login

# သီးခြား profile ဖြင့် command လည်ပတ်ပါ
omi --profile work memory list

# Environment variable ဖြင့် profile ရွေးပါ
export OMI_PROFILE=work
omi memory list

# စမ်းသပ်ရန်အတွက် custom endpoint သုံးပါ
omi --profile staging --api-base https://api.staging.omi.me memory list
```

---

## ၉။ လုံခြုံရေးလမ်းညွှန်ချက်များနှင့် အကောင်းဆုံးအလေ့အကျင့်များ

* **Key များကို code ထဲ မထည့်ပါနှင့် —** API key များ (`omi_dev_*`) ကို Git repository သို့ ဘယ်တော့မှ commit မလုပ်ပါနှင့်။ `.gitignore` တွင် ထည့်ထားသော `.env` ဖိုင်များ သို့မဟုတ် လုံခြုံသော secret manager များကို သုံးပါ။
* **Shell history ကို ကာကွယ်ပါ —** မျှဝေသုံးသော server များတွင် key များကို command-line argument အဖြစ် တိုက်ရိုက် မပေးပါနှင့်။ Interactive login သို့မဟုတ် `OMI_API_KEY` ကို သုံးပါ။
* **Directory ခွင့်ပြုချက်များကို ကန့်သတ်ပါ —** Unix/macOS တွင် configuration directory ၏ ခွင့်ပြုချက်များ ကန့်သတ်ထားကြောင်း သေချာပါစေ —
  ```bash
  chmod 700 ~/.omi
  chmod 600 ~/.omi/config.toml 2>/dev/null || true
  ```
* **Session ရှင်းလင်းခြင်း —** ယာယီပတ်ဝန်းကျင်များကို ဖျက်သိမ်းသောအခါ environment variable ကို ဖယ်ရှားရန် မမေ့ပါနှင့် —
  ```bash
  unset OMI_API_KEY
  ```
