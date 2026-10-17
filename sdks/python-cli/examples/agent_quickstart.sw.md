# omi-cli kwa mawakala

> Mwongozo wa vitendo kwa harnesses zinazoendeshwa na LLM (Claude Code, Cursor, bot zako).

## Kwa nini CLI ni rafiki kwa mawakala

* **Mkataba thabiti wa JSON.** `--json` huandika hati halali ya JSON kwenda stdout na *tu* JSON — hakuna ujumbe wa maendeleo wala spinners. Makosa huenda stderr kama `{"error": "...", "detail": "..."}`.
* **Misimbo thabiti ya kutoka.** `0` ok / `1` matumizi / `2` auth / `3` seva / `4` rate limited / `5` haipatikani. Mawakala wanaweza kufanya branch bila kupinga makosa ya lugha asilia.
* **Hakuna maswali ya kuingiliana katika mazingira headless.** Pitisha `--yes` (au `-y`) kwa amri za uharibifu; pitisha `--api-key` au weka `OMI_API_KEY` kuruka kuingia kwa kuingiliana.
* **Tabia ya retry ya msamaha.** `429` na `5xx` hujaribiwa tena kwa backoff kabla ya kutokea.

## Uthibitishaji (mara moja, kwa binadamu)

Mtumiaji hupata dev API key kutoka programu ya wavuti ya Omi
(`https://app.omi.me` → Developer → API Keys) kisha:

```bash
omi auth login                          # bandika kwa kuingiliana; key haiko kwenye historia ya shell
# # au
export OMI_API_KEY=omi_dev_...          # ya muda mfupi, rafiki wa kontena
```

## Mambo matano ambayo mawakala hufanya zaidi

### 1. Kusoma memories

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Kuunda memory

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Kusoma conversations

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Kusoma action items zilizo wazi

```bash
omi action-item list --json --open
```

### 5. Kuweka action item kama imekamilika

```bash
omi action-item complete --json a1b2c3d4
```

## API ya Desktop ya ndani

Omi Desktop inapofungua API yake ya ndani, mawakala wanaweza kuuliza
historia ya skrini kwenye kifaa, recaps, SQL na tasks bila kutumia dev API ya wingu:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# # au, kwa vikao vya muda mfupi:
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

Kamilisha au futa tasks tu wakati mtumiaji anaomba wazi:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` huandika screenshot kwenye
diski na bado kuchapisha JSON kwenda stdout kwa script. ID ya screenshot kwa
kawaida hutoka `local search-screen` au SQL juu ya jedwali `screenshots`. Ikiwa
Desktop inarudisha kosa lililopangwa kama `screenshot_pending`,
`screenshot_file_missing` au `screenshot_chunk_corrupted`, hali ya JSON huhifadhi
`reason`, `hint` na `screenshot_id` kwenye stderr ili wakala aweze kujaribu ID ya
zamani au kuripoti kizuizi kamili. Thibitisha outputs zilizofaulu kwa `file PATH`
kabla ya kuzipeleka kwa zana za vision.

## Mfano uliotendwa: kitanzi cha wakala wa Python

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

# Soma action items zote zilizo wazi na uweke kukamilika zile zaidi ya siku 30.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Kushughulikia rate limits

Memories: 120/saa. Conversations: 25/saa. Uundaji wa batch: 15/saa.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] inaonekana kama: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Vidokezo

* Tumia `--profile <name>` ikiwa wakala wako unashughulikia akaunti nyingi za
  Omi. Kila profaili ina credential na API base yake.
* Tumia `--api-base http://localhost:8080` kwa kujaribu backend ya ndani.
* Tumia `OMI_LOCAL_API_URL` na `OMI_LOCAL_TOKEN` kubadilisha mipangilio ya
  Desktop API ya profaili kwa moja ya kuendesha.
* Tumia `--verbose` kwa debugging — huandika `METHOD path → status (Ns)`
  kwenda stderr bila kuathiri stdout, hivyo hali ya JSON hubaki halali.
* Kupipa maudhui kwenye conversation, tumia `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
