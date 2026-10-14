# omi-cli mō ngā kaihanga

> Aratohu whaihua mō ngā harness e arahina ana e LLM (Claude Code, Cursor, āu ake bots).

## He aha te CLI e pai ai ki ngā kaihanga

* **Kirimana JSON pumau.** `--json` ka puta he tuhinga JSON tika ki te stdout me
  *anake* he tuhinga JSON — kāore he karere whanake, kāore he spinner. Ngā hē ka
  haere ki te stderr hei `{"error": "...", "detail": "..."}`.
* **Waehere putanga pumau.** `0` pai / `1` whakamahi / `2` auth / `3` server /
  `4` aukatinga tere / `5` kāore i kitea. Ka taea e ngā kaihanga te peka ki ēnei
  me te kore e tātari ngā hē reo tūturu.
* **Kāore he prompt interactive i ngā horopaki headless.** Tukua `--yes` (a `-y` rānei)
  ki ngā whakahau whakakino; tukua `--api-key` a whakatauhia rānei `OMI_API_KEY` hei
  tāpae i te takiuru interactive.
* **Whanonga retry whakaae.** `429` me `5xx` ka retry i te backoff i mua i te putanga.

## Auth (tahi wā, nā te tangata)

Ka mau te kaiwhakamahi i tētahi kī dev API mai i te taupānga tukutuku Omi
(`https://app.omi.me` → Developer → API Keys) me:

```bash
omi auth login                          # tāpihia interactive; te kī kāore e noho ki te hītori o te shell
# a
export OMI_API_KEY=omi_dev_...          # pōnehu, pai mō ngā kono
```

## Ngā mea e rima ka mahia nuitia e ngā kaihanga

### 1. Pānuihia ngā mahara

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Waihangahia tētahi mahara

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Pānuihia ngā kōrerorero

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Pānuihia ngā tīmatā mahi tuwhera

```bash
omi action-item list --json --open
```

### 5. Tohu i tētahi tīmatā mahi kua oti

```bash
omi action-item complete --json a1b2c3d4
```

## API takiwā o Desktop

Ina whakahuatia e Omi Desktop tōna API takiwā, ka taea e ngā kaihanga te uiui
i te hītori mata o te pūrere, ngā whakarāpopototanga, SQL, me ngā mahi me te
kore e whakamahi i te API dev i te kapua:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# a, mō ngā hui pōnehu:
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

Whakamutua a mukuha rānei ngā mahi ina tono mārama te kaiwhakamahi:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` ka tuhi i te screenshot ki te
kopae me te tonu e tā i te JSON ki te stdout mō ngā kōnae. Ko te ID screenshot ka
puta i te nuinga mai `local search-screen` a SQL rānei ki te tēpū `screenshots`.
Ki te whakahokia e Desktop tētahi hē takitahi pērā i `screenshot_pending`,
`screenshot_file_missing`, a `screenshot_chunk_corrupted` rānei, ka pupuri te
ahua JSON i ngā whāinga `reason`, `hint`, me `screenshot_id` ki te stderr kia
taea ai e ngā kaihanga te retry ki tētahi ID tawhito ake a te pūrongo rānei i te
parakainga tino. Whakatūturu i ngā putanga pai mā `file PATH` i mua i te tukunga
ki ngā taputapu tirohanga.

## Tauira whaihua: poro kaihanga Python

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

## Whakahaere i ngā aukatinga tere

Mahara: 120/h. Kōrerorero: 25/h. Waihanga pēke: 15/h.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Ngā tohutohu

* Whakamahia `--profile <name>` mēnā tō kaihanga e whakahaere ana i ngā kaute Omi
  maha. Ia kōtaha he credential me te tūāpapa API ōna ake.
* Whakamahia `--api-base http://localhost:8080` mō ngā whakamātautau backend takiwā.
* Whakamahia `OMI_LOCAL_API_URL` me `OMI_LOCAL_TOKEN` hei whakakapi i ngā tautuhinga
  API takiwā o Desktop o te kōtaha mō tētahi whakahaerenga.
* Whakamahia `--verbose` mō te patuiro — ka tā `METHOD path → status (Ns)` ki te
  stderr me te kore e pa ki te stdout, nō reira ka noho tika te ahua JSON.
* Hei pipe i te ihirangi ki tētahi kōrerorero, whakamahia `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
