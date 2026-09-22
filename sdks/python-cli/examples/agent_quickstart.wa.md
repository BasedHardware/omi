# omi-cli po les agents

> Gude pratike po les harnés moennés pa LLM (Claude Code, Cursor, vos bots a vos).

## Pocwè li CLI est boune po les agents

* **Coton JSON eståve.** `--json` evoye on documint JSON valåve sol stdout
  eyet *rén k'* on documint JSON — pont di messaedjes d' progrés, pont di
  spinners. Les arokes vont sol stderr come `{"error": "...", "detail": "..."}`.
* **Codes di rexhowe eståves.** `0` ok / `1` usage / `2` auth / `3` server /
  `4` rate limited / `5` not found. Les agents pôrèt prinde des decisions
  la-disse sins lére les arokes e lingaedje naturel.
* **Pont di dmandes interactives dins les conthètes headless.** Passez
  `--yes` (ou `-y`) ås comandes distrudjeus ; passez `--api-key` ou metoz
  `OMI_API_KEY` po passer li lôdjî interactive.
* **Ritriyes induldjantes.** `429` et `5xx` sont ritriyîs avou backoff divant
  d' esse mostrés.

## Auth (on seu côp, pa l' umain)

Li cis k' eploye prind ene clé API des diswalpeus del waibe app Omi
(`https://app.omi.me` → Developer → API Keys), pu fwait on di çes deus :

```bash
omi auth login                          # tapez di rawete ; li clé n' est nén dins l' istwere do shell
# ou
export OMI_API_KEY=omi_dev_...          # efimere, boune po les conteneus
```

## Les cénk sacwès ki les agents fwèt l' pus sovint

### 1. Lére les souvnances

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Fé ene souvnance

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Lére les coviernaedjes

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Lére les accions nén achevêyes

```bash
omi action-item list --json --open
```

### 5. Mårker ene accion come fwait

```bash
omi action-item complete --json a1b2c3d4
```

## API locåle Desktop

Cwand Omi Desktop mostere s' API locåle, les agents pôrèt dmander l' istwere
do waitroûle, les rcapéts, SQL et les bouyes sol mochene sins eployî l' API
des diswalpeus do nbule :

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# ou, po des sessions efimeres :
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

Fijhoz les bouyes come fwaites ou disfijhoz-les rén k' cwand l' eployeu l'
dmande clairmint :

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` scrijh li screneye sol
disc eyet evoye todi JSON sol stdout po les scrîts. L' ID del screneye vént
sovint di `local search-screen` ou d' ene dmande SQL sol tåve `screenshots`.
Si Desktop evoye ene aroke structurêye come `screenshot_pending`,
`screenshot_file_missing`, ou `screenshot_chunk_corrupted`, li môde JSON
garde les tchamps `reason`, `hint` et `screenshot_id` sol stderr po k' les
agents polèt ritreyî avou on vî ID ou rspondre l' aroke comint fåt.
Verifyîz les rexhowes ki ont moussî avou `file PATH` divant di les evoeyer
ås usteyes di vision.

## Egzeince ovré : boucle d' agent e Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Eploye li CLI omi e môde JSON ; evoye ene aroke si li code di rexhowe ni va nén."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # Li CLI evoye des arokes structurêyes sol stderr e môde JSON :
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Lére totes les accions nén achevêyes eyet mårker come fwaites celés di pus di 30 djoûs.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Kimint manaedjî les rate limits

Memories: 120/hr. Conversations: 25/hr. Batch creates: 15/hr.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # limite di debit
    err = json.loads(result.stderr)
    # err["detail"] ressembe a : "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Ascets

* Eployîz `--profile <no>` si vosse agent djouwe avou pus d' on conte Omi.
  Tchaeke profile a s' credince et s' API base a luy.
* Eployîz `--api-base http://localhost:8080` po essayer on backend locå.
* Eployîz `OMI_LOCAL_API_URL` et `OMI_LOCAL_TOKEN` po passiner les parametes
  del API Desktop do profile po on seu rolaedje.
* Eployîz `--verbose` po l' disrataedje — i scrijh `METHOD path → status (Ns)`
  sol stderr sins tchatchî stdout, dabôd li môde JSON dmère valåve.
* Po mete on contnou dins ene coviernaedje, eployîz `--text -` :
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
