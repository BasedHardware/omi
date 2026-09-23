# omi-cli za agente

> Praktični vodnik za LLM-ovodene harness-e (Claude Code, Cursor, vaši boti).

## Zakaj je CLI prijazen do agentov

* **Stabilna JSON pogodba.** `--json` izpiše veljaven JSON dokument na stdout in
  *samo* JSON dokument — brez sporočil o napredku, brez spinnerjev. Napake gredo na
  stderr kot `{"error": "...", "detail": "..."}`.
* **Stabilne exit kode.** `0` ok / `1` uporaba / `2` auth / `3` server / `4`
  omejitev hitrosti / `5` ni najdeno. Agenti lahko vejijo na podlagi teh brez
  razčlenjevanja napak v naravnem jeziku.
* **Brez interaktivnih pozivov v headless kontekstih.** Pošlji `--yes` (ali `-y`)
  destruktivnim ukazom; pošlji `--api-key` ali nastavi `OMI_API_KEY` za preskočitev
  interaktivne prijave.
* **Odpustljivo vedenje pri ponovitvah.** `429` in `5xx` se ponovno poskusita z
  backoffom pred prikazom.

## Auth (enkrat, s strani človeka)

Uporabnik dobi dev API ključ iz Omi spletne aplikacije
(`https://app.omi.me` → Developer → API Keys) in bodisi:

```bash
omi auth login                          # interactive paste; key not in shell history
# or
export OMI_API_KEY=omi_dev_...          # ephemeral, container-friendly
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

### 4. Branje odprtih action itemov

```bash
omi action-item list --json --open
```

### 5. Označevanje action itema kot končanega

```bash
omi action-item complete --json a1b2c3d4
```

## Lokalni Desktop API

Ko Omi Desktop izpostavi svojo lokalno API, lahko agenti vprašajo zgodovino zaslona
naprave, recap, SQL in naloge brez uporabe oblaka dev API:

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

Dokončaj ali izbriši naloge samo, ko uporabnik jasno prosi:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` zapiše posnetek zaslona na
disk in še vedno izpisuje JSON na stdout za skripte. ID posnetka običajno prihaja iz
`local search-screen` ali SQL nad tabelo `screenshots`. Če Desktop vrne
strukturirano napako kot `screenshot_pending`, `screenshot_file_missing`
ali `screenshot_chunk_corrupted`, JSON način ohrani polja `reason`, `hint` in
`screenshot_id` na stderr, da lahko agenti poskusijo starejši ID ali poročajo
natančno oviro. Preveri uspešne izhode z `file PATH` preden jih posreduješ
orodjem za vision.

## Praktični primer: Python agent zanka

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

## Obravnava omejitev hitrosti

Spomini: 120/uro. Pogovori: 25/uro. Množično ustvarjanje: 15/uro.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Nasveti

* Uporabi `--profile <ime>` če tvoj agent upravlja z več Omi računi. Vsak
  profil ima svoje poverilnice in API base.
* Uporabi `--api-base http://localhost:8080` za lokalno testiranje backend-a.
* Uporabi `OMI_LOCAL_API_URL` in `OMI_LOCAL_TOKEN` za preglasitev profil-lokalnih
  Desktop API nastavitev za en zagon.
* Uporabi `--verbose` za razhroščevanje — beleži `METHOD path → status (Ns)` na stderr
  brez vplivanja na stdout, tako da JSON način ostane veljaven.
* Za vsebino v pogovor uporabi `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
