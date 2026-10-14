# omi-cli za agente

> Praktični vodnik za harness-e, ki jih vodi LLM (Claude Code, Cursor, vaši lastni boti).

## Zakaj je CLI prijazen do agentov

* **Stabilna JSON pogodba.** `--json` izda veljaven JSON dokument na stdout in
  *samo* JSON dokument — brez sporočil o napredku, brez spinnerjev. Napake gredo
  na stderr kot `{"error": "...", "detail": "..."}`.
* **Stabilne izhodne kode.** `0` v redu / `1` uporaba / `2` auth / `3` strežnik /
  `4` omejitev hitrosti / `5` ni najdeno. Agenti se lahko razvejijo nanje brez
  razčlenjevanja napak v naravnem jeziku.
* **Brez interaktivnih pozivov v headless kontekstih.** Podajte `--yes` (ali `-y`)
  destruktivnim ukazom; podajte `--api-key` ali nastavite `OMI_API_KEY`, da preskočite
  interaktivno prijavo.
* **Odpustljivo vedenje ponovitev.** `429` in `5xx` se ponovita z backoff-om, preden
  se pojavita.

## Auth (enkrat, človek)

Uporabnik dobi dev API ključ iz Omi spletne aplikacije
(`https://app.omi.me` → Developer → API Keys) in bodisi:

```bash
omi auth login                          # interaktivno lepljenje; ključ ne ostane v zgodovini lupine
# ali
export OMI_API_KEY=omi_dev_...          # kratkotrajen, idealen za vsebnike
```

## Pet stvari, ki jih agenti najpogosteje počnejo

### 1. Branje spominov

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Ustvarjanje spomina

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Branje pogovorov

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Branje odprtih točk ukrepov

```bash
omi action-item list --json --open
```

### 5. Označevanje točke ukrepa kot dokončane

```bash
omi action-item complete --json a1b2c3d4
```

## Lokalni Desktop API

Ko Omi Desktop izpostavi svoj lokalni API, lahko agenti poizvedujejo zgodovino
zaslona naprave, povzetke, SQL in naloge brez uporabe oblakov dev API:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# ali, za kratkotrajne seje:
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

Dokončajte ali izbrišite naloge samo, ko uporabnik to jasno zahteva:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` zapiše posnetek zaslona na
disk in še vedno izpiše JSON na stdout za skripte. ID posnetka običajno prihaja
iz `local search-screen` ali SQL nad tabelo `screenshots`. Če Desktop vrne
strukturirano napako, kot je `screenshot_pending`, `screenshot_file_missing` ali
`screenshot_chunk_corrupted`, JSON način ohrani polja `reason`, `hint` in
`screenshot_id` na stderr, da lahko agenti poskusijo s starejšim ID-jem ali
sporočijo natančen zaviralec. Preverite uspešne izhode z `file PATH`, preden jih
posredujete vidnim orodjem.

## Izdelan primer: Python agentova zanka

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

## Upravljanje omejitev hitrosti

Spomini: 120/h. Pogovori: 25/h. Paketne ustvaritve: 15/h.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Nasveti

* Uporabite `--profile <name>`, če vaš agent upravlja več Omi računov. Vsak profil
  ima svoje poverilnice in API bazo.
* Uporabite `--api-base http://localhost:8080` za lokalne backend teste.
* Uporabite `OMI_LOCAL_API_URL` in `OMI_LOCAL_TOKEN`, da za eno izvedbo zamenjate
  profilove nastavitve lokalnega Desktop API-ja.
* Uporabite `--verbose` za odpravljanje napak — beleži `METHOD path → status (Ns)`
  na stderr brez vpliva na stdout, tako da JSON način ostane veljaven.
* Za usmerjanje vsebine v pogovor uporabite `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
