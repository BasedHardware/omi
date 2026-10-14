# omi-cli pai agjents

> Guida pratiche pai harness guidâts di LLM (Claude Code, Cursor, i tiei stes bots).

## Parcè la CLI e je amighe ai agjents

* **Contrat JSON stabil.** `--json` al emit un document JSON valit su stdout e
  *dome* un document JSON — nissun messaç di progrès, nissun spinner. I erôrs
  a van su stderr come `{"error": "...", "detail": "..."}`.
* **Codis di jessude stabilis.** `0` ok / `1` usadure / `2` auth / `3` server /
  `4` limit di velocitât / `5` no cjatât. I agjents a puedin fâ branch su chestis
  cence analizâ erôrs in lenghe natural.
* **Nissun prompt interatîf in contest headless.** Passe `--yes` (o `-y`) ai
  comants distrutîfs; passe `--api-key` o imposte `OMI_API_KEY` par saltâ il
  login interatîf.
* **Compuartament di retry che al perdone.** `429` e `5xx` a vegnin ripetûts
  cun backoff prime di jessî.

## Auth (une volte, de persone)

Il utent al cjape une clâf dev API de web app Omi
(`https://app.omi.me` → Developer → API Keys) e o:

```bash
omi auth login                          # incolâ interatîf; la clâf no je te storie de shell
# o
export OMI_API_KEY=omi_dev_...          # efimere, ideâl pai conteneurs
```

## Lis cinc cjesis che i agjents a fasin di plui

### 1. Lezi lis memoriis

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Creâ une memorie

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Lezi lis conversazions

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Lezi i ponts di azion vierçs

```bash
omi action-item list --json --open
```

### 5. Segnâ un pont di azion come fat

```bash
omi action-item complete --json a1b2c3d4
```

## API locâl di Desktop

Cuand Omi Desktop al espon la sô API locâl, i agjents a puedin interogâ la
storie dal scherm sul dispositîf, i recap, SQL, e lis tascs cence doprâ la API
dev dal cloud:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# o, pai sessions efimeris:
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

Complete o elimine lis tascs dome cuand il utent al domande claramentri:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` al scrive il screenshot sul
disc e al stampije ancjemò JSON su stdout pai scripts. L'ID dal screenshot al
rive di solit di `local search-screen` o SQL su la tabele `screenshots`. Se
Desktop al torne un erôr struturât come `screenshot_pending`,
`screenshot_file_missing`, o `screenshot_chunk_corrupted`, il mût JSON al
preserve i cjamps `reason`, `hint`, e `screenshot_id` su stderr in mût che i
agjents a puedin tornâ a provâ un ID plui vecj o segnalâ il bloc precîs.
Valide lis jessudis riussidis cun `file PATH` prime di passâlis ai struments
di vision.

## Esempli lavurât: loop di agjent in Python

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

## Gjestîs di limit di velocitât

Memoriis: 120/ore. Conversazions: 25/ore. Creazions in batch: 15/ore.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Consii

* Doprê `--profile <name>` se il to agjent al gjestìs plui accounts Omi. Ogni
  profîl al à lis sôs credenzâls e la sô base API.
* Doprê `--api-base http://localhost:8080` pai tests backend locâi.
* Doprê `OMI_LOCAL_API_URL` e `OMI_LOCAL_TOKEN` par sostituî lis impostazions
  de API locâl di Desktop dal profîl par une esecuzion.
* Doprê `--verbose` pal debug — al registre `METHOD path → status (Ns)` su stderr
  cence tocjâ stdout, cussì il mût JSON al reste valit.
* Par fâ pipe di contignût intune conversazion, doprê `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
