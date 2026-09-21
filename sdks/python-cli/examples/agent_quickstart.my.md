# အေးဂျင့်များအတွက် omi-cli

> LLM စနစ်များ (Claude Code, Cursor, သင်၏ ကိုယ်ပိုင် bot များ) အတွက် လက်တွေ့ကျသော လမ်းညွှန်။

## CLI သည် အေးဂျင့်များအတွက် အဘယ်ကြောင့် အဆင်ပြေစေသနည်း

* **တည်ငြိမ်သော JSON သတ်မှတ်ချက်။** `--json` သည် stdout သို့ တရားဝင် JSON စာရွက်စာတမ်းနှင့်
  JSON စာရွက်စာတမ်းကို *သာ* ထုတ်ပေးပါသည် — လုပ်ဆောင်မှု မက်ဆေ့ဂျ်များ သို့မဟုတ် လည်ပတ်နေသော animation များ
  မပါဝင်ပါ။ အမှားများကို stderr သို့ `{"error": "...", "detail": "..."}` အဖြစ် ပို့ဆောင်ပေးပါသည်။
* **တည်ငြိမ်သော exit codes များ။** `0` အောင်မြင် / `1` အသုံးပြုမှု အမှား / `2` စစ်ဆေးမှု အမှား /
  `3` ဆာဗာ အမှား / `4` တောင်းဆိုမှု ကန့်သတ်ချက်ကျော်လွန်ခြင်း (rate limited) / `5` မတွေ့ရှိပါ။
  အေးဂျင့်များသည် သဘာဝဘာသာစကား အမှားများကို ခွဲခြမ်းစိတ်ဖြာရန် မလိုဘဲ ဤကုဒ်များပေါ်တွင် တိုက်ရိုက် ဆုံးဖြတ်ချက် ချနိုင်ပါသည်။
* **မျက်နှာပြင်မဲ့ (headless) အခြေအနေများတွင် အပြန်အလှန် မေးမြန်းမှုများ မရှိခြင်း။** အပြောင်းအလဲ ပြုလုပ်သော
  command များသို့ `--yes` (သို့မဟုတ် `-y`) ထည့်သွင်းပါ; အပြန်အလှန် စကားဝှက်ရိုက်ထည့်ခြင်းကို ကျော်လွှားရန်
  `--api-key` ထည့်သွင်းပါ သို့မဟုတ် `OMI_API_KEY` ပတ်ဝန်းကျင် ပြောင်းလဲနိုင်သော တန်ဖိုးကို သတ်မှတ်ပါ။
* **အလိုအလျောက် ပြန်လည်ကြိုးစားမှု စနစ်။** `429` နှင့် `5xx` အမှားများသည် ပြသခြင်း မပြုမီ နှောင့်နှေးမှုဖြင့်
  အလိုအလျောက် ပြန်လည်ကြိုးစားပေးပါသည်။

## အထောက်အထား စစ်ဆေးခြင်း (လူသားတစ်ဦးမှ တစ်ကြိမ်သာ ပြုလုပ်ရန်)

အသုံးပြုသူသည် Omi ဝဘ်အက်ပ်မှ developer API key ကို ရယူပြီး
(`https://app.omi.me` → Developer → API Keys) အောက်ပါတို့အနက် တစ်ခုကို ရွေးချယ်သည် -

```bash
omi auth login                          # အပြန်အလှန် ကူးယူထည့်သွင်းခြင်း; shell မှတ်တမ်းတွင် key မကျန်ရှိပါ
# သို့မဟုတ်
export OMI_API_KEY=omi_dev_...          # ယာယီ၊ container များအတွက် အဆင်ပြေသည်
```

## အေးဂျင့်များ အများဆုံး လုပ်ဆောင်သည့် အချက် ၅ ချက်

### 1. မှတ်ဉာဏ်များကို ဖတ်ရှုခြင်း

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. မှတ်ဉာဏ်အသစ် ဖန်တီးခြင်း

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. စကားပြောဆိုမှုများကို ဖတ်ရှုခြင်း

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. မပြီးပြတ်သေးသော လုပ်ဆောင်ချက်များကို ဖတ်ရှုခြင်း

```bash
omi action-item list --json --open
```

### 5. လုပ်ဆောင်ချက်ကို ပြီးစီးကြောင်း မှတ်သားခြင်း

```bash
omi action-item complete --json a1b2c3d4
```

## ဒေသတွင်း Desktop API (Local Desktop API)

