# omi-cli Schnellstartanleitung (Deutsch)

> Praktische Anleitung zur Interaktion mit Omi über das Terminal. Geeignet für Menschen und KI-Agenten.

`omi-cli` ist die offizielle Kommandozeilenschnittstelle für die Interaktion mit den Entwickler-APIs von [Omi](https://omi.me). Sie verarbeitet die vier Kernressourcen von Omi — **Erinnerungen, Gespräche, Aktionselemente und Ziele** — effizient und skriptfähig.

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Offizielle Dokumentation:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Quellcode:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Installation

Die empfohlene Installationsmethode verwendet `pipx`, um Abhängigkeiten zu isolieren.

```bash
# Empfohlen: mit pipx installieren
pipx install omi-cli

# Alternativ: mit pip installieren
pip install omi-cli
```

> **Wichtig: Unterschied zwischen Paketname und Befehlsname**
> * Das installierte Python-Paket heißt **`omi-cli`** (das eigenständige `omi`-Paket ist ein anderes, nicht zusammenhängendes Paket).
> * Der nach der Installation im Terminal ausführbare Befehl heißt **`omi`**.

Überprüfen Sie nach der Installation die Version und die Hilfe.

```bash
omi --version
omi --help
```

---

## 2. Authentifizierung

`omi-cli` unterstützt zwei Authentifizierungsmethoden.

| Methode | Empfohlene Verwendung | Beispielbefehl |
| :--- | :--- | :--- |
| **Entwickler-API-Schlüssel (`omi_dev_*`)** | CI/CD, automatisierte Skripte, KI-Agenten | `omi auth login --api-key ...` oder Umgebungsvariable |
| **Browser-OAuth (Google/Apple)** | Entwickler-PC / Laptop | `omi auth login --browser` |

### Interaktive Anmeldung
Ohne Optionen werden Sie aufgefordert, zwischen Browser-Anmeldung und API-Schlüssel-Eingabe zu wählen.

```bash
omi auth login
# 1) Browser — mit Google- oder Apple-Konto anmelden (für Menschen)
# 2) API key — Entwicklerschlüssel von app.omi.me einfügen (für Agenten/CI)
```

### Direkte Anmeldung über den Browser
```bash
omi auth login --browser
```

### Verwendung des API-Schlüssels
Holen Sie sich den Entwicklerschlüssel unter **Developer → API Keys** auf [app.omi.me](https://app.omi.me) und richten Sie ihn ein.

```bash
# Über Befehl einrichten
omi auth login --api-key omi_dev_...

# Oder über Umgebungsvariable (ideal für CI/CD oder Container)
export OMI_API_KEY=omi_dev_...
```

### Authentifizierungsstatus überprüfen
* `omi auth status`: zeigt das lokale Profil, das maskierte Token und das Ablaufdatum an (funktioniert offline).
* `omi auth whoami`: sendet eine echte Authentifizierungsanfrage an den Omi-Server (erfordert Netzwerkverbindung).

```bash
omi auth status
omi auth whoami
```

Zum Abmelden:
```bash
omi auth logout
```

---

## 3. Grundlegende Verwendung

Sie können die vier Kernressourcen von Omi auflisten und verwalten.

### Erinnerungen (Memories)
Verwalten Sie vom System gelernte Fakten und Erkenntnisse.

```bash
# Alle Erinnerungen auflisten
omi memory list

# Neue Erinnerung erstellen
omi memory create "Benutzer bevorzugt den Dunkelmodus" --category lifestyle

# Details einer bestimmten Erinnerung anzeigen
omi memory get <MEMORY_ID>
```

### Gespräche (Conversations)
Audio- oder Textverlauf der Gespräche, die vom tragbaren Gerät oder der App erfasst wurden.

```bash
# Die letzten 5 Gespräche abrufen
omi conversation list --limit 5

# Gesprächsdetails und Transkript anzeigen
omi conversation get <CONVERSATION_ID> --include-transcript
```

### Aktionselemente (Action Items)
Aufgaben oder Follow-up-Elemente, die automatisch aus Gesprächen extrahiert wurden.

```bash
# Nur offene Aktionselemente auflisten
omi action-item list --open

# Aktionselement als erledigt markieren
omi action-item complete <ACTION_ITEM_ID>
```

### Ziele (Goals)
Verwalten Sie Ziele, deren Fortschritt verfolgt wird.

```bash
# Alle Ziele auflisten
omi goal list
```

---

## 4. Skriptverarbeitung und JSON-Ausgabe (`--json`)

`omi-cli` unterstützt nativ die JSON-Ausgabe. In Kombination mit `jq` oder Python-Skripten muss die **globale Option** `--json` vor dem Unterbefehl stehen.

```bash
# Erinnerungsliste als JSON abrufen und ID und Inhalt extrahieren
omi --json memory list | jq '.[] | {id, content, category}'

# Titel der letzten 5 Gespräche abrufen
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# Offene Aktionselemente auflisten
omi --json action-item list --open | jq '.[] | {id, description, due_at}'

# Ziele auflisten
omi --json goal list | jq '.[] | {id, title, current: .current_value, target: .target_value}'
```

---

## 5. Sitzungsdiagnose

Verwenden Sie diese beiden Befehle paarweise zur schnellen Fehlerbehebung.

```bash
# 1) Zuerst lokale Konfiguration prüfen
omi auth status

# 2) Beim Omi-Server bestätigen
omi auth whoami

# 3) Falls nötig, Anmeldung neu starten
omi auth login
```

---

## 6. Best Practices

* **Verwenden Sie `--json` in Skripten:** Vermeiden Sie das Parsen von Freitext; verlassen Sie sich immer auf strukturierte JSON-Ausgabe.
* **Isolieren Sie Umgebungen mit `pipx`:** Vermeidet Abhängigkeitskonflikte mit anderen Python-Paketen.
* **Geben Sie API-Schlüssel nicht weiter:** `omi_dev_*`-Schlüssel gewähren vollen Kontozugriff — speichern Sie sie in einem Secret-Manager oder in Umgebungsvariablen.
* **Melden Sie sich auf gemeinsam genutzten Geräten ab:** Verwenden Sie `omi auth logout` nach Sitzungen auf gemeinsamen Maschinen.

---

## 7. Fehlerbehebung

| Symptom | Wahrscheinliche Ursache | Lösung |
| :--- | :--- | :--- |
| `command not found: omi` | PATH enthält das pipx-bin-Verzeichnis nicht | `pipx ensurepath` ausführen und Terminal neu starten |
| `401 Unauthorized` | API-Schlüssel ungültig oder abgelaufen | Neuen Schlüssel auf app.omi.me generieren und aktualisieren |
| `connection refused` | Kein Netzwerkzugriff auf den Omi-Server | Internetverbindung und Proxy-Einstellungen prüfen |
| `permission denied` auf Konfigurationsdateien | Konfigurationsverzeichnis nicht beschreibbar | Berechtigungen von `~/.omi/config.toml` prüfen |

---

## 8. Schnelllinks

* Quell-Repository: [github.com/BasedHardware/omi](https://github.com/BasedHardware/omi)
* Vollständige Dokumentation: [docs.omi.me](https://docs.omi.me)
* Issues und Support: [github.com/BasedHardware/omi/issues](https://github.com/BasedHardware/omi/issues)
* Discord-Community: Einladung über die Omi-Startseite erhältlich