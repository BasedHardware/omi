# omi-cli ügynököknek

> Gyakorlati útmutató LLM-vezérelt keretrendszerekhez (Claude Code, Cursor, saját botok).

## Miért ügynökbarát a CLI

* **Stabil JSON-szerződés.** A `--json` érvényes JSON-dokumentumot ír a stdout-ra, és
  *csak* JSON-dokumentumot — nincs haladási üzenet, nincs spinner. A hibák a
  stderr-re kerülnek `{"error": "...", "detail": "..."}` alakban.
* **Stabil kilépési kódok.** `0` rendben / `1` használat / `2` hitelesítés / `3` szerver /
  `4` sebességkorlát / `5` nem található. Az ügynökök ezekre ágazhatnak anélkül,
  hogy természetes nyelvű hibákat elemeznének.
* **Nincsenek interakciók fej nélküli környezetben.** Adj `--yes` (vagy `-y`)
  kapcsolót a romboló parancsokhoz; add meg az `--api-key` kapcsolót, vagy állítsd be
  az `OMI_API_KEY` környezeti változót az interaktív bejelentkezés kihagyásához.
* **Megbocsátó újrapróbálás.** A `429` és `5xx` visszalépéssel újrapróbálódik, mielőtt
  a hiba megjelenne.

## Hitelesítés (egyszeri, emberi feladat)

A felhasználó fejlesztői API-kulcsot szerez az Omi webalkalmazásból
(`https://app.omi.me` → Developer → API Keys), és az alábbiak egyikét választja:

```bash
omi auth login                          # interactive paste; key not in shell history
# or
export OMI_API_KEY=omi_dev_...          # ephemeral, container-friendly
```

## Az öt dolog, amit az ügynökök a leggyakrabban csinálnak

### 1. Emlékek olvasása

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Emlék létrehozása

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Beszélgetések olvasása

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Nyitott feladatok olvasása

```bash
omi action-item list --json --open
```

### 5. Feladat jelölése készre

```bash
omi action-item complete --json a1b2c3d4
```

## Helyi Desktop API

Ha a Omi Desktop helyi API-t kínál, az ügynökök eszközszintű képernyőelőzményeket,
összefoglalókat, SQL-t és feladatokat kérdezhetnek felhő nélkül:

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

Csak akkor fejezz be vagy törölj feladatot, ha a felhasználó egyértelműen kéri:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

Az `omi local screenshot SCREENSHOT_ID --output PATH` képernyőképet ír a lemezre, és
mindig JSON-t nyom a stdout-ra a scripteknek. A screenshot ID általában a
`local search-screen` parancsból vagy a `screenshots` tábla SQL-lekérdezéséből jön.
Ha a Desktop strukturált hibát ad vissza — például `screenshot_pending`,
`screenshot_file_missing` vagy `screenshot_chunk_corrupted` —, a JSON mód a
`reason`, `hint` és `screenshot_id` mezőket a stderr-en hagyja, hogy az ügynök
régebbi ID-val próbálkozhasson, vagy pontosan jelezze az akadályt. A sikeres
kimenetet a `file PATH` paranccsd ellenőrizd, mielőtt továbbadod vizuális eszközöknek.

## Példa: Python ügynök-ciklus

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

## Sebességkorlátok kezelése

Emlékek: 120/óra. Beszélgetések: 25/óra. Csoportos létrehozás: 15/óra.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Tippek

* Használd a `--profile <név>` kapcsolót, ha az ügynök több Omi-fiókot kezel. Minden
  profilnak saját hitelesítője és API-bázisa van.
* Helyi backend teszteléshez használd az `--api-base http://localhost:8080` kapcsolót.
* Az `OMI_LOCAL_API_URL` és `OMI_LOCAL_TOKEN` egyetlen futásra felülírja a profil
  Desktop API-beállításait.
* Hibakereséshez használd a `--verbose` kapcsolót — a `METHOD path → status (Ns)` sort a
  stderr-re írja, a stdout-ot nem érinti, így a JSON mód érvényes marad.
* Beszélgetésbe szöveg beviteléhez használd a `--text -` kapcsolót:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
