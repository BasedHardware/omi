# omi-cli pe ll'agiente

> Guida pràteca pe li harness guidate da LLM (Claude Code, Cursor, 'e bot tuje).

## Pecché 'a CLI è amichevole pe ll'agiente

* **Cuntratto JSON stabile.** `--json` manna nu documento JSON valido ncoppa
  stdout e *sulo* nu documento JSON — nisciuna mangiata 'e messaggi, nisciuno
  spinner. 'E errore vanno ncoppa stderr comm'a `{"error": "...", "detail": "..."}`.
* **Codece 'e nisciuta stabile.** `0` buono / `1` uso / `2` autenticazzione /
  `3` server / `4` limitato 'o ritmo / `5` nun truvato. Ll'agiente ponno
  ramificà ncoppa chisti codece senza analizzà errore 'n lengua naturale.
* **Nisciune dumande interattive dint' 'e cunteste headless.** Passa `--yes` (o
  `-y`) 'e cumande distruttive; passa `--api-key` o mpòsta `OMI_API_KEY` pe
  saltà 'o login interattivo.
* **Cumportamento 'e riprova tollerante.** `429` e `5xx` vènono riprovate cu
  backoff primma 'e se fà vedè.

## Autenticazzione (na vota, pe ll'ommo)

L'utente se piglia na chiave API dev 'a ll'app web Omi
(`https://app.omi.me` → Developer → API Keys) e pò:

```bash
omi auth login                          # ncollo interattivo; 'a chiave nun trase dint' 'a storia d' 'o shell
# o
export OMI_API_KEY=omi_dev_...          # efimero, buono pe li cuntinitore
```

## 'E cinche ccose ca ll'agiente fanno 'e cchiù

### 1. Leggere 'e memorie

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Crià na memoria

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Leggere 'e cunversazzione

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Leggere ll'elemente 'e azzione aperte

```bash
omi action-item list --json --open
```

### 5. Marcà n'elemento 'e azzione comme fatto

```bash
omi action-item complete --json a1b2c3d4
```

## API Desktop Locale

Quanno Omi Desktop espone 'a API locale soja, ll'agiente ponno addimannà 'a
storia 'e schermo ncoppa 'o dispositivo, 'e riassunte, SQL e 'e task senza
ausà 'a API dev d' 'o cloud:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# o, pe sissione efimere:
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

Cumpleta o cancella 'e task sulo quanno l'utente 'o dimanna chiaramente:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` scrive 'a cattura 'e schermo
ncoppa 'o disco e stampa sempe JSON ncoppa stdout pe li script. L'ID d' 'a
cattura 'e solito vene da `local search-screen` o da SQL ncoppa 'a tabella
`screenshots`. Si Desktop torna nu fallimento strutturato comm'a
`screenshot_pending`, `screenshot_file_missing` o `screenshot_chunk_corrupted`,
'a moda JSON conserva 'e campe `reason`, `hint` e `screenshot_id` ncoppa stderr
accussì ll'agiente ponno riprovà cu n'ID cchiù viecchio o segnalà 'o blocco
esatto. Valida 'e nisciute riesciute cu `file PATH` primma 'e passàlle a li
strumente 'e visione.

## Asempio cumpleto: ciclo 'e agente in Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Invoca 'a CLI omi 'n moda JSON, arzanno ncoppa codece 'e nisciuta nun riesciute."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # 'A CLI stampa errore strutturate ncoppa stderr 'n moda JSON:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Legge tutte ll'elemente 'e azzione aperte e marca comme fatte chille cchiù vecchie 'e 30 juorne.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Gestione d' 'e limite 'e ritmo

Memorie: 120/ora. Cunversazzione: 25/ora. Criazzione 'n lotto: 15/ora.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # limitato 'o ritmo
    err = json.loads(result.stderr)
    # err["detail"] pare comm'a: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Cunsiglie

* Ausa `--profile <name>` si l'agente tujo gestisce cchiù cunte Omi. Ogne
  profilo tene 'a credenziale e 'a base API soja.
* Ausa `--api-base http://localhost:8080` pe pruvà 'o backend locale.
* Ausa `OMI_LOCAL_API_URL` e `OMI_LOCAL_TOKEN` pe suprascrivere 'e
  mpustazzione d' 'a API Desktop Locale d' 'o profilo pe na esecuzzione.
* Ausa `--verbose` p' 'o debug — registra `METHOD path → status (Ns)` ncoppa
  stderr senza tuccà stdout, accussì 'a moda JSON resta valida.
* Pe mannà cuntenuto dint' a na cunversazzione, ausa `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
