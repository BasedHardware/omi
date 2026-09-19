# omi-cli kwa ajili ya maajenti

> Mwongozo wa vitendo kwa mifumo inayoendeshwa na LLM (Claude Code, Cursor, roboti zako binafsi).

## Kwa nini CLI hii inafaa kwa maajenti

* **Mkataba thabiti wa JSON.** `--json` hutoa hati halali ya JSON kwenye stdout na
  *tu* hati ya JSON — hakuna jumbe za maendeleo, hakuna vinyago vinavyozunguka. Hitilafu hupelekwa
  kwenye stderr kama `{"error": "...", "detail": "..."}`.
* **Misimbo thabiti ya kutoka.** `0` sawa / `1` kosa la matumizi / `2` uthibitishaji /
  `3` hitilafu ya seva / `4` kikomo cha kasi kimefikiwa / `5` haijapatikana. Maajenti wanaweza kugawanya
  mantiki kulingana na misimbo hii bila kuchambua hitilafu za lugha asilia.
* **Hakuna maelekezo shirikishi katika mazingira yasiyo na kiolesura (headless).** Pitisha `--yes` (au `-y`)
  kwa amri zinazoweza kufuta data; pitisha `--api-key` au weka `OMI_API_KEY` ili kuruka kuingia kwa maingiliano.
* **Mwenendo wa kusamehe wa kujaribu tena.** Hitilafu za `429` na `5xx` hujaribiwa tena kiotomatiki
  kwa kucheleweshwa (backoff) kabla ya kurudishwa.

## Uthibitishaji (mara moja, unaofanywa na binadamu)

Mtumiaji anapata ufunguo wa API ya msanidi programu kutoka kwa programu ya wavuti ya Omi
(`https://app.omi.me` → Developer → API Keys) na kisha huchagua mojawapo ya njia hizi:

```bash
omi auth login                          # kubandika kwa maingiliano; ufunguo hauhifadhiwi kwenye historia ya shell
# au
export OMI_API_KEY=omi_dev_...          # ya muda mfupi, inafaa kwa makontena
```

## Mambo matano ambayo maajenti hufanya zaidi

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

### 4. Kusoma vipengee vya utekelezaji vilivyo wazi

```bash
omi action-item list --json --open
```

### 5. Kuweka alama kuwa kipengee kimekamilika

```bash
omi action-item complete --json a1b2c3d4
```

## API ya Eneo Kazi ya Karibu (Local Desktop API)

Wakati Omi Desktop inapofungua API yake ya ndani, maajenti wanaweza kuuliza historia ya skrini,
muhtasari, SQL na majukumu kwenye kifaa chenyewe bila kutumia dev API ya wingu:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# au kwa vipindi vya muda mfupi:
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

Kamilisha au futa majukumu pale tu mtumiaji anapoomba waziwazi:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

Amri ya `omi local screenshot SCREENSHOT_ID --output PATH` huandika picha ya skrini kwenye diski
na inaendelea kutoa JSON kwenye stdout kwa matumizi ya hati. Kitambulisho cha picha ya skrini kwa kawaida hutoka
kwenye `local search-screen` au swali la SQL kwenye jedwali la `screenshots`. Ikiwa Desktop itarejesha
hitilafu iliyopangwa kama `screenshot_pending`, `screenshot_file_missing` au `screenshot_chunk_corrupted`,
hali ya JSON huhifadhi sehemu za `reason`, `hint` na `screenshot_id` kwenye stderr, ikiruhusu maajenti kujaribu
tena kwa kitambulisho cha zamani au kueleza kizuizi halisi. Thibitisha faili zilizofanikiwa kwa `file PATH` kabla
ya kuzipitisha kwa zana za kuona.

## Mfano wa vitendo: mzunguko wa ajenti wa Python

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

## Kushughulikia vikomo vya kasi ya maombi (rate limits)

Kumbukumbu: 120/saa. Mazungumzo: 25/saa. Uundaji wa wingi: 15/saa.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Vidokezo

* Tumia `--profile <jina>` ikiwa ajenti wako anasimamia akaunti nyingi za Omi. Kila wasifu
  unayo hati tambulishi na anwani yake ya msingi ya API.
* Tumia `--api-base http://localhost:8080` kwa majaribio ya mifumo ya ndani.
* Tumia `OMI_LOCAL_API_URL` na `OMI_LOCAL_TOKEN` ili kubadilisha mipangilio ya ndani ya
  Desktop API ya wasifu kwa ajili ya mzunguko mmoja.
* Tumia `--verbose` kwa utatuzi — inarekodi `METHOD path → status (Ns)` kwenye stderr
  bila kuathiri stdout, kwa hivyo hali ya JSON inabaki halali.
* Ili kupitisha maudhui kwenye mazungumzo kupitia bomba (pipe), tumia `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
