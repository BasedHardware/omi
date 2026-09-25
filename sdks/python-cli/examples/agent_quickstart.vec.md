# omi-cli par i agenti

> Guida pràtega par i arnesi guidai da LLM (Claude Code, Cursor, i tò bot).

## Parché la CLI la ze amiga par i agenti

* **Contrato JSON stàbile.** `--json` el manda un documento JSON vàlido su
  stdout e *sol* un documento JSON — nisun mesajo de progreso, nisun spinner.
  I erori i va su stderr come `{"error": "...", "detail": "..."}`.
* **Còdeghi de uscita stàbili.** `0` bon / `1` doparasion / `2` autenticasion /
  `3` server / `4` limità dal ritmo / `5` no catà. I agenti i pol ramifegar su
  sti còdeghi sensa analizar erori in lengua natural.
* **Nisuna dimanda interativa in contesti headless.** Passa `--yes` (o `-y`) ai
  comandi distrutivi; passa `--api-key` o inposta `OMI_API_KEY` par saltar el
  login interativo.
* **Conportamento de retentivo tolerante.** `429` e `5xx` i vien retentai co
  backoff prima de saltar fora.

## Autenticasion (na volta, da l'omo)

L'utente el ciapa na ciave API dev da l'aplicasion web Omi
(`https://app.omi.me` → Developer → API Keys) e dopo:

```bash
omi auth login                          # incolamento interativo; la ciave no entra inte la cronologia de la shell
# o
export OMI_API_KEY=omi_dev_...          # efimaro, bon par i contenidori
```

## Le sinque cose che i agenti i fa de pi

### 1. Lexer le memorie

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Crear na memoria

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Lexer le conversasion

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Lexer i elementi de asion verti

```bash
omi action-item list --json --open
```

### 5. Marcar un elemento de asion come fato

```bash
omi action-item complete --json a1b2c3d4
```

## API Desktop Locale

Co Omi Desktop el verze la so API locale, i agenti i pol dimandar la storia de
schermo sul dispozitivo, i resunti, SQL e i task sensa doparar la API dev del
cloud:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# o, par sesion efimare:
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

Completa o scançela i task sol co che l'utente el dimanda in ciaro:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` el scrive la catura de
schermo sul disco e el stampa senpre JSON su stdout par i script. L'ID de la
catura de solito el vien da `local search-screen` o da SQL su la tabela
`screenshots`. Se Desktop el torna un falimento struturà come
`screenshot_pending`, `screenshot_file_missing` o `screenshot_chunk_corrupted`,
el modo JSON el conserva i campi `reason`, `hint` e `screenshot_id` su stderr
cussì che i agenti i pol riprovar co un ID pi vecio o segnalar el bloco esato.
Verifega i risultai riusii con `file PATH` prima de pasarli ai strumenti de
vision.

## Ezenpio conpleto: siclo de agente in Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """El invoca la CLI omi in modo JSON, lanzando sui còdeghi de uscita no riusii."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # La CLI la stampa erori struturai su stderr in modo JSON:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Lexi tuti i elementi de asion verti e marca come fati quei pi veci de 30 dì.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Gestion dei limiti de ritmo

Memorie: 120/ora. Conversasion: 25/ora. Creasion in bloco: 15/ora.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # limità dal ritmo
    err = json.loads(result.stderr)
    # err["detail"] el someja a: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Conseji

* Dopara `--profile <name>` se el tò agente el gestise pi conti Omi. Ogni
  profilo el ga la so credensial e base API.
* Dopara `--api-base http://localhost:8080` par provar el backend locale.
* Dopara `OMI_LOCAL_API_URL` e `OMI_LOCAL_TOKEN` par sorascriver le inpostasion
  de la API Desktop Locale del profilo par na esecusion.
* Dopara `--verbose` par el debug — el registra `METHOD path → status (Ns)` su
  stderr sensa tocar stdout, cussì el modo JSON el resta vàlido.
* Par mandar contegnuo drento na conversasion, dopara `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
