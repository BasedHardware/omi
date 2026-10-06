# omi-cli für Agenten

> Praktischer Leitfaden für LLM-gesteuerte Testumgebungen und Bots (Claude Code, Cursor oder eigene Bots).

## Warum das CLI agentenfreundlich ist

* **Stabiler JSON-Vertrag.** `--json` gibt ein gültiges JSON-Dokument auf stdout aus
  und *ausschließlich* ein JSON-Dokument – keine Fortschrittsmeldungen, keine Spinner.
  Fehler werden auf stderr als `{"error": "...", "detail": "..."}` ausgegeben.
* **Stabile Exit-Codes.** `0` OK / `1` Falsche Verwendung / `2` Authentifizierung /
  `3` Serverfehler / `4` Ratenbegrenzung / `5` Nicht gefunden. Agenten können
  anhand dieser Codes verzweigen, ohne natürlichsprachige Fehler parsen zu müssen.
* **Keine interaktiven Eingabeaufforderungen in Headless-Kontexten.** Übergeben Sie
  `--yes` (oder `-y`) an destruktive Befehle; übergeben Sie `--api-key` oder setzen
  Sie `OMI_API_KEY`, um die interaktive Anmeldung zu überspringen.
* **Tolerantes Wiederholungsverhalten.** Bei `429` und `5xx` wird automatisch ein
  Backoff-Retry durchgeführt, bevor ein Fehler gemeldet wird.

## Authentifizierung (einmalig, durch den Benutzer)

Der Benutzer ruft einen Entwickler-API-Schlüssel über die Omi-Web-App ab
(`https://app.omi.me` → Developer → API Keys) und wählt eine der folgenden Optionen:

```bash
omi auth login                          # interactive paste; key not in shell history
# or
export OMI_API_KEY=omi_dev_...          # ephemeral, container-friendly
```

## Die fünf häufigsten Aufgaben für Agenten

### 1. Erinnerungen lesen

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Eine Erinnerung erstellen

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Konversationen lesen

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

Wenn Omi Desktop seine lokale API bereitstellt, können Agenten auf dem Gerät
Bildschirmverlauf, Zusammenfassungen, SQL und Aufgaben abfragen, ohne die
Cloud-Dev-API zu nutzen:

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

Aufgaben nur abschließen oder löschen, wenn der Benutzer dies ausdrücklich anfordert:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` schreibt den Screenshot auf die
Festplatte und gibt weiterhin JSON auf stdout für Skripte aus. Die Screenshot-ID
stammt normalerweise aus `local search-screen` oder SQL über die Tabelle
`screenshots`. Wenn Desktop einen strukturierten Fehler zurückgibt (wie
`screenshot_pending`, `screenshot_file_missing` oder `screenshot_chunk_corrupted`),
behält der JSON-Modus die Felder `reason`, `hint` und `screenshot_id` auf stderr bei,
sodass Agenten eine ältere ID erneut versuchen oder die genaue Ursache melden können.
Erfolgreiche Ausgaben vor der Übergabe an Vision-Tools mit `file PATH` validieren.

## Vollständiges Beispiel: Python-Agentenschleife

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

## Umgang mit Ratenbegrenzungen

Erinnerungen: 120/Std. Konversationen: 25/Std. Batch-Erstellungen: 15/Std.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Tipps

* Verwenden Sie `--profile <name>`, wenn Ihr Agent mehrere Omi-Konten verwaltet.
  Jedes Profil hat eigene Anmeldedaten und API-Basis.
* Verwenden Sie `--api-base http://localhost:8080` für lokale Backend-Tests.
* Verwenden Sie `OMI_LOCAL_API_URL` und `OMI_LOCAL_TOKEN`, um die
  Desktop-API-Einstellungen eines Profils für einen Durchlauf zu überschreiben.
* Verwenden Sie `--verbose` zum Debuggen — protokolliert `METHOD path → status (Ns)`
  auf stderr, ohne stdout zu beeinflussen, sodass der JSON-Modus gültig bleibt.
* Verwenden Sie `--text -`, um Inhalte in eine Konversation weiterzuleiten:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
