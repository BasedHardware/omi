# omi-cli für Agenten

> Praxisleitfaden für LLM-gesteuerte Harnesses (Claude Code, Cursor, eigene Bots).

## Warum die CLI agentenfreundlich ist

* **Stabiler JSON-Vertrag.** `--json` gibt auf stdout ein gültiges JSON-Dokument
  aus und *nur* ein JSON-Dokument — keine Fortschrittsmeldungen, keine Spinner.
  Fehler landen auf stderr als `{"error": "...", "detail": "..."}`.
* **Stabile Exit-Codes.** `0` ok / `1` Bedienfehler / `2` Authentifizierung /
  `3` Server / `4` Ratenlimit / `5` nicht gefunden. Agenten können daran
  verzweigen, ohne Fehlertexte in natürlicher Sprache zu parsen.
* **Keine interaktiven Rückfragen in Headless-Umgebungen.** Übergib `--yes`
  (oder `-y`) an destruktive Befehle; übergib `--api-key` oder setze `OMI_API_KEY`,
  um den interaktiven Login zu überspringen.
* **Nachsichtiges Wiederholungsverhalten.** `429` und `5xx` werden mit Backoff
  wiederholt, bevor sie gemeldet werden.

## Authentifizierung (einmalig, durch den Menschen)

Die Person holt sich einen Entwickler-API-Schlüssel in der Omi-Web-App
(`https://app.omi.me` → Developer → API Keys) und macht eines von beidem:

```bash
omi auth login                          # interaktives Einfügen; der Schlüssel landet nicht in der Shell-History
# oder
export OMI_API_KEY=omi_dev_...          # flüchtig, containerfreundlich
```

## Die fünf häufigsten Aufgaben von Agenten

### 1. Erinnerungen lesen

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Eine Erinnerung anlegen

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Gespräche lesen

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Offene Aufgaben lesen

```bash
omi action-item list --json --open
```

### 5. Eine Aufgabe als erledigt markieren

```bash
omi action-item complete --json a1b2c3d4
```

## Lokale Desktop-API

Wenn Omi Desktop seine lokale API bereitstellt, können Agenten Bildschirmverlauf,
Zusammenfassungen, SQL und Aufgaben direkt auf dem Gerät abfragen, ohne die
Cloud-Entwickler-API zu benutzen:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# oder, für flüchtige Sitzungen:
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

Aufgaben nur dann abschließen oder löschen, wenn die Person es eindeutig
verlangt:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` schreibt den Screenshot auf die
Festplatte und gibt für Skripte weiterhin JSON auf stdout aus. Die Screenshot-ID
stammt meist aus `local search-screen` oder aus SQL über die Tabelle
`screenshots`. Liefert Desktop einen strukturierten Fehler wie
`screenshot_pending`, `screenshot_file_missing` oder
`screenshot_chunk_corrupted`, behält der JSON-Modus die Felder `reason`, `hint`
und `screenshot_id` auf stderr bei, sodass der Agent es mit einer älteren ID
erneut versuchen oder den genauen Blocker melden kann. Prüfe erfolgreiche
Ausgaben mit `file PATH`, bevor du sie an Vision-Werkzeuge weitergibst.

## Ausgearbeitetes Beispiel: Agentenschleife in Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Ruft die omi-CLI im JSON-Modus auf und wirft bei Exit-Codes ungleich 0 eine Ausnahme."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # Im JSON-Modus schreibt die CLI strukturierte Fehler auf stderr:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Alle offenen Aufgaben lesen und alles älter als 30 Tage als erledigt markieren.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Umgang mit Ratenlimits

Erinnerungen: 120/Std. Gespräche: 25/Std. Stapelanlagen: 15/Std.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # Ratenlimit
    err = json.loads(result.stderr)
    # err["detail"] sieht so aus: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Tipps

* Verwende `--profile <name>`, wenn dein Agent mehrere Omi-Konten jongliert.
  Jedes Profil hat eigene Zugangsdaten und eine eigene API-Basis.
* Verwende `--api-base http://localhost:8080` zum Testen gegen ein lokales Backend.
* Verwende `OMI_LOCAL_API_URL` und `OMI_LOCAL_TOKEN`, um die im Profil
  gespeicherten Desktop-API-Einstellungen für einen einzelnen Lauf zu übersteuern.
* Verwende `--verbose` zum Debuggen — es protokolliert `METHOD path → status (Ns)`
  auf stderr, ohne stdout zu berühren, sodass der JSON-Modus gültig bleibt.
* Um Inhalte per Pipe in ein Gespräch zu leiten, verwende `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
