# omi-cli Deutsche Kurzanleitung

> Sprich mit Omi vom Terminal aus. Entwickelt fuer Menschen **und** Agenten.

`omi-cli` ist die Befehlszeilenschnittstelle zur [Omi](https://omi.me) Entwickler-API.
Es bietet agentenfreundliche Befehle fuer die vier Hauptressourcen:

* **memories** — Fakten und Erinnerungen
* **conversations** — Erfasste und verarbeitete Unterhaltungen
* **action items** — Aufgaben und Folgeaktionen
* **goals** — Verfolgte Fortschrittsmetriken

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Dokumentation:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)

---

## 1. Installation

Empfohlen mit `pipx` fuer isolierte Installation:

```bash
pipx install omi-cli
# oder
pip install omi-cli
```

> **Hinweis:** Der PyPI-Paketname ist `omi-cli`. Der Befehl heisst `omi`.

Nach der Installation ueberpruefen:

```bash
omi --version
omi --help
```

---

## 2. Authentifizierung

| Methode | Einsatz | Befehl |
| :--- | :--- | :--- |
| **API-Key** (`omi_dev_*`) | CI/CD, Agenten | `omi auth login --api-key ...` |
| **Browser** (Google/Apple) | Persoenlich | `omi auth login --browser` |

### Interaktives Anmelden

```bash
omi auth login
# 1) Browser → Google oder Apple (empfohlen fuer Menschen)
# 2) API key → Entwickler-Key von app.omi.me (empfohlen fuer Agenten/CI)
```

### API-Key

Von [app.omi.me](https://app.omi.me) unter **Developer → API Keys** beziehen.

```bash
omi auth login --api-key omi_dev_...
# oder via Umgebungsvariable
export OMI_API_KEY=omi_dev_...
```

### Status pruefen

```bash
omi auth status    # Lokaler Status
omi auth whoami    # Server-Seite verifizieren
```

---

## 3. Daten lesen

```bash
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open --limit 5
omi goal list --limit 5
```

| Befehl | Beschreibung |
| --- | --- |
| `memory` | Fakten und Erinnerungen |
| `conversation` | Gespraeche |
| `action-item` | Aufgaben |
| `goal` | Ziele |

---

## 4. JSON-Ausgabe fuer Skripte

`--json` ist eine globale Option (vor dem Befehl):

```bash
omi --json memory list --limit 5 | jq '.[] | {id, content}'
```

### In Shell-Skripten

```bash
ids=$(omi --json memory list --limit 5 | jq -r '.[].id')
for id in $ids; do
  echo "Verarbeite Erinnerung: $id"
done
```

### In Python

```python
import subprocess, json
result = subprocess.run(
    ["omi", "--json", "memory", "list", "--limit", "5"],
    capture_output=True, text=True
)
memories = json.loads(result.stdout)
for m in memories:
    print(m["id"], m.get("content", "")[:80])
```

---

## 5. Exit-Codes

| Code | Bedeutung | Aktion |
| --- | --- | --- |
| `0` | Erfolg | — |
| `1` | Allgemeiner Fehler | Fehlermeldung pruefen |
| `2` | Auth-Fehler | `omi auth login` ausfuehren |
| `3` | Netzwerkfehler | Verbindung pruefen |

---

## Weitere Informationen

* Vollstaendige Referenz: `omi --help`
* Dokumentation: [docs.omi.me](https://docs.omi.me/doc/developer/cli/introduction)
* Issues: [GitHub](https://github.com/BasedHardware/omi/issues)

---

*Erstellt von AUTO (AI Agent). Bounty: Issue #13360*
