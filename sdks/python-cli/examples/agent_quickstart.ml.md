# ഏജന്റുകൾക്കായുള്ള omi-cli

> LLM-നിർവഹിത ഏജന്റ് പരിതസ്ഥിതികൾക്കുള്ള (Claude Code, Cursor, നിങ്ങളുടെ സ്വന്തം ബോട്ടുകൾ) പ്രായോഗിക ഗൈഡ്.

## CLI എന്തുകൊണ്ട് ഏജന്റ്-സൗഹൃദമാണ്

* **സ്ഥിരതയുള്ള JSON കരാർ.** `--json` stdout-ലേക്ക് സാധുവായ ഒരു JSON രേഖ പുറപ്പെടുവിക്കുന്നു,
  *ഒരു JSON രേഖ മാത്രം* — പ്രോഗ്രസ് സന്ദേശങ്ങളില്ല, സ്പിന്നറുകളില്ല. പിശകുകൾ
  stderr-ലേക്ക് `{"error": "...", "detail": "..."}` രൂപത്തിൽ പോകുന്നു.
* **സ്ഥിരതയുള്ള എക്സിറ്റ് കോഡുകൾ.** `0` വിജയം / `1` തെറ്റായ ഉപയോഗം / `2` പ്രാമാണീകരണം /
  `3` സെർവർ / `4` നിരക്ക് പരിമിതം / `5` കണ്ടെത്തിയില്ല. സ്വാഭാവിക-ഭാഷാ പിശകുകൾ
  പാർസ് ചെയ്യാതെ തന്നെ ഏജന്റുകൾക്ക് ഈ കോഡുകളിൽ ശാഖകളുണ്ടാക്കാം.
* **ഹെഡ്‌ലെസ് സന്ദർഭങ്ങളിൽ സംവേദനാത്മക പ്രോംപ്റ്റുകളില്ല.** നാശകരമായ കമാൻഡുകൾക്ക്
  `--yes` (അല്ലെങ്കിൽ `-y`) നൽകുക; സംവേദനാത്മക ലോഗിൻ ഒഴിവാക്കാൻ `--api-key` നൽകുക
  അല്ലെങ്കിൽ `OMI_API_KEY` സെറ്റ് ചെയ്യുക.
* **ക്ഷമാശീലമുള്ള വീണ്ടും-ശ്രമം സ്വഭാവം.** `429`, `5xx` എന്നിവ പുറത്തുവരുന്നതിന് മുമ്പ്
  ബാക്കോഫോടെ വീണ്ടും ശ്രമിക്കുന്നു.

## പ്രാമാണീകരണം (ഒരിക്കൽ, മനുഷ്യനാൽ)

ഉപയോക്താവ് Omi വെബ് ആപ്പിൽ നിന്ന് (`https://app.omi.me` → Developer → API Keys) ഒരു ഡെവ്
API കീ നേടി, ഇവയിൽ ഒന്ന് തിരഞ്ഞെടുക്കുന്നു:

```bash
omi auth login                          # സംവേദനാത്മക പേസ്റ്റ്; കീ shell ചരിത്രത്തിൽ നിലനിൽക്കില്ല
# അല്ലെങ്കിൽ
export OMI_API_KEY=omi_dev_...          # താൽക്കാലികം, കണ്ടെയ്‌നർ-സൗഹൃദം
```

## ഏജന്റുകൾ ഏറ്റവും കൂടുതൽ ചെയ്യുന്ന അഞ്ച് കാര്യങ്ങൾ

### 1. ഓർമ്മകൾ വായിക്കുക

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. ഒരു ഓർമ്മ സൃഷ്ടിക്കുക

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. സംഭാഷണങ്ങൾ വായിക്കുക

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. തുറന്ന ആക്ഷൻ ഐറ്റങ്ങൾ വായിക്കുക

```bash
omi action-item list --json --open
```

### 5. ഒരു ആക്ഷൻ ഐറ്റം പൂർത്തിയാക്കുക

```bash
omi action-item complete --json a1b2c3d4
```

## ലോക്കൽ ഡെസ്ക്ടോപ്പ് API

Omi Desktop അതിന്റെ ലോക്കൽ API വെളിപ്പെടുത്തുമ്പോൾ, ക്ലൗഡ് ഡെവ് API ഉപയോഗിക്കാതെ
ഏജന്റുകൾക്ക് ഉപകരണത്തിലെ സ്ക്രീൻ ചരിത്രം, സംഗ്രഹങ്ങൾ, SQL, ടാസ്ക്കുകൾ എന്നിവ
ക്വറി ചെയ്യാം:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# അല്ലെങ്കിൽ, താൽക്കാലിക സെഷനുകൾക്ക്:
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

