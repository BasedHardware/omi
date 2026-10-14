# omi-cli fir Agenten

> Praktesche Guide fir LLM-gefouert Harnesser (Claude Code, Cursor, Är eegene Bots).

## Firwat de CLI agentefrëndlech ass

* **Stabilt JSON-Kontrakt.** `--json` gëtt e valablen JSON-Dokument op stdout a
  *nëmmen* e JSON-Dokument — keng Fortschrëtts-Messagen, keng Spinner. Feeler
  ginn op stderr als `{"error": "...", "detail": "..."}`.
* **Stabil Ausgangscoden.** `0` gutt / `1` Benotzung / `2` auth / `3` Server /
  `4` Geschwindegkeetslimit / `5` net fonnt. Agenten kënnen op dësen branchéieren
  ouni natierlech-sproocheg Feeler ze analyséieren.
* **Keng interaktiv Prompten a headless Kontexter.** Pass `--yes` (oder `-y`) un
  destruktiv Kommandoen; pass `--api-key` oder setz `OMI_API_KEY` fir interaktive
  Login ze iwwersprangen.
* **Verzeechend Retry-Verhalen.** `429` an `5xx` ginn mat backoff widderholl
  éier se erauskommen.

## Auth (eemol, vum Mënsch)

De Benotzer hëlt en dev API-Schlëssel vun der Omi Webapp
(`https://app.omi.me` → Developer → API Keys) a entweder:

```bash
omi auth login                          # interaktiv Pechen; de Schlëssel bleift net an der Shell-Histoir
# oder
export OMI_API_KEY=omi_dev_...          # efemer, ideal fir Containeren
```

## Déi fënnef Saachen, déi Agenten am meeschte maachen

### 1. Erënnerunge liesen

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Eng Erënnerung erstellen

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Conversatiounen liesen

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Oppen Aktiounspunkten liesen

```bash
omi action-item list --json --open
```

### 5. En Aktiounspunkt als gemaach markéieren

```bash
omi action-item complete --json a1b2c3d4
```

## Lokal Desktop-API

Wann Omi Desktop seng lokal API aussetzt, kënnen Agenten den Apparatsbildschierm
historie, Recaps, SQL an Aufgaben opfrot ouni d'Cloud-dev-API ze benotzen:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# oder, fir efemer Sessiounen:
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

Fäerdeg oder läschen Aufgaben nëmmen wann de Benotzer et kloer fro:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` schreift de Screenshot op den
Disk an dréckt weiderhin JSON op stdout fir Skripter. D'Screenshot-ID kënnt
normalerweis vu `local search-screen` oder SQL iwwer d' `screenshots`-Tabell.
Wann Desktop e strukturéierte Feeler wéi `screenshot_pending`,
`screenshot_file_missing` oder `screenshot_chunk_corrupted` zréckgëtt, beaart
de JSON-Modus d'`reason`-, `hint`- an `screenshot_id`-Felder op stderr fir datt
Agenten e méi ale ID widderprobéieren oder de genee Blocker mellen.
Validéiert erfollegräich Ausgaben mat `file PATH` éier Dir se un Visiouns-Tools
wiiderginn.

## Aarbechtsbeispill: Python-Agent-Schleef

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

## Gestioun vun de Geschwindegkeetslimiten

Erënnerungen: 120/h. Conversatiounen: 25/h. Batch-Kreatiounen: 15/h.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Tipps

* Benotz `--profile <name>` wann Ären Agent méi Omi-Konten verwalt. All Profil
  huet seng eegen Kredenziale an API-Basis.
* Benotz `--api-base http://localhost:8080` fir lokal Backend-Tester.
* Benotz `OMI_LOCAL_API_URL` an `OMI_LOCAL_TOKEN` fir d'Profil-lokal-Desktop-API-Astellungen
  fir eng Ausféierung z'iwwerschreiwen.
* Benotz `--verbose` fir Debugging — et loggt `METHOD path → status (Ns)` op
  stderr ouni stdout ze beaflosse, sou datt de JSON-Modus valabel bleift.
* Fir Inhalt an eng Conversatioun ze pipen, benotz `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
