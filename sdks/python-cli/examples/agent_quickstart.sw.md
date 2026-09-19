# omi-cli kwa Maajenti wa AI

> Mwongozo wa vitendo kwa mifumo inayoendeshwa na LLM (Claude Code, Cursor, roboti zako binafsi).

## Kwa nini CLI ni rafiki kwa maajenti

* **Mkataba thabiti wa JSON.** Bendera ya `--json` hutoa hati halali ya JSON kwa stdout na
  *hati ya JSON pekee* — hakuna ujumbe wa maendeleo, hakuna viashiria vya kupakia. Hitilafu
  hutumwa kwa stderr kama `{"error": "...", "detail": "..."}`.
* **Misimbo thabiti ya kutoka.** `0` sawa / `1` hitilafu ya matumizi / `2` uthibitishaji /
  `3` seva / `4` kikomo cha kasi kimevukwa / `5` haikupatikana. Maajenti wanaweza kugawanya
  mantiki moja kwa moja bila kuchanganua lugha asilia.
* **Hakuna maombi shirikishi katika mazingira yasiyo na kiolesura (headless).** Pitisha `--yes`
  (au `-y`) kwa amri zinazofuta; pitisha `--api-key` au weka `OMI_API_KEY` ili kuruka kuingia
  kwa mwingiliano.
* **Tabia ya kujaribu tena yenye uvumilivu.** Hitilafu za `429` na `5xx` hujaribiwa tena
  kiotomatiki kwa kucheleweshwa kulingana na muda (backoff) kabla ya kuripotiwa.

## Uthibitishaji (mara moja, na binadamu)

Mtumiaji anapata ufunguo wa API wa msanidi programu kutoka kwa programu ya wavuti ya Omi
(`https://app.omi.me` → Developer → API Keys) na kufanya mojawapo ya yafuatayo:

```bash
omi auth login                          # kubandika kwa maingiliano; ufunguo hauhifadhiwi katika historia ya shell
# au
export OMI_API_KEY=omi_dev_...          # ya muda, inafaa kwa vyombo (containers)
```

## Mambo matano ambayo maajenti hufanya mara nyingi

### 1. Kusoma kumbukumbu

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Kuunda kumbukumbu

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Kusoma mazungumzo

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Kusoma vipengee vya vitendo vilivyo wazi

```bash
omi action-item list --json --open
```

### 5. Kuweka alama kitendo kimekamilika

```bash
omi action-item complete --json a1b2c3d4
```

## API ya Ndani ya Desktop

Wakati Omi Desktop inapowezesha API yake ya ndani, maajenti wanaweza kuuliza historia ya
skrini ya kifaa, muhtasari, data ya SQL na kazi bila kutumia API ya wingu:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# au kwa vipindi vya muda:
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

Kamilisha au futa kazi pale tu mtumiaji anapoomba waziwazi:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

Amri `omi local screenshot SCREENSHOT_ID --output PATH` huhifadhi picha ya skrini kwenye diski
na bado huchapisha JSON kwa stdout kwa matumizi ya hati. Kitambulisho cha picha ya skrini kwa
kawaida hutoka kwa `local search-screen` au swali la SQL kwenye jedwali la `screenshots`. Ikiwa
Desktop itarejesha hitilafu iliyoundwa kama `screenshot_pending`, `screenshot_file_missing`, au
`screenshot_chunk_corrupted`, hali ya JSON huhifadhi sehemu za `reason`, `hint`, na `screenshot_id`
kwenye stderr ili maajenti waweze kujaribu kitambulisho cha zamani au kuripoti kizuizi halisi.
Thibitisha matokeo yaliyofanikiwa kwa amri ya `file PATH` kabla ya kuyapitisha kwa zana za maono.

## Mfano halisi: Mzunguko wa ajenti wa Python

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

## Kushughulikia vikomo vya maombi (Rate Limits)

Kumbukumbu: 120/saa. Mazungumzo: 25/saa. Uundaji wa makundi: 15/saa.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Vidokezo

* Tumia `--profile <name>` ikiwa ajenti wako anasimamia akaunti nyingi za Omi. Kila
  wasifu una vitambulisho na msingi wake wa API.
* Tumia `--api-base http://localhost:8080` kwa majaribio ya mfumo wa ndani.
* Tumia vigezo vya mazingira `OMI_LOCAL_API_URL` na `OMI_LOCAL_TOKEN` ili kubatilisha
  mipangilio ya ndani ya API ya Desktop kwa uendeshaji mmoja.
* Tumia `--verbose` kwa utatuzi — hurekodi `METHOD path → status (Ns)` kwa stderr
  bila kuathiri stdout, kwa hivyo hali ya JSON inabaki kuwa halali.
* Ili kupitisha maudhui kwenye mazungumzo, tumia `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
