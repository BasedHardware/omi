# omi-cli per a agents

> Guia pràctica per a entorns basats en LLM (Claude Code, Cursor, els vostres propis bots).

## Per què la CLI és adequada per a agents

* **Contracte JSON estable.** `--json` emet un document JSON vàlid a stdout i
  *només* un document JSON — sense missatges de progrés ni indicadors de càrrega (spinners). Els errors es dirigeixen
  a stderr com a `{"error": "...", "detail": "..."}`.
* **Codis de sortida estables.** `0` correcte / `1` ús incorrecte / `2` autenticació /
  `3` servidor / `4` límit de peticions / `5` no trobat. Els agents poden ramificar basant-se en aquests codis
  sense necessitat d'analitzar errors en llenguatge natural.
* **Sense sol·licituds interactives en entorns headless.** Passeu `--yes` (o `-y`) a les
  ordres destructives; passeu `--api-key` o definiu `OMI_API_KEY` per ometre
  l'inici de sessió interactiu.
* **Comportament de reintent tolerant.** Els errors `429` i `5xx` es reintenten amb retrocés (backoff)
  abans de mostrar-se.

## Autenticació (un sol cop, per la persona)

L'usuari obté una clau API de desenvolupador des de l'aplicació web d'Omi
(`https://app.omi.me` → Developer → API Keys) i tria una d'aquestes opcions:

```bash
omi auth login                          # enganxament interactiu; la clau no queda a l'historial del shell
# o bé
export OMI_API_KEY=omi_dev_...          # efímer, ideal per a contenidors
```

## Les cinc accions que els agents fan més sovint

### 1. Llegir records

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Crear un record

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Llegir converses

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Llegir elements d'acció pendents

```bash
omi action-item list --json --open
```

### 5. Marcar un element d'acció com a completat

```bash
omi action-item complete --json a1b2c3d4
```

## API local de Desktop

Quan Omi Desktop exposa la seva API local, els agents poden consultar l'historial
de pantalla al dispositiu, resums, SQL i tasques sense utilitzar l'API de desenvolupador al núvol:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# o bé, per a sessions efímeres:
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

Només completeu o suprimiu tasques quan l'usuari ho demani explícitament:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` escriu la captura de pantalla al
disc i continua imprimint JSON a stdout per als scripts. L'identificador de captura prové normalment
de `local search-screen` o d'una consulta SQL sobre la taula `screenshots`. Si Desktop
retorna una fallada estructurada com ara `screenshot_pending`, `screenshot_file_missing`
o `screenshot_chunk_corrupted`, el mode JSON conserva els camps `reason`, `hint` i
`screenshot_id` a stderr perquè els agents puguin reintentar amb un ID més antic o informar del
bloqueig exacte. Valideu les sortides correctes amb `file PATH` abans de passar-les
a eines de visió.

## Exemple pràctic: bucle d'agent en Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Invoca la CLI d'omi en mode JSON, generant una excepció en codis de sortida diferents de zero."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # La CLI imprimeix errors estructurats a stderr en mode JSON:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi ha sortit amb el codi {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Llegir tots els elements d'acció oberts i marcar com a completats els que tinguin més de 30 dies.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Gestió dels límits de velocitat (rate limits)

Records: 120/h. Converses: 25/h. Creacions en lot: 15/h.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # límit de peticions superat
    err = json.loads(result.stderr)
    # err["detail"] té el format: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Consells útils

* Utilitzeu `--profile <nom>` si el vostre agent gestiona múltiples comptes d'Omi. Cada
  perfil té les seves pròpies credencials i URL base d'API.
* Utilitzeu `--api-base http://localhost:8080` per a proves locals de backend.
* Utilitzeu `OMI_LOCAL_API_URL` i `OMI_LOCAL_TOKEN` per substituir la configuració de
  l'API local de Desktop d'un perfil per a una sola execució.
* Utilitzeu `--verbose` per a la depuració — registra `METHOD path → status (Ns)` a stderr
  sense afectar stdout, de manera que el mode JSON es manté vàlid.
* Per canalitzar (pipe) contingut cap a una conversa, utilitzeu `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
