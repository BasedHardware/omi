# omi-cli tî agent-wâ

> Mbëtï mbëti tî kua tî LLM-harness (Claude Code, Cursor, ngere ti mo mveni).

## Ngbanga tî so CLI ayeke nzoni tî agent-wâ

* **Ködörö tî JSON ayeke ngangu.** `--json` afä atënë tî JSON na stdout na
  *tënë tî JSON oko* — pëpe tî message tî lêkwa, pëpe spinner. Faute ake
  na stderr tongana `{"error": "...", "detail": "..."}`.
* **Code tî sigirî ayeke ngangu.** `0` nzoni / `1` usara / `2` auth / `3` server /
  `4` limite tî ngangu / `5` a-wara pëpe. Agent-wâ alingbi ti fa na ndö ni
  pëpe ti hunda na faute na lêkua tî zo.
* **Pëpe prompt interactive na context headless.** Särä `--yes` (wala `-y`)
  na commande tî buba; särä `--api-key` wala `OMI_API_KEY` ti tüngbeni login interactive.
* **Réessayer tî tanga.** `429` na `5xx` ayeke réessayer na backoff avant
  ti sigirî.

## Auth (âmâ oko, na zo)

Zo ayeke wara dev API key na web app tî Omi
(`https://app.omi.me` → Developer → API Keys) na nga:

```bash
omi auth login                          # paste interactive; key ayeke na histoire tî shell pëpe
# wala
export OMI_API_KEY=omi_dev_...          # na ngûngû, nzoni tî conteneur
```

## Chose ôsô so agent-wâ ayeke këre mingi

### 1. Dö mêmory

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Sära mêmory oko

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Dö tene

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Dö action-item so ayeke zi

```bash
omi action-item list --json --open
```

### 5. Fä action-item oko tongana ayeke huni

```bash
omi action-item complete --json a1b2c3d4
```

## API local tî Desktop

Tongana Omi Desktop afä API local tî lo, agent-wâ alingbi ti hunda na ndö
histoire tî écran, récap, SQL, na tâche na ndö ti machine pëpe ti usara
API dev tî cloud:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# wala, tî session na ngûngû:
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

Huni wala fâ tâche tongana zo ahunda na ngangu:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` asüsü screenshot na disque
na ayeke sûrû JSON na stdout tî script. ID tî screenshot ayeke na `local
search-screen` wala SQL na ndö ti table `screenshots`. Tongana Desktop afä
faute structuré tongana `screenshot_pending`, `screenshot_file_missing`, wala
`screenshot_chunk_corrupted`, mode JSON ayeke wara `reason`, `hint`, na
`screenshot_id` na stderr tî agent-wâ alingbi ti réessayer na ID tî mbeni wala
ti fä blocage précis. Vérifie résultat nzoni na `file PATH` avant ti särä na
outil vision.

## Exemple travaillé: boucle tî agent Python

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

## Gère limite tî ngangu

Mêmory: 120/h. Tene: 25/h. Sära batch: 15/h.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Conseil-wâ

* Usara `--profile <name>` tongana agent tî mo ayeke gère account tî Omi mingi.
  Profile oko na code tî lo mveni na base tî API.
* Usara `--api-base http://localhost:8080` tî test backend local.
* Usara `OMI_LOCAL_API_URL` na `OMI_LOCAL_TOKEN` ti passé sur setting tî
  API local tî profile tî run oko.
* Usara `--verbose` tî debug — ayeke log `METHOD path → status (Ns)` na stderr
  pëpe ti toucher stdout, tongana mode JSON ayeke valid.
* Tî pipe contenu na tene, usara `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
