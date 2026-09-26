# omi-cli pi l'aggenti

> Guida pràtica pi li harness guidati di LLM (Claude Code, Cursor, li tò bot).

## Pirchì la CLI è amichevuli pi l'aggenti

* **Cuntrattu JSON stàbbili.** `--json` manna un ducumentu JSON vàlidu a stdout
  e *sulu* un ducumentu JSON — nuddu missaggiu di prugressu, nuddu spinner. Li
  erruri vàninu a stderr comu `{"error": "...", "detail": "..."}`.
* **Còdici di nisciuta stàbbili.** `0` bonu / `1` usu / `2` autinticazzioni /
  `3` server / `4` limitatu dû ritmu / `5` nun truvatu. L'aggenti pònu
  ramificari supra sti còdici senza analizzari erruri ntâ lingua naturali.
* **Nuddi dumanni intirattivi nta cuntesti headless.** Passa `--yes` (o `-y`)
  a li cumanni distruttivi; passa `--api-key` o mpusta `OMI_API_KEY` pi
  sustari lu login intirattivu.
* **Cumportamentu di riprova tolleranti.** `429` e `5xx` vèninu riprivati cu
  backoff prima di cumpariri.

## Autinticazzioni (na vota, di l'òmunu)

L'utenti si pigghia na chiavi API dev di l'app web Omi
(`https://app.omi.me` → Developer → API Keys) e poi:

```bash
omi auth login                          # ncuddamentu intirattivu; la chiavi nun trasi ntâ storia dû shell
# o
export OMI_API_KEY=omi_dev_...          # efimeru, còmutu pi li cuntinituri
```

## Li cincu cosi chi l'aggenti fàninu cchiù ssai

### 1. Lèggiri li memori

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Criari na memoria

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Lèggiri li cunversazzioni

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Lèggiri l'elimenti d'azzioni graputi

```bash
omi action-item list --json --open
```

### 5. Signari n'elimentu d'azzioni comu fattu

```bash
omi action-item complete --json a1b2c3d4
```

## API Desktop Lucali

Quannu Omi Desktop ammustra la sò API lucali, l'aggenti pònu addimannari la
storia di schermu ntô dispusitivu, li riassunti, SQL e li task senza usari
l'API dev dû cloud:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# o, pi sissioni efimeri:
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

Cumpleta o cancella task sulu quannu l'utenti lu addimanna chiaramenti:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` scrivi la cattura di
schermu ntô discu e stampa sempri JSON a stdout pi li script. L'ID dâ cattura
veni di sòlitu di `local search-screen` o di SQL supra la taula `screenshots`.
Si Desktop arritorna un fallimentu strutturatu comu `screenshot_pending`,
`screenshot_file_missing` o `screenshot_chunk_corrupted`, lu modu JSON
priserva li campi `reason`, `hint` e `screenshot_id` a stderr accussì
l'aggenti pònu riprivari cu n'ID cchiù vecchiu o signalari lu bloccu esattu.
Valida li nisciuti arrinisciuti cu `file PATH` prima di passàrili a li
strumenti di visioni.

## Asempiu cumpletu: cìculu di aggenti n Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Invoca la CLI omi n modu JSON, arzannu n còdici di nisciuta nun arrinisciuti."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # La CLI stampa erruri strutturati a stderr n modu JSON:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Leggi tutti l'elimenti d'azzioni graputi e signa comu fatti chiddi chi hannu cchiù di 30 jorna.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Gistioni dî limiti di ritmu

Memori: 120/ura. Cunversazzioni: 25/ura. Criazzioni n lotu: 15/ura.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # limitatu dû ritmu
    err = json.loads(result.stderr)
    # err["detail"] pari comu: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Cunsigghi

* Usa `--profile <name>` si lu tò aggenti gistisci diversi cunti Omi. Ogni
  prufilu havi la sò cridentiali e la sò basi API.
* Usa `--api-base http://localhost:8080` p'aspirimentari lu backend lucali.
* Usa `OMI_LOCAL_API_URL` e `OMI_LOCAL_TOKEN` pi suprascriviri li mpustazioni
  di l'API Desktop Lucali dû prufilu pi na esecuzzioni.
* Usa `--verbose` pû debug — riggistra `METHOD path → status (Ns)` a stderr
  senza tuccari stdout, accussì lu modu JSON resta vàlidu.
* Pi mannari cuntinutu nta na cunversazzioni, usa `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
