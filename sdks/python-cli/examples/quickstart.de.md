# omi-cli — Deutsche Kurzanleitung

`omi-cli` verbindet dein Terminal mit der Entwickler-API von [Omi](https://omi.me).
Du kannst Erinnerungen, Gespräche, Aufgaben und Ziele lesen und bearbeiten.

## 1. Installation

Mit `pipx` bleiben die Abhängigkeiten von anderen Python-Projekten getrennt:

```bash
pipx install omi-cli
# Alternativ:
pip install omi-cli

omi --version
omi --help
```

Das Paket heißt **`omi-cli`**, der installierte Befehl **`omi`**. Das separate
PyPI-Paket `omi` gehört nicht zu diesem CLI. Python 3.10 oder neuer ist erforderlich.

## 2. Anmeldung

```bash
omi auth login
```

Der interaktive Dialog bietet Browser-Anmeldung (Google/Apple) oder einen
Entwickler-API-Key an. Die Eingabe des Keys wird dabei verborgen.
Entwickler-Keys findest du unter **Developer → API Keys** auf
[app.omi.me](https://app.omi.me).

Für die direkte Browser-Anmeldung:

```bash
omi auth login --browser
```

Für Skripte und CI kannst du `OMI_API_KEY` verwenden (siehe Abschnitt 6).
`omi auth login --api-key omi_dev_...` speichert einen Key im gewählten Profil;
verwende in einem gemeinsam genutzten Terminal lieber die interaktive Eingabe,
damit der Key nicht im Befehlsverlauf steht.

```bash
omi auth status    # Lokale Konfiguration prüfen; kein Serveraufruf
omi auth whoami    # Anmeldung beim Server überprüfen; benötigt Netzwerk
omi auth refresh   # Nur für Browser-/OAuth-Anmeldungen
omi auth logout    # Im aktuellen Profil abmelden
```

`auth refresh` erneuert einen OAuth-Token. Bei API-Key-Anmeldung gibt es keinen
solchen Token; der Befehl endet dann mit einem Anwendungsfehler (Exit-Code `1`).

## 3. Die wichtigsten Befehle

```bash
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open --limit 5
omi goal list --limit 5
```

Weitere Beispiele; ersetze die IDs durch Werte aus deinem eigenen Konto:

```bash
omi memory get MEMORY_ID
omi conversation get CONVERSATION_ID --include-transcript
omi goal history GOAL_ID
```

Diese Befehle verändern Daten:

```bash
omi memory create "Bevorzugt das dunkle Design" --category lifestyle
omi action-item complete ACTION_ITEM_ID
omi goal progress GOAL_ID 25
```

`goal progress` braucht sowohl die Ziel-ID als auch den neuen Fortschrittswert.
Eine Frage zu deinen Gesprächen stellst du mit:

```bash
omi ask "Was habe ich gestern zum Projekt entschieden?"
```

## 4. JSON für Skripte

Globale Optionen stehen **vor** dem Unterbefehl:

```bash
omi --json memory list --limit 5 | jq '.[] | {id, content}'
```

In Python prüfst du den Exit-Code, bevor du die Ausgabe einliest:

```python
import json
import subprocess

result = subprocess.run(
    ["omi", "--json", "memory", "list", "--limit", "5"],
    check=True,
    capture_output=True,
    text=True,
)
for memory in json.loads(result.stdout):
    print(memory["id"], memory.get("content", "")[:80])
```

## 5. Exit-Codes

| Code | Bedeutung | Typische Ursache |
| --- | --- | --- |
| `0` | Erfolg | Befehl abgeschlossen |
| `1` | Anwendungs- oder Validierungsfehler | Ungültige Eingabe, ungeeignete Authentifizierungsmethode für `auth refresh` |
| `2` | Authentifizierungsfehler | Fehlende Zugangsdaten, abgelaufener Token oder fehlende Berechtigung |
| `3` | Server- oder Verbindungsfehler | HTTP 5xx, Zeitüberschreitung oder Verbindungsfehler |
| `4` | Anfragelimit erreicht | HTTP 429; vor dem nächsten Versuch warten |
| `5` | Nicht gefunden | HTTP 404; Ressourcen-ID überprüfen |

Unbekannte Optionen und fehlende Pflichtargumente werden bereits von Click
abgefangen und liefern ebenfalls `2`. Dieser Code bedeutet daher nicht in
jedem Fall, dass eine erneute Anmeldung nötig ist; lies auch die Fehlermeldung.

## 6. Umgebungsvariablen

In Bash/Zsh kannst du den Key ohne sichtbare Eingabe oder Klartext im
Befehlsverlauf für die aktuelle Sitzung setzen:

```bash
read -r -s OMI_API_KEY
export OMI_API_KEY
omi --json memory list --limit 5
unset OMI_API_KEY
```

In PowerShell kann ein CI-System `OMI_API_KEY` als geheime Umgebungsvariable
bereitstellen. Die JSON-Ausgabe lässt sich so weiterverarbeiten:

```powershell
(omi --json memory list --limit 5 | ConvertFrom-Json) | Select-Object id, content
```

| Variable | Zweck |
| --- | --- |
| `OMI_API_KEY` | Entwickler-Key als Ersatz, wenn im Profil kein API-Key gespeichert ist |
| `OMI_PROFILE` | Profil auswählen, sofern `--profile` nicht gesetzt ist |
| `OMI_CONFIG` | Alternativer Pfad zur Konfigurationsdatei |
| `OMI_API_BASE` | Basis-URL der Cloud-API überschreiben |
| `OMI_LOCAL_API_URL` | URL der lokalen Desktop-API überschreiben |
| `OMI_LOCAL_TOKEN` | Token der lokalen Desktop-API überschreiben |

Ein bereits gespeicherter API-Key hat Vorrang vor `OMI_API_KEY`.
Fehlt dieser gespeicherte Key, stellt `OMI_API_KEY` das Profil für den Aufruf
auf API-Key-Anmeldung um — auch bei zuvor gewählter OAuth-Anmeldung. Entferne
die Variable mit `unset OMI_API_KEY`, wenn du die gespeicherte Browser-Anmeldung
verwenden möchtest.

## 7. Profile

Die Konfiguration liegt standardmäßig in `~/.omi/config.toml`.
Mit Profilen trennst du Konten und Umgebungen:

```bash
omi --profile personal auth login
omi --profile work auth login
omi --profile work memory list --limit 5
omi config show
omi config path
```

Für die Profilauswahl gilt: **`--profile` / `-p` → `OMI_PROFILE` →
`active_profile` in der Konfiguration → `default`**, falls kein aktives Profil
konfiguriert ist. Die globale Option gehört vor den Unterbefehl.

```bash
export OMI_PROFILE=work
omi memory list --limit 5
omi --profile personal memory list --limit 5  # Überschreibt OMI_PROFILE
unset OMI_PROFILE
```

## 8. Lokale Desktop-API

Dieser Bereich setzt eine laufende Omi-Desktop-App mit aktivierter lokaler API
voraus. Cloud-Zugangsdaten ersetzen den lokalen API-Token nicht.
Ersetze `DEIN_LOKALER_TOKEN` durch den Token deiner Desktop-App:

```bash
omi local configure --url http://127.0.0.1:47778 --token DEIN_LOKALER_TOKEN
omi --json local status
omi --json local tools
```

`local configure` speichert URL und Token im aktuellen Profil.
`local status` prüft die konfigurierte Desktop-API; anders als `auth status`
ist es daher nicht nur eine lokale Konfigurationsanzeige.
Prüfe mit `local tools`, welche Werkzeuge deine App bereitstellt, bevor du sie aufrufst:

```bash
omi --json local search-screen "Projektplanung" --days 7 --app Safari
omi local screenshot 123 --output ./omi-shot.jpg
omi --json local sql "SELECT appName, COUNT(*) FROM screenshots GROUP BY appName"
```

Bildschirmverlauf und Screenshots können persönliche Informationen enthalten.
Verwende eine tatsächliche Screenshot-ID aus deinen Ergebnissen und teile die
Ausgabe nur, wenn du sie geprüft hast.

## Weiterführende Informationen

- [Agent-Kurzanleitung](./agent_quickstart.md)
- [Shell-Beispiele](./shell_examples.sh)
- [Vollständige CLI-Dokumentation](https://docs.omi.me/doc/developer/cli/introduction)
- `omi --help` und `omi COMMAND --help` für die installierte Version
