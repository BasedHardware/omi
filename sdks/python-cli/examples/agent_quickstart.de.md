# omi-cli für Agenten

> Praxisanleitung für LLM-gesteuerte Umgebungen (Claude Code, Cursor, eigene Bots).

## Warum das CLI agentenfreundlich ist

* **Stabiler JSON-Vertrag.** `--json` gibt ein gültiges JSON-Dokument nach stdout aus und *nur* dieses — keine Fortschrittsmeldungen oder Spinner. Fehler werden nach stderr als `{"error": "...", "detail": "..."}` geschrieben.
* **Stabile Exit-Codes.** `0` OK / `1` Verwendungsfehler / `2` Authentifizierungsfehler / `3` Serverfehler / `4` Rate-Limit erreicht / `5` Nicht gefunden. Agenten können ohne natürliche-Sprachanalyse von Fehlermeldungen auf diese Codes verzweigen.
* **Keine interaktiven Eingabeaufforderungen in headless-Kontexten.** Übergeben Sie `--yes` (oder `-y`) für destruktive Befehle; übergeben Sie `--api-key` oder setzen Sie `OMI_API_KEY`, um den interaktiven Login zu überspringen.
* **Tolerante Retry-Logik.** `429` und `5xx` werden mit exponentiellem Backoff wiederholt, bevor sie gemeldet werden.

## Authentifizierung (einmalig, durch den Menschen)

Der Benutzer holt einen Entwickler-API-Schlüssel aus der Omi-Web-App (`https://app.omi.me` → Developer → API Keys) und führt eines der folgenden aus:

```bash
omi auth login                          # interaktives Einfügen; der Schlüssel landet nicht in der Shell-Historie
# oder
export OMI_API_KEY=omi_dev_...          # temporär, container-freundlich
```

## Die fünf Dinge, die Agenten am häufigsten tun

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

Wenn Omi Desktop seine lokale API bereitstellt, können Agenten geräteinternen Bildschirmverlauf, Zusammenfassungen, SQL und Aufgaben abfragen, ohne die Cloud-Dev-API zu verwenden:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# temporär, container-freundlich:
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

Erledigen oder löschen Sie Aufgaben nur, wenn der Benutzer dies ausdrücklich wünscht:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` speichert den Screenshot auf der Festplatte und schreibt weiterhin JSON nach stdout für Skripte. Screenshot-IDs stammen typischerweise aus `local search-screen` oder SQL auf der `screenshots`-Tabelle. Wenn Desktop einen strukturierten Fehler wie `screenshot_pending`, `screenshot_file_missing` oder `screenshot_chunk_corrupted` zurückgibt, bewahrt der JSON-Modus die Felder `reason`, `hint` und `screenshot_id` auf stderr, damit Agenten mit einer älteren ID erneut versuchen oder das genaue Hindernis melden können. Überprüfen Sie erfolgreiche Ergebnisse mit `file PATH`, bevor Sie sie an Vision-Tools übergeben.

## Praktisches Beispiel: Python-Agentenloop

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """omi CLI im JSON-Modus ausführen und bei schlechten Exit-Codes Ausnahme werfen."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # Das CLI schreibt strukturierte Fehler im JSON-Modus nach stderr:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi beendet mit Code {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Alle offenen Aufgaben lesen und ältere als 30 Tage als erledigt markieren.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Ratenbegrenzungsbehandlung

Erinnerungen: 120/Stunde. Konversationen: 25/Stunde. Batch-Erstellung: 15/Stunde.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # Rate-Limit erreicht
    err = json.loads(result.stderr)
    # err["detail"] sieht aus wie: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Tipps

* Verwenden Sie `--profile <name>`, wenn Ihr Agent mehrere Omi-Konten verwaltet. Jedes Profil hat eigene Anmeldedaten und API-Basis.
* Verwenden Sie `--api-base http://localhost:8080` für lokale Backend-Tests.
* Verwenden Sie `OMI_LOCAL_API_URL` und `OMI_LOCAL_TOKEN`, um die Desktop-API-Einstellungen des Profils für eine einzelne Ausführung zu überschreiben.
* Verwenden Sie `--verbose` zum Debuggen — protokolliert `METHOD path → status (Ns)` nach stderr ohne stdout zu beeinflussen, der JSON-Modus bleibt daher gültig.
* Um Inhalt in eine Konversation zu pipen, verwenden Sie `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
