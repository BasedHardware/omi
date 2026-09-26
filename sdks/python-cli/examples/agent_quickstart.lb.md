# omi-cli fir Agenten

> Praktesche Guide fir LLM-gedriwwen Harnessen (Claude Code, Cursor, déi eegen Bots).

## Firwat d'CLI agentfrëndlech ass

* **Stabilen JSON-Kontrakt.** `--json` gëtt e gültegt JSON-Dokument op stdout aus
  an *nëmmen* en JSON-Dokument — keng Fortschrëttsmeldungen, keng Spinner.
  Feeler ginn op stderr als `{"error": "...", "detail": "..."}`.
* **Stabil Exit-Coden.** `0` ok / `1` Benotzung / `2` Authentifikatioun / `3`
  Server / `4` Rate-Limit / `5` net fonnt. Agenten kënnen dorop branchéieren
  ouni Feeler an natierlecher Sprooch ze parsen.
* **Keng interaktiv Prompter an headless Kontexter.** Gëff `--yes` (oder `-y`)
  bei destruktiven Kommandos; gëff `--api-key` oder setz `OMI_API_KEY` fir
  d'interaktivt Login z'iwwersprangen.
* **Tolerant Retry-Verhalen.** `429` an `5xx` ginn mat Backoff erëm probéiert
  ier se duerchkommen.

## Authentifikatioun (eemol, duerch de Mënsch)

De Benotzer kritt en Dev-API-Schlëssel vun der Omi-Web-App
(`https://app.omi.me` → Developer → API Keys) an entweeder:

```bash
omi auth login                          # interaktivt afloen; Schlëssel kënnt net an d'Shell-Historik
# oder
export OMI_API_KEY=omi_dev_...          # ephemer, containerfrëndlech
```

## Déi fënnef Saachen déi Agenten am heefegsten maachen

### 1. Erënnerungen liesen

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Eng Erënnerung uleeën

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Gespréicher liesen

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Oppe Aktiounsitemen liesen

```bash
omi action-item list --json --open
```

### 5. En Aktiounsitem als fäerdeg markéieren

```bash
omi action-item complete --json a1b2c3d4
```

## Lokal Desktop-API

Wann Omi Desktop seng lokal API exposéiert, kënnen Agenten d'Bildschiermgeschicht
um Apparat, Rekapen, SQL an Aufgaben ofruffen ouni d'Cloud-Dev-API ze benotzen:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# oder, fir ephemer Sessiounen:
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

Kompletéier oder läsch Aufgaben nëmmen wann den Benotzer et kloer freet:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` schreift de Screenshot op
d'Plack a dréckt weiderhin JSON op stdout fir Skripten. D'Screenshot-ID kënnt
meeschtens vun `local search-screen` oder SQL iwwer d'`screenshots`-Tabell. Wann
Desktop e strukturéierte Feeler wéi `screenshot_pending`,
`screenshot_file_missing` oder `screenshot_chunk_corrupted` zréckgëtt, behält de
JSON-Modus d'Felder `reason`, `hint` an `screenshot_id` op stderr, sou datt
Agenten en eelere ID nach eng Kéier kënne probéieren oder de geneeë Blocker
mellen. Validéier erfollegräich Ausgaben mat `file PATH` ier s du se un
Vision-Tools weidergëss.

## Geschafft Beispill: Python-Agent-Loop

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Ruff d'omi CLI am JSON-Modus op, a werft bei net-erfollegräichen Exit-Coden."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # D'CLI dréckt strukturéiert Feeler op stderr am JSON-Modus:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Liest all oppe Aktiounsitemen a markéiert alles méi al wéi 30 Deeg als fäerdeg.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Rate-Limiten handhaben

Erënnerungen: 120/Stonn. Gespréicher: 25/Stonn. Batch-Erstellen: 15/Stonn.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # Rate-Limit
    err = json.loads(result.stderr)
    # err["detail"] gesäit esou aus: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Tipps

* Benotz `--profile <name>` wann däin Agent verschidde Omi-Konten handhabt.
  All Profil huet säin eegene Credential an API-Basis.
* Benotz `--api-base http://localhost:8080` fir de lokale Backend ze testen.
* Benotz `OMI_LOCAL_API_URL` an `OMI_LOCAL_TOKEN` fir d'lokal
  Desktop-API-Astellungen vum Profil fir ee Run z'iwwerschreiwen.
* Benotz `--verbose` fir Debuggen — et loggt `METHOD path → status (Ns)` op
  stderr ouni stdout ze beaflossen, sou datt de JSON-Modus gülteg bleift.
* Fir Inhalt an e Gespréich ze pipen, benotz `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