Omi Desktop သည် ၎င်း၏ local API ကို ဖွင့်ထားသည့်အခါ အေးဂျင့်များသည် cloud developer API ကို
အသုံးမပြုဘဲ စက်ပေါ်ရှိ မျက်နှာပြင်မှတ်တမ်း၊ အကျဉ်းချုပ်များ၊ SQL နှင့် လုပ်ဆောင်ချက်များကို မေးမြန်းနိုင်ပါသည် -

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# သို့မဟုတ် ယာယီ session များအတွက် -
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

အသုံးပြုသူက ရှင်းလင်းစွာ တောင်းဆိုသည့်အခါမှသာ လုပ်ဆောင်ချက်များကို ပြီးစီးအောင် သို့မဟုတ် ဖျက်ပစ်ပါ -

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` သည် မျက်နှာပြင်ဓာတ်ပုံကို disk တွင် ရေးသားပြီး
script များအတွက် stdout သို့ JSON ဆက်လက် ထုတ်ပေးပါသည်။ မျက်နှာပြင်ဓာတ်ပုံ ID ကို အများအားဖြင့်
`local search-screen` သို့မဟုတ် `screenshots` ဇယားရှိ SQL query မှ ရရှိပါသည်။ အကယ်၍ Desktop သည်
`screenshot_pending`, `screenshot_file_missing` သို့မဟုတ် `screenshot_chunk_corrupted` ကဲ့သို့သော
ဖွဲ့စည်းပုံဆိုင်ရာ အမှားကို ပြန်ပို့ပါက JSON စနစ်သည် `reason`, `hint` နှင့် `screenshot_id` အကွက်များကို
stderr တွင် ထိန်းသိမ်းထားသောကြောင့် အေးဂျင့်များသည် ယခင် ID ဖြင့် ထပ်မံကြိုးစားနိုင်သည် သို့မဟုတ်
အတားအဆီးကို တိကျစွာ အစီရင်ခံနိုင်ပါသည်။ အောင်မြင်သော ရလဒ်များကို vision ကိရိယာများသို့ မပို့မီ `file PATH` ဖြင့် စစ်ဆေးပါ။

## လက်တွေ့ ဥပမာ - Python အေးဂျင့် စက်ဝန်း

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """JSON စနစ်ဖြင့် omi CLI ကို ခေါ်ယူပြီး မအောင်မြင်သော exit code များတွင် အမှားထုတ်ပေးသည်။"""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI သည် JSON စနစ်တွင် stderr သို့ ဖွဲ့စည်းပုံဆိုင်ရာ အမှားများကို ထုတ်ပေးသည် -
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# မပြီးသေးသော လုပ်ဆောင်ချက်အားလုံးကို ဖတ်ပြီး ရက် ၃၀ ကျော်သည်များကို ပြီးစီးကြောင်း မှတ်သားပါ။
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## တောင်းဆိုမှု ကန့်သတ်ချက်များကို ကိုင်တွယ်ခြင်း

မှတ်ဉာဏ်များ - ၁၂၀/နာရီ။ စကားပြောဆိုမှုများ - ၂၅/နာရီ။ အစုလိုက် ဖန်တီးခြင်း - ၁၅/နာရီ။

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # ကန့်သတ်ချက် ကျော်လွန်သည်
    err = json.loads(result.stderr)
    # err["detail"] သည်: "Retry in 12s. ..." ကဲ့သို့ ဖြစ်သည်
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## အကြံပြုချက်များ

* အကယ်၍ သင်၏ အေးဂျင့်သည် Omi အကောင့်များစွာကို စီမံခန့်ခွဲပါက `--profile <name>` ကို အသုံးပြုပါ။
  ပရိုဖိုင်တစ်ခုစီတွင် ကိုယ်ပိုင် အထောက်အထားနှင့် API အခြေခံ ရှိပါသည်။
* ဒေသတွင်း backend စမ်းသပ်ခြင်းအတွက် `--api-base http://localhost:8080` ကို အသုံးပြုပါ။
* တစ်ကြိမ်တည်းအတွက် profile-local Desktop API ဆက်တင်များကို ပြောင်းလဲရန် `OMI_LOCAL_API_URL` နှင့်
  `OMI_LOCAL_TOKEN` ကို အသုံးပြုပါ။
* အမှားရှာဖွေရန်အတွက် `--verbose` ကို အသုံးပြုပါ — ၎င်းသည် stdout ကို မထိခိုက်စေဘဲ
  stderr သို့ `METHOD path → status (Ns)` ကို မှတ်တမ်းတင်ပေးသောကြောင့် JSON စနစ် ပျက်စီးမှု မရှိပါ။
* စကားပြောဆိုမှုထဲသို့ အကြောင်းအရာများ ထည့်သွင်းရန် `--text -` ကို အသုံးပြုပါ -
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
