# omi-cli kwa waagenti

> Mwongozo wa vitendo kwa LLM-driven harnesses (Claude Code, Cursor, bots zako).

## Kwa nini CLI ni rafiki kwa waagenti

* **Mkataba thabiti wa JSON.** `--json` hutolea JSON halali kwenye stdout na
  *tu* JSON — bila ujumbe wa maendeleo, bila spinners. Makosa huenda kwenye
  stderr kama `{"error": "...", "detail": "..."}`.
* **Nambari thabiti za kufunga.** `0` ok / `1` matumizi / `2` auth / `3` server / `4`
  kikomo cha mzunguko / `5` haikupatikana. Waagenti wanaweza matawi kulingana na hizi
  bila kuchambua makosa ya lugha ya kawaida.
* **Hakuna maswali ya mwingiliano katika mazingira ya headless.** Pisha `--yes` (au `-y`)
  kwa amri mbaya; pisha `--api-kunjia` au weka `OMI_API_KEY` kupita kuingia
  kwa mwingiliano.
* **Tabia ya kusamehe ya majaribio.** `429` na `5xx` hujaribiwa tena na backoff
  kabla ya kuonekana.

## Auth (mara moja, na mtumiaji)

Mtumiaji hupata kikimoja cha API cha maendeleo kutoka kwenye programu ya wavuti ya Omi
(`https://app.omi.me` → Developer → API Keys) na ama:

```bash
omi auth login                          # interactive paste; key not in shell history
# or
export OMI_API_KEY=omi_dev_...          # ephemeral, container-friendly
```

## Mambo matano ambayo waagenti hufanya zaidi

### 1. Soma kumbukumbu

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Tengeneza kumbukumbu

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Soma mazungumzo

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Soma vitu vya kitendo vilivyo wazi

```bash
omi action-item list --json --open
```

### 5. Weka kitembeo cha kitendo kama kilichokamilika

```bash
omi action-item complete --json a1b2c3d4
```

## API ya ndani ya Desktop

Okiwa Omi Desktop huonyesha API yake ya ndani, waagenti wanaweza kuuliza historia ya
skrini ya kifaa, muhtasari, SQL na kazi bila kutumia API ya wingu:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# or, for ephemeral sessions:
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

Kamilisha au futa kazi tu mtumiaji akiomba wazi:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` huandika picha ya skrini kwenye
diski na bado hutengeneza JSON kwenye stdout kwa ajili ya script. Kitambulisho cha
picha kawaida hutoka kwa `local search-screen` au SQL juu ya jedwali la `screenshots`.
Ikiwa Desktop hurudisha hiti la muundo kama `screenshot_pending`,
`screenshot_file_missing`, au `screenshot_chunk_corrupted`, hali ya JSON huhifadhi
visanduku `reason`, `hint`, na `screenshot_id` kwenye stderr ili waagenti waweze
kujaribu kitambulisho cha zamani au kuripoti kizuizi halisi. Thibitisha matokeo
yenye mafanikio kwa `file PATH` kabla ya kuyapitisha kwenye zana za vision.

## Mfano wa vitendo: Python agent loop

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

## Kushughulikia vikomo vya mzunguko

Kumbukumbu: 120/saa. Mazungumzo: 25/saa. Uundaji wa kundi: 15/saa.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Vidokezo

* Tumia `--profile <jina>` kama agenti yako inashughulikia akaunti nyingi za Omi. Kila
  wasifu lina kimemo chake cha kuingia na API base.
* Tumia `--api-base http://localhost:8080` kwa majaribio ya backend ya ndani.
* Tumia `OMI_LOCAL_API_URL` na `OMI_LOCAL_TOKEN` kupita kwenye mipangilio ya API
  ya Desktop ya wasifu kwa mara moja.
* Tumia `--verbose` kwa kurekebisha — hurekodi `METHOD path → status (Ns)` kwenye stderr
  bila kuathiri stdout, hivhi JSON hubaki sahihi.
* Kwa kupitisha maudhui kwenye mazungumzo, tumia `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
