# omi-cli kwa ajenti

> Mwongozo wa vitendo kwa mifumo inayoendeshwa na LLM (Claude Code, Cursor, na boti zako).

## Kwa nini CLI inafaa kwa ajenti

* **Mkataba thabiti wa JSON.** `--json` hutoa waraka halali wa JSON kwenye stdout na waraka wa JSON *pekee* — bila jumbe za maendeleo wala viashiria vinavyozunguka. Hitilafu huenda kwenye stderr kama `{"error": "...", "detail": "..."}`.
* **Misimbo thabiti ya kutoka.** `0` sawa / `1` matumizi yasiyo sahihi / `2` uthibitishaji / `3` seva / `4` kiwango kimezidi / `5` haikupatikana. Ajenti wanaweza kugawanya mantiki kulingana na misimbo hii bila kuchanganua makosa ya lugha asilia.
* **Hakuna maombi shirikishi katika mazingira yasiyo na skrini (headless).** Pitisha `--yes` (au `-y`) kwa amri zinazofuta au kubadilisha data; pitisha `--api-key` au weka `OMI_API_KEY` ili kuruka kuingia kwa maingiliano.
* **Mwenendo mvumilivu wa kujaribu tena.** Makosa ya `429` na `5xx` hujaribiwa tena kiotomatiki kabla ya kuonyeshwa.

## Uthibitishaji (mara moja, na binadamu)

Mtumiaji anapata ufunguo wa API wa msanidi kutoka kwa programu ya wavuti ya Omi (`https://app.omi.me` → Developer → API Keys) na kuchagua mojawapo:

```bash
omi auth login                          # kubandika shirikishi; ufunguo hauhifadhiwi kwenye historia ya ganda
# au
export OMI_API_KEY=omi_dev_...          # ya muda, inafaa kwa makontena
```

## Mambo matano ambayo ajenti hufanya mara nyingi zaidi

### 1. Soma kumbukumbu

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Unda kumbukumbu

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Soma mazungumzo

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Soma majukumu yaliyo wazi

```bash
omi action-item list --json --open
```

### 5. Weka alama ya jukumu limekamilika

```bash
omi action-item complete --json a1b2c3d4
```

## API ya Ndani ya Kompyuta ya Mezani (Desktop)

Wakati Omi Desktop inatoa API yake ya ndani, ajenti wanaweza kuuliza historia ya skrini kwenye kifaa, mihtasari, SQL, na majukumu bila kutumia dev API ya wingu:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# au, kwa vipindi vya muda:
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

`omi local screenshot SCREENSHOT_ID --output PATH` huandika picha ya skrini kwenye diski na bado huchapisha JSON kwenye stdout kwa ajili ya hati. Kitambulisho cha picha mara nyingi hutoka kwa `local search-screen` au hoja ya SQL kwenye jedwali la `screenshots`. Ikiwa Desktop itarejesha hitilafu iliyopangwa kama vile `screenshot_pending`, `screenshot_file_missing`, au `screenshot_chunk_corrupted`, hali ya JSON huhifadhi sehemu za `reason`, `hint`, na `screenshot_id` kwenye stderr ili ajenti waweze kujaribu tena kitambulisho cha zamani au kuripoti kizuizi halisi. Thibitisha faili zilizofanikiwa kwa `file PATH` kabla ya kuzipeleka kwa zana za kuona.

## Mfano wa utendaji: Mzunguko wa ajenti wa Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Hutekeleza omi CLI katika hali ya JSON, ikitoa hitilafu kwa misimbo isiyofanikiwa."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI huchapisha hitilafu zilizopangwa kwenye stderr katika hali ya JSON:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi ilitoka na msimbo {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Soma majukumu yote yaliyo wazi na ukamilishe yale yaliyo zaidi ya siku 30.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Kushughulikia mipaka ya kasi

Kumbukumbu: 120/saa. Mazungumzo: 25/saa. Uundaji wa pamoja: 15/saa.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # kiwango kimezidi
    err = json.loads(result.stderr)
    # err["detail"] inaonekana kama: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Vidokezo

* Tumia `--profile <jina>` ikiwa ajenti wako anasimamia akaunti nyingi za Omi. Kila wasifu una kitambulisho chake na msingi wa API.
* Tumia `--api-base http://localhost:8080` kwa majaribio ya mfumo wa ndani.
* Tumia `OMI_LOCAL_API_URL` na `OMI_LOCAL_TOKEN` kubatilisha mipangilio ya ndani ya API ya Desktop kwa utekelezaji mmoja.
* Tumia `--verbose` kwa utatuzi wa hitilafu — hurekodi `METHOD path → status (Ns)` kwenye stderr bila kuathiri stdout, ili hali ya JSON ibaki kuwa halali.
* Kuingiza maudhui kwenye mazungumzo kupitia bomba (pipe), tumia `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
