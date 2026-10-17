# omi-cli pentru agenți

> Ghid practic pentru harness-uri conduse de LLM (Claude Code, Cursor, roboții tăi).

## De ce CLI-ul este prietenos cu agenții

* **Contract JSON stabil.** `--json` emite pe stdout un document JSON valid și *doar* JSON — fără mesaje de progres sau spinners. Erorile ajung pe stderr ca `{"error": "...", "detail": "..."}`.
* **Coduri de ieșire stabile.** `0` ok / `1` utilizare / `2` auth / `3` server / `4` rate limited / `5` negăsit. Agenții pot ramifica pe ele fără a parsa erori în limbaj natural.
* **Fără prompturi interactive în contexte headless.** Transmite `--yes` (sau `-y`) comenzilor distructive; transmite `--api-key` sau setează `OMI_API_KEY` pentru a sări peste loginul interactiv.
* **Reîncercări îngăduitoare.** `429` și `5xx` sunt reîncercate cu backoff înainte de a apărea.

## Autentificare (o dată, de către om)

Utilizatorul obține o dev API key din aplicația web Omi
(`https://app.omi.me` → Developer → API Keys) și fie:

```bash
omi auth login                          # lipire interactivă; cheia nu în istoricul shell
# # sau
export OMI_API_KEY=omi_dev_...          # efemeră, prietenoasă cu containere
```

## Cele cinci lucruri pe care agenții le fac cel mai des

### 1. Citirea memories

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Crearea unei memory

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Citirea conversations

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Citirea action items deschise

```bash
omi action-item list --json --open
```

### 5. Marcarea unui action item ca făcut

```bash
omi action-item complete --json a1b2c3d4
```

## API Desktop local

Când Omi Desktop expune API-ul local, agenții pot interoga istoricul
de ecran on-device, recapuri, SQL și task-uri fără dev API din cloud:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# # sau, pentru sesiuni efemere:
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

Finalizează sau șterge task-uri doar când utilizatorul cere clar:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` scrie screenshot-ul pe
disc și continuă să printeze JSON pe stdout pentru scripturi. ID-ul screenshot-ului
vine de obicei din `local search-screen` sau SQL peste tabela `screenshots`. Dacă
Desktop returnează o eroare structurată precum `screenshot_pending`,
`screenshot_file_missing` sau `screenshot_chunk_corrupted`, modul JSON păstrează
`reason`, `hint` și `screenshot_id` pe stderr astfel încât agentul poate reîncerca
un ID mai vechi sau poate raporta blocajul exact. Validează ieșirile reușite cu
`file PATH` înainte de a le pasa uneltelor de viziune.

## Exemplu lucrat: buclă de agent Python

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

# Citește toate action items deschise și marchează-le complete pe cele mai vechi de 30 de zile.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Gestionarea rate limits

Memories: 120/oră. Conversations: 25/oră. Creări în lot: 15/oră.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] arată așa: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Sfaturi

* Folosește `--profile <name>` dacă agentul jonglează cu mai multe conturi Omi.
  Fiecare profil are propriile credențiale și bază API.
* Folosește `--api-base http://localhost:8080` pentru testarea backend-ului local.
* Folosește `OMI_LOCAL_API_URL` și `OMI_LOCAL_TOKEN` pentru a suprascrie
  setările Desktop API ale profilului pentru o singură rulare.
* Folosește `--verbose` pentru debugging — loghează `METHOD path → status (Ns)`
  pe stderr fără a afecta stdout, deci modul JSON rămâne valid.
* Pentru a trimite conținut prin pipe într-o conversation, folosește `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
