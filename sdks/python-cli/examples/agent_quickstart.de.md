# omi-cli für Agenten

> Praktischer Leitfaden für LLM-gesteuerte Umgebungen (Claude Code, Cursor, eigene Bots).

## Warum die CLI agentenfreundlich ist

* **Stabiler JSON-Vertrag.** `--json` gibt ein gültiges JSON-Dokument auf stdout aus und
  *ausschließlich* ein JSON-Dokument — keine Fortschrittsmeldungen, keine Spinner. Fehler werden auf
  stderr als `{"error": "...", "detail": "..."}` ausgegeben.
* **Stabile Exit-Codes.** `0` OK / `1` Syntax- oder Verwendungsfehler / `2` Authentifizierungsfehler / `3` Serverfehler / `4` Rate
  Limit erreicht / `5` nicht gefunden. Agenten können anhand dieser Codes verzweigen, ohne Fehlermeldungen
  in natürlicher Sprache analysieren zu müssen.
* **Keine interaktiven Eingabeaufforderungen in Headless-Kontexten.** Übergeben Sie `--yes` (oder `-y`) für
  destruktive Befehle; übergeben Sie `--api-key` oder setzen Sie `OMI_API_KEY`, um
  die interaktive Anmeldung zu überspringen.
* **Tolerantes Wiederholungsverhalten.** Fehler vom Typ `429` und `5xx` werden mit exponentiellem Backoff
  automatisch wiederholt, bevor sie gemeldet werden.

## Authentifizierung (einmalig, durch den Menschen)

Der Benutzer ruft einen Entwickler-API-Schlüssel in der Omi-Web-App ab
(`https://app.omi.me` → Developer → API Keys) und wählt eine der folgenden Optionen:

```bash
omi auth login                          # interaktives Einfügen; Schlüssel erscheint nicht im Shell-Verlauf
# oder
export OMI_API_KEY=omi_dev_...          # flüchtig, containerfreundlich
```

## Die fünf häufigsten Aktionen für Agenten

### 1. Erinnerungen lesen

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Eine Erinnerung erstellen

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Unterhaltungen lesen

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

Wenn Omi Desktop seine lokale API bereitstellt, können Agenten den On-Device-Bildschirmverlauf,
Zusammenfassungen, SQL und Aufgaben abfragen, ohne die Cloud-Entwickler-API zu beanspruchen:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# oder für flüchtige Sitzungen:
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

Erledigen oder löschen Sie Aufgaben nur, wenn der Benutzer dies ausdrücklich anfordert:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` schreibt den Screenshot auf die
Festplatte und gibt für Skripte weiterhin JSON auf stdout aus. Die Screenshot-ID
stammt typischerweise aus `local search-screen` oder SQL-Abfragen über die Tabelle `screenshots`. Wenn Desktop
einen strukturierten Fehler wie `screenshot_pending`, `screenshot_file_missing`
oder `screenshot_chunk_corrupted` zurückgibt, bleiben die Felder `reason`, `hint` und
`screenshot_id` auf stderr erhalten, sodass Agenten eine ältere ID wiederholen oder die
genaue Ursache melden können. Überprüfen Sie erfolgreiche Ausgaben mit `file PATH`, bevor Sie sie
an Vision-Tools übergeben.

## Praxisbeispiel: Python-Agentenschleife

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Ruft die omi-CLI im JSON-Modus auf und wirft bei Fehlschlägen eine Exception."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # Die CLI gibt im JSON-Modus strukturierte Fehler auf stderr aus:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi beendet mit Code {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Alle offenen Aufgaben lesen und alles als erledigt markieren, was älter als 30 Tage ist.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Umgang mit Rate Limits

Erinnerungen: 120/h. Unterhaltungen: 25/h. Batch-Erstellungen: 15/h.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # Rate Limit erreicht
    err = json.loads(result.stderr)
    # err["detail"] sieht aus wie: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Tipps

* Verwenden Sie `--profile <name>`, wenn Ihr Agent mehrere Omi-Konten verwaltet. Jedes
  Profil besitzt eigene Anmeldeinformationen und API-Basen.
* Verwenden Sie `--api-base http://localhost:8080` für Tests mit einem lokalen Backend.
* Verwenden Sie `OMI_LOCAL_API_URL` und `OMI_LOCAL_TOKEN`, um profilbezogene
  Desktop-API-Einstellungen für eine einzelne Ausführung zu überschreiben.
* Verwenden Sie `--verbose` zum Debuggen — es protokolliert `METHOD pfad → status (Ns)` auf stderr,
  ohne stdout zu beeinflussen, sodass der JSON-Modus gültig bleibt.
* Um Inhalte per Pipe in eine Unterhaltung zu leiten, verwenden Sie `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
