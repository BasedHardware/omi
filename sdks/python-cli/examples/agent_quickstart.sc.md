# omi-cli pro sos agentes

> Guida pràtica pro sos strumentos guiados da LLM (Claude Code, Cursor, sos bots tuos).

## Pro ite sa CLI est amigàbile pro sos agentes

* **Contratu JSON istàbile.** `--json` emitet un documentu JSON vàlidu a stdout e
  *iscurmente* un documentu JSON — chena messàgios de progressu, chena spinners.
  Sos errores andant a stderr comente `{"error": "...", "detail": "..."}`.
* **Còdigos de essida istàbiles.** `0` bene / `1` impreu / `2` autenticatzione /
  `3` serbidore / `4` limitadu da su ritmu / `5` non agatadu. Sos agentes podent
  branchare subra de custos chena analizare errores in limba naturale.
* **Chena preguntas interativas in contestos headless.** Passa `--yes` (o `-y`)
  a sos cumandos distrutivos; passa `--api-key` o cunfigura `OMI_API_KEY` pro
  brincare su login interativu.
* **Cumportamentu de riprova tollerante.** `429` e `5xx` sunt riprovados cun
  backoff in antis de bessire.

## Autenticatzione (una bia, da s'òmine)

S'utilizadore otènet una crae API dev da s'aplicatzione web de Omi
(`https://app.omi.me` → Developer → API Keys) e pois:

```bash
omi auth login                          # incollamentu interativu; sa crae non andat in s'istòria de su shell
# o
export OMI_API_KEY=omi_dev_...          # efìmeru, adatu a sos contenidores
```

## Sas chimbe cosas chi sos agentes faghent prus a su sòlitu

### 1. Lèghere sas memòrias

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Creare una memòria

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Lèghere sas conversatziones

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Lèghere sos elementos de atzione abertos

```bash
omi action-item list --json --open
```

### 5. Marcares un elementu de atzione comente fatu

```bash
omi action-item complete --json a1b2c3d4
```

## API Desktop Locale

Cando Omi Desktop isponet sa API locale sua, sos agentes podent preguntare
s'istòria de s'ischermu in su dispositivu, sos resùmenes, SQL e sas fainas
chena impreare sa API dev de sa nue:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# o, pro sessões efìmeras:
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

Cumpleta o iscancella fainas isceti cando s'utilizadore lu pede claramente:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` iscrivet sa captura de
ischermu in su discu e iscrivet semper JSON a stdout pro sos scripts. S'ID de
sa captura benit de su sòlitu dae `local search-screen` o dae SQL subra de sa
taula `screenshots`. Si Desktop torrat un fallimentu istructuradu comente
`screenshot_pending`, `screenshot_file_missing` o `screenshot_chunk_corrupted`,
su modu JSON mantenet sos campos `reason`, `hint` e `screenshot_id` a stderr
pro chi sos agentes podant torrare a proare cun un ID betzu o sinnalare su
blocu esatu. Valida sos resurtados andados bene cun `file PATH` in antis de los
passare a sos istrumentos de visione.

## Esempru cumpletu: tziclu de agente in Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Invoca sa CLI omi in modu JSON, subrende in còdigos de essida non andados bene."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # Sa CLI iscrivet errores istructurados a stderr in modu JSON:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Lèghet sos elementos de atzione abertos totos e marca comente fatus sos chi ant prus de 30 dies.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Gestionare sos limites de ritmu

Memòrias: 120/ora. Conversatziones: 25/ora. Creazioni in grupu: 15/ora.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # limitadu da su ritmu
    err = json.loads(result.stderr)
    # err["detail"] paret comente: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Cussìgios

* Imprea `--profile <name>` si s'agente tuo gestit prus contos Omi. Cada perfil
  ten sa credenziale e sa base API sua.
* Imprea `--api-base http://localhost:8080` pro proare su backend locale.
* Imprea `OMI_LOCAL_API_URL` e `OMI_LOCAL_TOKEN` pro subrascriere sos
  paràmetros de sa API Desktop Locale de su perfil pro una esecutzione.
* Imprea `--verbose` pro su debug — registrat `METHOD path → status (Ns)` a
  stderr chena afetare stdout, duncas su modu JSON abarrat vàlidu.
* Pro incanalare cuntenutu a una conversatzione, imprea `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
