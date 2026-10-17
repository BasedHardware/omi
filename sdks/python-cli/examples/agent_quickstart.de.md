# omi-cli für Agenten

> Praktischer Leitfaden für LLM-gesteuerte Harnesses (Claude Code, Cursor, eigene Bots).

## Warum die CLI agentenfreundlich ist

* **Stabiler JSON-Vertrag.** `--json` gibt ein gültiges JSON-Dokument auf stdout aus und *nur* ein JSON-Dokument — keine Fortschrittsanzeigen, keine Spinner. Fehler gehen als `{"error": "...", "detail": "..."}` an stderr.
* **Stabile Exit-Codes.** `0` ok / `1` Nutzung / `2` Auth / `3` Server / `4` rate limited / `5` nicht gefunden. Agenten können darauf verzweigen, ohne Fehlermeldungen in natürlicher Sprache zu parsen.
* **Keine interaktiven Abfragen in headless Kontexten.** `--yes` (oder `-y`) an destruktive Befehle übergeben; `--api-key` übergeben oder `OMI_API_KEY` setzen, um interaktive Anmeldung zu überspringen.
* **Nachsichtiges Wiederholungsverhalten.** `429` und `5xx` werden mit Backoff wiederholt, bevor sie auftauchen.

## Authentifizierung (einmalig, durch den Menschen)

Der Nutzer holt einen Dev-API-Key aus der Omi-Web-App
(`https://app.omi.me` → Developer → API Keys) und entweder:

```bash
omi auth login                          # interaktives Einfügen; Key nicht in Shell-History
# # oder
export OMI_API_KEY=omi_dev_...          # kurzlebig, container-tauglich
```

## Die fünf häufigsten Agentenaufgaben

### 1. Memories lesen

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Eine Memory erstellen

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Conversations lesen

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Offene Action Items lesen

```bash
omi action-item list --json --open
```

### 5. Action Item als erledigt markieren

```bash
omi action-item complete --json a1b2c3d4
```

## Lokale Desktop-API

Wenn Omi Desktop seine lokale API bereitstellt, können Agenten gerätelokale
Screen-History, Recaps, SQL und Tasks abfragen — ohne die Cloud-Dev-API:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# # oder, für kurzlebige Sitzungen:
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

Tasks nur abschließen oder löschen, wenn der Nutzer klar darum bittet:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` schreibt den Screenshot
auf die Platte und gibt weiterhin JSON auf stdout aus. Die Screenshot-ID kommt
gewöhnlich aus `local search-screen` oder SQL über die `screenshots`-Tabelle.
Liefert Desktop einen strukturierten Fehler wie `screenshot_pending`,
`screenshot_file_missing` oder `screenshot_chunk_corrupted`, bewahrt der
JSON-Modus die Felder `reason`, `hint` und `screenshot_id` auf stderr — so
können Agenten eine ältere ID erneut versuchen oder den genauen Blocker melden.
Erfolgreiche Ausgaben vor Übergabe an Vision-Tools mit `file PATH` prüfen.

## Praxisbeispiel: Python-Agentenschleife

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

# Alle offenen Action Items lesen und alles älter als 30 Tage abschließen.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Umgang mit Rate-Limits

Memories: 120/Std. Conversations: 25/Std. Batch-Erstellung: 15/Std.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] sieht so aus: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Tipps

* `--profile <name>` nutzen, wenn der Agent mehrere Omi-Konten jongliert. Jedes
  Profil hat eigene Credentials und API-Basis.
* `--api-base http://localhost:8080` für lokale Backend-Tests nutzen.
* `OMI_LOCAL_API_URL` und `OMI_LOCAL_TOKEN` nutzen, um profillokale
  Desktop-API-Einstellungen für einen Lauf zu überschreiben.
* `--verbose` zum Debuggen nutzen — es loggt `METHOD path → status (Ns)` auf
  stderr, ohne stdout zu beeinflussen; der JSON-Modus bleibt gültig.
* Um Inhalte in eine Conversation zu pipen, `--text -` nutzen:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