ഉപയോക്താവ് വ്യക്തമായി ആവശ്യപ്പെടുമ്പോൾ മാത്രം ടാസ്ക്കുകൾ പൂർത്തിയാക്കുകയോ
ഇല്ലാതാക്കുകയോ ചെയ്യുക:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` സ്ക്രീൻഷോട്ട് ഡിസ്കിലേക്ക് എഴുതുകയും
സ്ക്രിപ്റ്റുകൾക്കായി stdout-ലേക്ക് JSON അച്ചടിക്കുകയും ചെയ്യുന്നു. സ്ക്രീൻഷോട്ട് ഐഡി സാധാരണയായി
`local search-screen`-ൽ നിന്നോ `screenshots` ടേബിളിലെ SQL-ൽ നിന്നോ വരുന്നു. Desktop
`screenshot_pending`, `screenshot_file_missing` അല്ലെങ്കിൽ `screenshot_chunk_corrupted`
പോലുള്ള ഘടനാപരമായ പരാജയം തിരികെ നൽകിയാൽ, JSON മോഡ് stderr-ൽ `reason`, `hint`,
`screenshot_id` ഫീൽഡുകൾ സൂക്ഷിക്കുന്നു — അതിനാൽ ഏജന്റുകൾക്ക് പഴയ ഐഡിയുമായി വീണ്ടും
ശ്രമിക്കാനോ കൃത്യമായ തടസ്സം റിപ്പോർട്ട് ചെയ്യാനോ കഴിയും. വിഷൻ ടൂളുകളിലേക്ക്
അയയ്ക്കുന്നതിന് മുമ്പ് വിജയകരമായ ഔട്ട്പുട്ടുകൾ `file PATH` ഉപയോഗിച്ച് പരിശോധിക്കുക.

## പ്രവർത്തന ഉദാഹരണം: Python ഏജന്റ് ലൂപ്പ്

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """omi CLI JSON മോഡിൽ പ്രവർത്തിപ്പിക്കുന്നു, പരാജയ എക്സിറ്റ് കോഡുകളിൽ എക്സെപ്ഷൻ ഉയർത്തുന്നു."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI JSON മോഡിൽ stderr-ലേക്ക് ഘടനാപരമായ പിശകുകൾ അച്ചടിക്കുന്നു:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# എല്ലാ തുറന്ന ആക്ഷൻ ഐറ്റങ്ങളും വായിച്ച് 30 ദിവസത്തിലധികം പഴക്കമുള്ളവ പൂർത്തിയാക്കുക.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## നിരക്ക് പരിധികൾ കൈകാര്യം ചെയ്യൽ

ഓർമ്മകൾ: 120/മണിക്കൂർ. സംഭാഷണങ്ങൾ: 25/മണിക്കൂർ. ബാച്ച് സൃഷ്ടികൾ: 15/മണിക്കൂർ.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # നിരക്ക് പരിമിതം
    err = json.loads(result.stderr)
    # err["detail"] ഇങ്ങനെയിരിക്കും: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## നുറുങ്ങുകൾ

* നിങ്ങളുടെ ഏജന്റ് ഒന്നിലധികം Omi അക്കൗണ്ടുകൾ കൈകാര്യം ചെയ്യുന്നെങ്കിൽ `--profile <name>`
  ഉപയോഗിക്കുക. ഓരോ പ്രൊഫൈലിനും അതിന്റേതായ ക്രെഡൻഷ്യലുകളും API ബേസും ഉണ്ട്.
* ലോക്കൽ ബാക്കെൻഡ് പരിശോധനയ്ക്ക് `--api-base http://localhost:8080` ഉപയോഗിക്കുക.
* ഒരു റണ്ണിനായി പ്രൊഫൈൽ-ലോക്കൽ Desktop API ക്രമീകരണങ്ങൾ ഓവർറൈഡ് ചെയ്യാൻ
  `OMI_LOCAL_API_URL`, `OMI_LOCAL_TOKEN` എന്നിവ ഉപയോഗിക്കുക.
* ഡീബഗ്ഗിംഗിന് `--verbose` ഉപയോഗിക്കുക — ഇത് stderr-ലേക്ക് `METHOD path → status (Ns)`
  ലോഗ് ചെയ്യുന്നു, stdout-നെ ബാധിക്കുന്നില്ല, അതിനാൽ JSON മോഡ് സാധുവായി തുടരുന്നു.
* പൈപ്പിലൂടെ സംഭാഷണത്തിലേക്ക് ഉള്ളടക്കം അയയ്ക്കാൻ `--text -` ഉപയോഗിക്കുക:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
