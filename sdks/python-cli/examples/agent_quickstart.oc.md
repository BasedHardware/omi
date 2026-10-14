# omi-cli pels agents

> Guida practica pels harnesses guiats per LLM (Claude Code, Cursor, vòstres pròpris bots).

## Perqué la CLI es amiga pels agents

* **Contracte JSON estabil.** `--json` emet un document JSON valid a stdout e
  *sonque* un document JSON — sens messatges de progrès, sens spinners. Las errors
  van a stderr coma `{"error": "...", "detail": "..."}`.
* **Còdis de sortida estabils.** `0` plan / `1` utilizacion / `2` auth / `3` servidor /
  `4` limit de velocitat / `5` pas trobat. Los agents se pòdon ramificar sus aquò
  sens analisar las errors en lengatge natural.
* **Pas de prompts interactius dins los contexts headless.** Passatz `--yes` (o `-y`)
  als comandaments destructius; passatz `--api-key` o meteissètz `OMI_API_KEY` per
  sautar l'autentificacion interactiva.
* **Compòrtament de ressèrche perdonador.** `429` e `5xx` se tornan ensajar amb
  backoff abans de sortir.

## Auth (un còp, per l'òme)

L'utilizaire obten una clau dev API de l'aplicacion web Omi
(`https://app.omi.me` → Developer → API Keys) e o:

```bash
omi auth login                          # pegada interactiva; la clau demora pas dins l'istoric del shell
# o
export OMI_API_KEY=omi_dev_...          # efimèra, ideal per als contenidors
```

## Las cinc causas que los agents fan mai

### 1. Legir las memòrias

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Crear una memòria

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Legir las conversacions

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Legir los ponches d'accion dobèrts

```bash
omi action-item list --json --open
```

### 5. Marcar un ponch d'accion coma fach

```bash
omi action-item complete --json a1b2c3d4
```

## API locala de Desktop

Quand Omi Desktop expausa sa API locala, los agents pòdon interrogar l'istoric
d'ecran del dispositiu, los recaps, SQL e las prètzefachas sens utilizar l'API
dev del núvol:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# o, per las sessions efimèras:
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

Acabar o suprimir las prètzefachas sonque quand l'utilizaire o demanda clar:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` escriu la captura d'ecran sul
disc e imprimís enquèra JSON a stdout pels scripts. L'ID de captura ven de
`local search-screen` o SQL sus la taula `screenshots`. Se Desktop retorna una
error estructurada coma `screenshot_pending`, `screenshot_file_missing` o
`screenshot_chunk_corrupted`, lo mòde JSON consèrva los camps `reason`, `hint` e
`screenshot_id` a stderr perque los agents pòscan tornar ensajar un ID mai vièlh
o raportar lo blocatge exacte. Validatz las sortidas reüssidas amb `file PATH`
abans de las passar als espleches de vision.

## Exemple trabalhat: bocla d'agent en Python

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

## Gestion dels limits de velocitat

Memòrias: 120/ora. Conversacions: 25/ora. Creacions en lòt: 15/ora.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Conselhs

* Utilizatz `--profile <name>` se vòstre agent gerís mantuns comptes Omi. Cada
  perfil a sas pròprias credencials e basa API.
* Utilizatz `--api-base http://localhost:8080` pels tèsts backend locals.
* Utilizatz `OMI_LOCAL_API_URL` e `OMI_LOCAL_TOKEN` per remplaçar los paramètres
  de l'API locala Desktop del perfil per una execucion.
* Utilizatz `--verbose` per desbugar — enregistra `METHOD path → status (Ns)` a
  stderr sens afectar stdout, doncas lo mòde JSON demòra valid.
* Per pipear de contengut dins una conversacion, utilizatz `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
