# omi-cli pentru agenți

> Ghid practic pentru sisteme bazate pe LLM (Claude Code, Cursor, proprii boți).

## De ce CLI-ul este optimizat pentru agenți

* **Contract JSON stabil.** Parametrul `--json` trimite un document JSON valid pe stdout și
  *doar* un document JSON — fără mesaje de progres, fără elemente animate. Erorile sunt trimise către
  stderr sub forma `{"error": "...", "detail": "..."}`.
* **Coduri de ieșire stabile.** `0` succes / `1` eroare de utilizare / `2` autentificare /
  `3` eroare de server / `4` limitare de rată / `5` negăsit. Agenții pot ramifica logica pe baza
  acestor coduri fără a parsa erori în limbaj natural.
* **Fără solicitări interactive în medii headless.** Trimiteți `--yes` (sau `-y`) pentru comenzi
  distructive; trimiteți `--api-key` sau setați `OMI_API_KEY` pentru a omite autentificarea interactivă.
* **Comportament permisiv de reîncercare.** Erorile `429` și `5xx` sunt reîncercate automat
  cu backoff exponențial înainte de a fi returnate.

## Autentificare (o singură dată, de către utilizator)

Utilizatorul obține o cheie API pentru dezvoltatori din aplicația web Omi
(`https://app.omi.me` → Developer → API Keys) și alege una dintre opțiuni:

```bash
omi auth login                          # lipire interactivă; cheia nu apare în istoricul shell-ului
# sau
export OMI_API_KEY=omi_dev_...          # efemer, optim pentru containere
```

## Cele cinci acțiuni cel mai des executate de agenți

### 1. Citirea amintirilor

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Crearea unei amintiri

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Citirea conversațiilor

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Citirea acțiunilor deschise

```bash
omi action-item list --json --open
```

### 5. Marcarea unei acțiuni ca finalizată

```bash
omi action-item complete --json a1b2c3d4
```

## API Desktop Local

Când Omi Desktop expune API-ul său local, agenții pot interoga istoricul ecranului,
rezumatele, SQL și sarcinile de pe dispozitiv fără a utiliza API-ul de cloud dev:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# sau, pentru sesiuni temporare:
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

Finalizați sau ștergeți sarcinile numai atunci când utilizatorul solicită în mod explicit acest lucru:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

Comanda `omi local screenshot SCREENSHOT_ID --output PATH` scrie captura de ecran pe disc și
continuă să afișeze JSON pe stdout pentru scripturi. ID-ul capturii provine de obicei din
`local search-screen` sau dintr-o interogare SQL pe tabela `screenshots`. Dacă Desktop returnează
o eroare structurată precum `screenshot_pending`, `screenshot_file_missing` sau
`screenshot_chunk_corrupted`, modul JSON păstrează câmpurile `reason`, `hint` și `screenshot_id`
pe stderr, permițând agenților să reîncerce cu un ID mai vechi sau să raporteze blocajul exact.
Validați fișierele de ieșire reușite cu `file PATH` înainte de a le transmite instrumentelor vizuale.

## Exemplu practic: buclă agent în Python

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

## Gestionarea limitărilor de rată

Amintiri: 120/oră. Conversații: 25/oră. Creare în lot: 15/oră.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Sfaturi utile

* Folosiți `--profile <nume>` dacă agentul gestionează mai multe conturi Omi. Fiecare profil
  are propriile acreditări și propria adresă API de bază.
* Folosiți `--api-base http://localhost:8080` pentru testarea pe backend local.
* Folosiți `OMI_LOCAL_API_URL` și `OMI_LOCAL_TOKEN` pentru a suprascrie setările locale Desktop API
  ale profilului pentru o singură rulare.
* Folosiți `--verbose` pentru depanare — înregistrează `METHOD path → status (Ns)` pe stderr
  fără a afecta stdout, menținând valid modul JSON.
* Pentru a transmite conținut într-o conversație prin pipe, utilizați `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
