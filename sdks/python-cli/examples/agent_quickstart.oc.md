# omi-cli pels agents

> Guida practica per las aisinas guidadas per LLM (Claude Code, Cursor, vòstres pròpris robòts).

## Perqué la CLI es amicala pels agents

* **Contracte JSON estable.** `--json` emetís un document JSON valid sus stdout
  — *sonque* un document JSON — pas de messatges de progrès, pas de spinner.
  Las errors van sus stderr coma `{"error": "...", "detail": "..."}`.
* **Còdes de sortida estables.** `0` òc / `1` usatge / `2` autenticacion / `3`
  servidor / `4` limitat per debit / `5` pas trobat. Los agents pòdon ramificar
  sus aqueles sens analisar d'errors en lenga naturala.
* **Pas de questions interactivas dins de contèxtes headless.** Passatz `--yes`
  (o `-y`) a las comandas destructivas; passatz `--api-key` o definissètz
  `OMI_API_KEY` per passar la connexion interactiva.
* **Comportament de reensag tolerant.** `429` e `5xx` son reensajats amb un
  repli d'espera abans d'aparéisser.

## Autenticacion (un còp, per l'uman)

L'utilizaire obten una clau API dev dempuèi l'aplicacion web Omi
(`https://app.omi.me` → Developer → API Keys) e puèi:

```bash
omi auth login                          # pegament interactiu; la clau passa pas dins l'istoric del shell
# o
export OMI_API_KEY=omi_dev_...          # efemèr, adaptat als contenedors
```

## Las cinc causas que los agents fan lo mai sovent

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

### 4. Legir los elements d'accion dobèrts

```bash
omi action-item list --json --open
```

### 5. Marcar un element d'accion coma facit

```bash
omi action-item complete --json a1b2c3d4
```

## API Desktop Local

Quand Omi Desktop expausa son API local, los agents pòdon interrogar l'istoric
d'ecran sus l'aparelh, los recapitulatius, SQL e las tascas sens utilizar l'API
dev del núvol:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# o, per de sessions efemèras:
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

Acabatz o escafatz las tascas solament quand l'utilizaire o demanda clarament:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` escriu la captura d'ecran sul
disc e imprimís totjorn del JSON sus stdout pels escripts. L'ID de la captura
ven normalament de `local search-screen` o de SQL sus la taula `screenshots`. Se
Desktop torna una error estructurada coma `screenshot_pending`,
`screenshot_file_missing`, o `screenshot_chunk_corrupted`, lo mòde JSON
preserva los camps `reason`, `hint`, e `screenshot_id` sus stderr perque los
agents pòscan reensajar amb un ID mai ancian o senhalar lo blocatge exacte.
Validatz las sortidas capitadas amb `file PATH` abans de las passar a las
aisinas de vision.

## Exemple trabalhat: bucle d'agent Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Invocar la CLI omi en mòde JSON, levant una excepcion sus de còdes de sortida pas capitats."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # La CLI imprimís d'errors estructuradas sus stderr en mòde JSON:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Legir totes los elements d'accion dobèrts e marcar coma facits los que son mai vièlhs de 30 jorns.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Gestion de las limitas de debit

Memòrias: 120/h. Conversacions: 25/h. Creacions en lot: 15/h.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # limitat per debit
    err = json.loads(result.stderr)
    # err["detail"] sembla a: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Astúcias

* Utilizatz `--profile <name>` se vòstre agent gerís mantun compte Omi. Cada
  perfil a sas pròprias credencialas e sa pròpria basa API.
* Utilizatz `--api-base http://localhost:8080` per de tèsts amb un backend local.
* Utilizatz `OMI_LOCAL_API_URL` e `OMI_LOCAL_TOKEN` per subrecargar los
  paramètres API Desktop del perfil per una execucion.
* Utilizatz `--verbose` pel desbogatge — enregistra `METHOD path → status (Ns)` sus stderr
  sens afectar stdout, donc lo mòde JSON demòra valid.
* Per injectar de contengut dins una conversacion, utilizatz `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
