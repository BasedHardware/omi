# omi-cli — deutsche Kurzanleitung

> Mit Omi vom Terminal aus arbeiten. Geeignet für Menschen und KI-Agenten.

`omi-cli` ist die offizielle Kommandozeilenschnittstelle für die Entwickler-API von [Omi](https://omi.me).
Sie bietet schnellen, skriptfreundlichen Zugriff auf die vier wichtigsten Omi-Ressourcen:
Erinnerungen, Unterhaltungen, Aufgaben und Ziele.

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Dokumentation:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Quellcode:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Installation

Empfohlen wird `pipx`. Damit wird das Programm in einer isolierten Umgebung installiert,
sodass die Abhängigkeiten Ihrer Projekte nicht miteinander kollidieren.

```bash
# empfohlen: Installation mit pipx
pipx install omi-cli

# oder mit pip
pip install omi-cli
```

> **Wichtig: Paketname und Befehl unterscheiden sich.**
> * Das installierte Paket heißt **`omi-cli`** (das separate Paket `omi` ist ein anderes Projekt).
> * Nach der Installation verwenden Sie den Befehl **`omi`**.

Installation prüfen:

```bash
omi --version
omi --help
```

---

## 2. Authentifizierung

`omi-cli` unterstützt zwei Anmeldemethoden.

| Methode | Geeignet für | Befehl |
| :--- | :--- | :--- |
| **Entwickler-API-Key (`omi_dev_*`)** | CI/CD, Skripte und KI-Agenten | `omi auth login --api-key ...` oder Umgebungsvariable |
| **Browser-Anmeldung (Google/Apple)** | Persönliche Arbeit am eigenen Rechner | `omi auth login --browser` |

### Interaktive Anmeldung

Ohne Optionen fragt der Befehl, welche Methode Sie verwenden möchten:

```bash
omi auth login
# 1) Browser — mit Google oder Apple anmelden (für Menschen empfohlen)
# 2) API-Key — Entwickler-Key von app.omi.me einfügen (für Agenten und CI empfohlen)
```

Bei der Eingabe eines Keys wird die Eingabe verborgen, damit der Key nicht in der Shell-Historie landet.

### Anmeldung über den Browser

```bash
omi auth login --browser
```

### Anmeldung mit einem Entwickler-Key

Den Key erhalten Sie auf [app.omi.me](https://app.omi.me) unter **Developer → API Keys**.

```bash
# Key in der Konfiguration speichern
omi auth login --api-key omi_dev_...

# oder nur über die Umgebung verwenden — praktisch für CI/CD und Container
export OMI_API_KEY=omi_dev_...
```

`OMI_API_KEY` wird verwendet, wenn im aktiven Profil kein Key gespeichert ist. Wenn das Profil bereits
einen Key enthält, hat der gespeicherte Key Vorrang vor der Umgebungsvariable.

### Anmeldung prüfen

Die folgenden Befehle prüfen unterschiedliche Dinge:

* `omi auth status` — zeigt den **lokal** gespeicherten Zustand: Profil, maskierten Key und Ablaufzeit.
  Dieser Befehl funktioniert ohne Netzwerk.
* `omi auth whoami` — führt eine Anfrage an den **Omi-Server** aus und prüft, ob die Zugangsdaten akzeptiert werden.

```bash
omi auth status    # lokaler, Offline-Status
omi auth whoami    # Prüfung auf der Serverseite
```

Ein fast ablaufendes Token können Sie ohne erneute Anmeldung aktualisieren. `omi auth refresh` gilt
**nur für Browser-/OAuth-Profile**. Für ein Profil mit Entwickler-API-Key (`omi_dev_*`) gibt es kein
OAuth-Token zum Aktualisieren; der Befehl endet mit einem Nutzungsfehler (Code `1`). Rotieren Sie in
diesem Fall den Key in der Omi-Webanwendung.

```bash
omi auth refresh
```

Abmelden und lokal gespeicherte Zugangsdaten löschen:

```bash
omi auth logout
```

---

## 3. Grundlegende Befehle

### Erinnerungen (`memory`)

Erinnerungen enthalten Fakten und Wissen, die Omi über Sie gespeichert hat.

```bash
# Erinnerungen auflisten
omi memory list

# eine Erinnerung anlegen
omi memory create "Der Benutzer bevorzugt das dunkle Design" --category lifestyle

# eine einzelne Erinnerung abrufen
omi memory get <MEMORY_ID>
```

### Unterhaltungen (`conversation`)

Unterhaltungen enthalten erfasste und verarbeitete Audio- oder Textgespräche.

```bash
# die fünf neuesten Unterhaltungen
omi conversation list --limit 5

# eine Unterhaltung mit Transkript abrufen
omi conversation get <CONVERSATION_ID> --include-transcript
```

### Aufgaben (`action-item`)

Aufgaben sind Folgeaktionen, die Omi aus Unterhaltungen abgeleitet hat.

```bash
# nur offene Aufgaben
omi action-item list --open

# eine Aufgabe als erledigt markieren
omi action-item complete <ACTION_ITEM_ID>
```

### Ziele (`goal`)

```bash
# Ziele auflisten
omi goal list

# einen neuen Fortschrittswert speichern (Ziel-ID und Wert sind beide erforderlich)
omi goal progress <GOAL_ID> 25

# Änderungsverlauf anzeigen
omi goal history <GOAL_ID>
```

---

## Fragen in natürlicher Sprache (`ask`)

Mit dem eigenständigen Befehl `ask` können Sie Omi zu Ihren eigenen Unterhaltungen befragen.

```bash
omi ask "Was habe ich zum Thema Umzug entschieden?"
omi --json ask "Welche Aufgaben habe ich für diese Woche versprochen?"
```

---

## 4. JSON und Skripte (`--json`)

`omi-cli` kann maschinenlesbares JSON ausgeben. Die Option `--json` ist global und steht daher
**vor** dem Unterbefehl.

```bash
# IDs, Text und Kategorie der Erinnerungen ausgeben
omi --json memory list | jq '.[] | {id, content, category}'

# Titel der neuesten Unterhaltungen ausgeben
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# offene Aufgaben als JSON ausgeben
omi --json action-item list --open | jq '.'
```

> **Häufiger Fehler:** `--json` kommt vor den Unterbefehl.
> * Richtig: `omi --json memory list`
> * Falsch: `omi memory list --json`

Im JSON-Modus wird auf stdout nur das JSON ausgegeben. Dadurch können Shell-Skripte und Agenten
den Output zuverlässig weiterverarbeiten.

---

## 5. Exit-Codes

Die Exit-Codes sind ein stabiler Vertrag für Skripte und CI:

| Code | Bedeutung | Typischer Fall |
| :---: | :--- | :--- |
| `0` | Erfolg | Der Befehl wurde erfolgreich ausgeführt. |
| `1` | Nutzungsfehler | Ungültige Flags, fehlende Argumente oder Validierungsfehler. |
| `2` | Authentifizierungsfehler | Keine Zugangsdaten, abgelaufenes Token oder fehlende Berechtigung. |
| `3` | Serverfehler | HTTP-5xx-Antwort oder Verbindungsfehler. |
| `4` | Rate-Limit | HTTP 429; später erneut versuchen. |
| `5` | Nicht gefunden | HTTP 404; die angegebene Ressource existiert nicht. |

Beispiel für eine Prüfung in Bash:

```bash
if omi --json auth whoami > /dev/null 2>&1; then
  echo "Die Anmeldung funktioniert."
else
  code=$?
  [ "$code" -eq 2 ] && echo "Bitte erneut anmelden."
  [ "$code" -eq 3 ] && echo "Der Server ist momentan nicht erreichbar."
fi
```

---

## 6. Umgebungsvariablen

### Bash / Zsh (Linux, macOS)

```bash
export OMI_API_KEY="omi_dev_Ihr_Key"

omi --json memory list --limit 10
```

Damit der Key in neuen Sitzungen automatisch gesetzt wird, tragen Sie die Zeile in `~/.bashrc`
oder `~/.zshrc` ein.

### PowerShell (Windows)

```powershell
$env:OMI_API_KEY = "omi_dev_Ihr_Key"

# JSON mit PowerShell verarbeiten
(omi --json memory list | ConvertFrom-Json) | Select-Object id, content
```

Dauerhaft für das Benutzerkonto setzen:

```powershell
[Environment]::SetEnvironmentVariable("OMI_API_KEY", "omi_dev_Ihr_Key", "User")
```

Weitere Umgebungsvariablen:

* `OMI_API_BASE` — überschreibt die API-Basis-URL.
* `OMI_CONFIG` — überschreibt den Pfad zu `~/.omi/config.toml`.
* `OMI_PROFILE` — wählt das aktive Profil, wenn kein `--profile` angegeben ist.
* `OMI_LOCAL_API_URL` und `OMI_LOCAL_TOKEN` — überschreiben die Zugangsdaten für die lokale Desktop-API.

---

## 7. Lokale Omi-Desktop-API

Wenn Omi Desktop läuft, können Sie einen Teil der Daten über die lokale API abrufen, ohne die Cloud
zu verwenden.

```bash
# Adresse und Token der lokalen API hinterlegen
omi local configure --url http://127.0.0.1:47778 --token IHR_TOKEN

# prüfen, ob die lokale API antwortet
omi --json local status

# Bildschirmhistorie durchsuchen
omi --json local search-screen "Preise" --days 7 --app Safari

# Screenshot anhand seiner ID abrufen
omi --json local screenshot 123 --output /tmp/omi-shot.jpg

# verfügbare lokale Werkzeuge anzeigen
omi --json local tools

# ein lokales Werkzeug mit JSON-Argumenten aufrufen
omi --json local call search_screen_history --args-json '{"query":"Preise","days":7}'

# Bildschirmzusammenfassung für den Vortag
omi --json local recap --days-ago 1

# lokale Aufgaben durchsuchen
omi --json local task search "Steuern" --include-completed
```

Empfohlener Ablauf: zuerst `omi --json local status`, dann `omi --json local tools` und erst danach
einen konkreten lokalen Aufruf starten. Für `local`-Befehle können Sie alternativ
`OMI_LOCAL_API_URL` und `OMI_LOCAL_TOKEN` setzen.

---

## 8. Profile

Wenn Sie mehrere Konten oder Umgebungen verwenden, trennen Sie sie mit Profilen. Die Konfiguration
liegt standardmäßig in `~/.omi/config.toml`; der Pfad kann mit `OMI_CONFIG` geändert werden.

```bash
# persönliches Profil verwenden
omi --profile personal auth login

# Arbeitsprofil verwenden
omi --profile work auth login

# Befehl in einem bestimmten Profil ausführen
omi --profile work memory list
```

Das verwendete Profil wird in dieser Reihenfolge bestimmt:

1. `--profile` (oder `-p`) hat die höchste Priorität.
2. Danach wird `OMI_PROFILE` verwendet.
3. Danach folgt das aktive Profil aus `~/.omi/config.toml`.
4. Als letzte Möglichkeit wird das Profil `default` verwendet.

Konfiguration anzeigen und ändern:

```bash
# aktuelle Konfiguration anzeigen
omi config show

# Pfad der Konfigurationsdatei anzeigen
omi config path

# eine Einstellung ändern
omi config set api_base https://api.omi.me
```

---

## 9. Nächste Schritte

* [`agent_quickstart.md`](./agent_quickstart.md) — `omi-cli` mit einem KI-Agenten verbinden.
* [`shell_examples.sh`](./shell_examples.sh) — fertige Shell-Beispiele.
* [Omi-Dokumentation](https://docs.omi.me/doc/developer/cli/introduction) — vollständige Referenz der Befehle.
