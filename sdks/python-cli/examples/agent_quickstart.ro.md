# omi-cli pentru agenți

> Ghid practic pentru harness-uri conduse de LLM (Claude Code, Cursor, bot-urile tale).

## De ce CLI-ul este prietenos cu agenții

* **Contract JSON stabil.** `--json` emite un document JSON valid pe stdout și
  *doar* un document JSON — fără mesaje de progres, fără spinners. Erorile merg pe
  stderr ca `{"error": "...", "detail": "..."}`.
* **Coduri de ieșire stabile.** `0` ok / `1` utilizare / `2` auth / `3` server / `4`
  rată limitată / `5` negăsit. Agenții pot ramifica pe baza acestora fără să parseze
  erori în limbaj natural.
* **Fără prompturi interactive în contexte headless.** Trimite `--yes` (sau `-y`)
  pentru comenzi destructivi; trimite `--api-key` sau setează `OMI_API_KEY` pentru a
  ocoli autentificarea interactivă.
* **Comportament de reîncercare indulgent.** `429` și `5xx` sunt reîncercate cu backoff
  înainte de a fi afișate.

## Auth (o singură dată, de către omul)

Utilizatorul obține un cheie API de dezvoltare din aplicația web Omi
(`https://app.omi.me` → Developer → API Keys) și fie:

```bash
omi auth login                          # interactive paste; key not in shell history
# or
export OMI_API_KEY=omi_dev_...          # ephemeral, container-friendly
```

## Cele cinci lucruri pe care agenții le fac cel mai des

### 1. Citește amintiri

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Creează o amintire

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Citește conversații

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Citește action items deschise

```bash
omi action-item list --json --open
```

### 5. Marchează un action item ca finalizat

```bash
omi action-item complete --json a1b2c3d4
```

## API local Desktop

Când Omi Desktop expune API-ul său local, agenții pot interroga istoricul ecranului
dispozitivului, recapitulări, SQL și sarcini fără a folosi API-ul cloud de dezvoltare:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# or, for ephemeral sessions:
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

Finalizează sau șterge sarcini doar când utilizatorul cere clar:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` scrie captura de ecran pe
disc și încă tipărește JSON pe stdout pentru scripturi. ID-ul capturii vine de
obicei din `local search-screen` sau din SQL peste tabelul `screenshots`. Dacă
Desktop returnează o eroare structurată precum `screenshot_pending`,
`screenshot_file_missing` sau `screenshot_chunk_corrupted`, modul JSON păstrează
câmpurile `reason`, `hint` și `screenshot_id` pe stderr ca agenții să poată
reîncerca un ID mai vechi sau să raporteze blocajul exact. Validează ieșirile
reușite cu `file PATH` înainte de a le trimite către tool-uri de viziune.

## Exemplu practic: buclă agent Python

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

## Gestionarea limitelor de rată

Amintiri: 120/oră. Conversații: 25/oră. Creări în lot: 15/oră.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Sfaturi

* Folosește `--profile <nume>` dacă agentul tău gestionează mai multe conturi Omi.
  Fiecare profil are propriile credențiale și API base.
* Folosește `--api-base http://localhost:8080` pentru testarea locală a backend-ului.
* Folosește `OMI_LOCAL_API_URL` și `OMI_LOCAL_TOKEN` pentru a suprascrie setările
  API Desktop locale ale unui profil pentru o singură rulare.
* Folosește `--verbose` pentru depanare — înregistrează `METHOD path → status (Ns)` pe stderr
  fără a afecta stdout, astfel încât modul JSON rămâne valid.
* Pentru a alimenta conținut într-o conversație, folosește `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
