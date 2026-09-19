# omi-cli pentru agenți

> Ghid practic pentru medii bazate pe LLM (Claude Code, Cursor, proprii boți).

## De ce este CLI-ul potrivit pentru agenți

* **Contract JSON stabil.** `--json` emite un document JSON valid la stdout și *doar* un document JSON — fără mesaje de progres, fără indicatoare de încărcare. Erorile merg la stderr ca `{"error": "...", "detail": "..."}`.
* **Coduri de ieșire stabile.** `0` ok / `1` utilizare / `2` autentificare / `3` server / `4` rată limitată / `5` negăsit. Agenții se pot ramifica pe baza acestora fără a analiza erorile în limbaj natural.
* **Fără solicitări interactive în contexte headless.** Transmiteți `--yes` (sau `-y`) la comenzile distructive; transmiteți `--api-key` sau setați `OMI_API_KEY` pentru a sări peste autentificarea interactivă.
* **Comportament tolerant la reîncercare.** Erorile `429` și `5xx` sunt reîncercate cu backoff înainte de a fi afișate.

## Autentificare (o singură dată, de către utilizator)

Utilizatorul obține o cheie API pentru dezvoltatori din aplicația web Omi (`https://app.omi.me` → Developer → API Keys) și alege una din opțiuni:

```bash
omi auth login                          # lipire interactivă; cheia nu rămâne în istoricul shell-ului
# sau
export OMI_API_KEY=omi_dev_...          # efemer, potrivit pentru containere
```

## Cele cinci acțiuni cele mai frecvente ale agenților

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

### 4. Citirea sarcinilor deschise

```bash
omi action-item list --json --open
```

### 5. Marcarea unei sarcini ca finalizată

```bash
omi action-item complete --json a1b2c3d4
```

## API local Desktop

Când Omi Desktop expune API-ul său local, agenții pot interoga istoricul ecranului de pe dispozitiv, rezumatele, SQL și sarcinile fără a utiliza API-ul cloud pentru dezvoltatori:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# sau, pentru sesiuni efemere:
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

Finalizați sau ștergeți sarcini doar atunci când utilizatorul solicită în mod explicit acest lucru:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` scrie captura de ecran pe disc și continuă să afișeze JSON la stdout pentru scripturi. ID-ul capturii provine de obicei din `local search-screen` sau din interogarea SQL a tabelului `screenshots`. Dacă Desktop returnează o eroare structurată precum `screenshot_pending`, `screenshot_file_missing` sau `screenshot_chunk_corrupted`, modul JSON păstrează câmpurile `reason`, `hint` și `screenshot_id` pe stderr, astfel încât agenții să poată reîncerca un ID mai vechi sau să raporteze blocajul exact. Validați ieșirile reușite cu `file PATH` înainte de a le transmite instrumentelor de procesare vizuală.

## Exemplu practic: buclă de agent în Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Apelează omi CLI în modul JSON, ridicând o excepție la coduri de ieșire diferite de 0."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI-ul afișează erori structurate la stderr în modul JSON:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi a ieșit cu codul {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Citește toate sarcinile deschise și le marchează pe cele mai vechi de 30 de zile ca finalizate.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Gestionarea limitelor de rată

Amintiri: 120/oră. Conversații: 25/oră. Creare în serie: 15/oră.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rată limitată
    err = json.loads(result.stderr)
    # err["detail"] arată astfel: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Sfaturi

* Folosiți `--profile <nume>` dacă agentul dumneavoastră gestionează mai multe conturi Omi. Fiecare profil are propriile credențiale și bază API.
* Folosiți `--api-base http://localhost:8080` pentru testarea locală a backend-ului.
* Folosiți `OMI_LOCAL_API_URL` și `OMI_LOCAL_TOKEN` pentru a suprascrie setările locale ale API-ului Desktop pentru o singură rulare.
* Folosiți `--verbose` pentru depanare — înregistrează `METHOD path → status (Ns)` la stderr fără a afecta stdout, astfel încât modul JSON rămâne valid.
* Pentru a trimite conținut într-o conversație prin pipe, utilizați `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
