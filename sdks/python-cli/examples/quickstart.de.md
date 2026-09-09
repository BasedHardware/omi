# omi-cli Deutsches Schnellstart-Handbuch (Quickstart Guide)

> Praktischer Leitfaden zur Interaktion mit Omi über das Terminal — konzipiert für Entwickler und autonome KI-Agenten.

`omi-cli` ist die offizielle Befehlszeilenschnittstelle zur [Omi](https://omi.me) Entwickler-API. Es ermöglicht die strukturierte, automatisierbare Verwaltung der Kernressourcen von Omi: Erinnerungen (Memories), Konversationen (Conversations), Aufgaben (Action Items) und Ziele (Goals).

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Offizielle Dokumentation:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Quellcode:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Installation

Die empfohlene Installationsmethode ist `pipx`, da es die Abhängigkeiten in einer isolierten Umgebung verwaltet:

```bash
# Empfohlen: Installation mit pipx
pipx install omi-cli

# Alternativ: Installation mit pip
pip install omi-cli
```

> **Wichtig: Paketname vs. Befehlsname**
> * Der Name des installierten Python-Pakets lautet **`omi-cli`** (das separate Paket `omi` ist nicht zugehörig).
> * Der ausführbare Befehl im Terminal lautet schlicht **`omi`**.

Überprüfen Sie die erfolgreiche Installation:

```bash
omi --version
omi --help
```

---

## 2. Authentifizierung (Authentication)

`omi-cli` unterstützt zwei Authentifizierungsmethoden:

| Authentifizierungsmethode | Typischer Anwendungsfall | Beispielbefehl |
| :--- | :--- | :--- |
| **Entwickler-API-Schlüssel (`omi_dev_*`)** | CI/CD, Hintergrundskripte, autonome KI-Agenten | `omi auth login --api-key ...` oder `OMI_API_KEY` |
| **Browser OAuth (Google/Apple)** | Lokale Workstations, interaktive Nutzung | `omi auth login --browser` (Google) / `--provider apple` |

### Interaktiver Login
Wird der Befehl ohne Optionen ausgeführt, erscheint ein Auswahldialog:

```bash
omi auth login
# 1) Browser — Anmeldung über Google (oder `--provider apple` für Apple) im Webbrowser
# 2) API key — Entwickler-API-Schlüssel von app.omi.me einfügen
```

### Direkter Browser-Login
```bash
# Standard-Login über Google
omi auth login --browser

# Alternativ über Apple
omi auth login --browser --provider apple
```

### Verwendung eines Entwickler-API-Schlüssels
Erstellen Sie einen Entwicklerschlüssel auf [app.omi.me](https://app.omi.me) unter **Developer → API Keys**:

```bash
# Über den Befehl konfigurieren
omi auth login --api-key omi_dev_...

# Oder als Umgebungsvariable setzen (ideal für Container & CI/CD)
export OMI_API_KEY="omi_dev_..."
```

### Überprüfung des Authentifizierungsstatus
* `omi auth status`: Zeigt das aktive lokale Profil und maskierte Anmeldeinformationen an; das Ablaufdatum wird nur bei OAuth-Profilen ausgewiesen (funktioniert offline).
* `omi auth whoami`: Sendet eine Verifizierungsanfrage an den Omi-Server zur Bestätigung der Gültigkeit (erfordert Netzwerkverbindung).

```bash
omi auth status
omi auth whoami
```

Zur Abmeldung:
```bash
omi auth logout
```

---

## 3. Grundlegende Befehle

Verwalten Sie die vier Hauptressourcen von Omi:

### Erinnerungen (Memories)
Fakten, Notizen und Kontext, den das System über Sie erfasst hat:

```bash
# Liste der gespeicherten Erinnerungen abrufen
omi memory list

# Neue Erinnerung erstellen
omi memory create "Bevorzugt TypeScript und Python für Backend-Dienste" --category work

# Spezifische Erinnerung anhand der ID abrufen
omi memory get <MEMORY_ID>
```

### Konversationen (Conversations)
Aufgezeichnete und transkribierte Audio- oder Text-Gespräche:

```bash
# Die letzten 5 Konversationen auflisten
omi conversation list --limit 5

# Konversation inklusive vollständigem Transkript anzeigen
omi conversation get <CONVERSATION_ID> --include-transcript
```

### Aufgaben (Action Items)
Automatisch aus Konversationen extrahierte Aufgaben und To-dos:

```bash
# Offene Aufgaben auflisten
omi action-item list --open

# Aufgabe als erledigt markieren
omi action-item complete <ACTION_ITEM_ID>
```

### Ziele (Goals)
Fortschritts- und Leistungskennzahlen verfolgen:

```bash
# Aktive Ziele anzeigen
omi goal list

# Neues Ziel anlegen
omi goal create "Täglich 2L Wasser trinken" --type numeric --target 2 --unit liters
```

---

## 4. Automatisierung und JSON-Ausgabe (`--json`)

`omi-cli` ist auf nahtlose Automatisierung ausgelegt. Setzen Sie das Flag `--json` als **globale Option vor den Unterbefehl**, um maschinenlesbare JSON-Daten zu erhalten:

```bash
# Erinnerungen im JSON-Format abrufen und mit jq filtern
omi --json memory list | jq '.[] | {id, content, category}'

# Titel der neuesten Konversationen extrahieren
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# Offene Aufgaben als JSON abrufen
omi --json action-item list --open | jq '.'
```

> **Wichtiger Hinweis zur Platzierung:**
> Das Flag `--json` muss **vor** dem jeweiligen Ressourcen-Unterbefehl stehen:
> * Richtig: `omi --json memory list`
> * Falsch: `omi memory list --json`

---

## 5. Exit-Codes für CI/CD und Skripte

Zur zuverlässigen Fehlerbehandlung gibt `omi-cli` standardisierte Exit-Codes zurück:

| Exit-Code | Bedeutung | Beschreibung |
| :---: | :--- | :--- |
| `0` | **Erfolg (Success)** | Der Befehl wurde fehlerfrei ausgeführt. |
| `1` | **Nutzungsfehler (Validierungsfehler)** | Ungültige Werte oder Anwendungsvalidierung; Click-Syntaxfehler wie fehlende Pflichtparameter oder unbekannte Optionen verwenden Exit-Code `2`. |
| `2` | **Authentifizierungsfehler (Auth Error)** | Fehlende Anmeldung, abgelaufenes Token oder ungültiger API-Schlüssel; Click-Syntaxfehler können ebenfalls diesen Code zurückgeben. |
| `3` | **Server-/Netzwerkfehler (Server Error)** | HTTP 5xx Fehler, Verbindungstimeout oder nicht erreichbarer Server. |
| `4` | **Ratenbegrenzung (Rate Limited)** | HTTP 429 Too Many Requests — Wiederholungslogik erforderlich. |
| `5` | **Nicht gefunden (Not Found)** | HTTP 404 Not Found — angeforderte ID existiert nicht. |

---

## 6. Plattformspezifische Shell-Beispiele

### Bash / Zsh (Linux / macOS)
```bash
# API-Schlüssel setzen
export OMI_API_KEY="omi_dev_your_actual_key_here"

# Liste abrufen und Exit-Code prüfen
omi --json memory list --limit 10
if [ $? -ne 0 ]; then
    echo "Fehler beim Abrufen der Erinnerungen!" >&2
fi
```

### PowerShell (Windows)
```powershell
# API-Schlüssel in PowerShell setzen
$env:OMI_API_KEY = "omi_dev_your_actual_key_here"

# JSON-Objekte direkt in PowerShell-Objekte umwandeln
$memories = omi --json memory list | ConvertFrom-Json
$memories | Select-Object id, content, category

# Überprüfung des Exit-Codes
if ($LASTEXITCODE -ne 0) {
    Write-Error "Omi CLI Aufruf fehlgeschlagen mit Code $LASTEXITCODE"
}
```

---

## 7. Lokale Desktop-API Integration

Wenn die Omi Desktop App lokal ausgeführt wird, kann die CLI direkt über das lokale Netzwerk mit ihr kommunizieren:

```bash
# Lokale Verbindung konfigurieren
omi local configure --url http://127.0.0.1:47778 --token IHR_DESKTOP_TOKEN

# Verbindungsstatus prüfen
omi --json local status

# Lokale Bildschirmhistorie durchsuchen
omi --json local search-screen "Projektbericht" --days 7 --app Safari
```

---

## 8. Profilverwaltung (Profiles)

Für mehrere Benutzerkonten oder Umgebungen (z. B. Entwicklung und Produktion) unterstützt die CLI benannte Profile. Die Konfiguration wird unter `~/.omi/config.toml` abgelegt:

```bash
# Profil 'personal' anlegen und anmelden
omi --profile personal auth login

# Profil 'work' anlegen und anmelden
omi --profile work auth login

# Befehl für ein spezifisches Profil ausführen
omi --profile work memory list
```

---

## 9. Sicherheitshinweise

* **Geheimhaltung von API-Schlüsseln:** Hinterlegen Sie Entwickler-API-Schlüssel niemals im Git-Repository. Nutzen Sie `.env`-Dateien oder Secret-Manager.
* **Shell-Historie:** Vermeiden Sie das Übergeben sensibler Schlüssel direkt als Befehlszeilenparameter. Bevorzugen Sie die Umgebungsvariable `OMI_API_KEY` oder den interaktiven Modus.
* **Schlüsselwiderruf:** Sollte ein Schlüssel kompromittiert worden sein, widerrufen Sie ihn umgehend im Dashboard unter [app.omi.me](https://app.omi.me).
