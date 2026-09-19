# omi-cli ágenseknek

> Gyakorlati útmutató LLM-vezérelt környezetekhez (Claude Code, Cursor, saját botok).

## Miért ágensbarát a CLI

* **Stabil JSON szerződés.** A `--json` kapcsoló érvényes JSON dokumentumot küld az stdoutra és *kizárólag* JSON dokumentumot — nincsenek folyamatjelző üzenetek vagy töltésjelzők. A hibák a stderr-re kerülnek: `{"error": "...", "detail": "..."}`.
* **Stabil kilépési kódok.** `0` rendben / `1` használati hiba / `2` hitelesítés / `3` szerverhiba / `4` sebességkorlátozás / `5` nem található. Az ágensek e kódok alapján elágazhatnak anélkül, hogy természetes nyelvű hibaüzeneteket kellene értelmezniük.
* **Nincsenek interaktív kérdések felügyelet nélküli környezetben.** Adja át a `--yes` (vagy `-y`) kapcsolót a destruktív parancsokhoz; adja át a `--api-key` kapcsolót vagy állítsa be az `OMI_API_KEY` változót az interaktív bejelentkezés kihagyásához.
* **Toleráns újrapróbálkozási viselkedés.** A `429` és `5xx` hibákat a rendszer automatikusan újrapróbálja exponenciális késleltetéssel a megjelenítés előtt.

## Hitelesítés (egyszeri, az ember által)

A felhasználó beszerez egy fejlesztői API kulcsot az Omi webes alkalmazásból (`https://app.omi.me` → Developer → API Keys), és az alábbiak egyikét futtatja:

```bash
omi auth login                          # interaktív beillesztés; a kulcs nem kerül a shell előzményeibe
# vagy
export OMI_API_KEY=omi_dev_...          # ideiglenes, konténerbarát
```

## Az öt dolog, amit az ágensek leggyakrabban csinálnak

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

### 5. Feladat elvégzettnek jelölése

```bash
omi action-item complete --json a1b2c3d4
```

## Helyi Desktop API

Amikor az Omi Desktop elérhetővé teszi helyi API-ját, az ágensek lekérdezhetik az eszköz képernyőelőzményeit, összefoglalóit, SQL adatait és feladatait a felhős fejlesztői API használata nélkül:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# vagy ideiglenes munkamenetekhez:
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

Csak akkor végezzen el vagy töröljön feladatokat, ha a felhasználó kifejezetten kéri:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

Az `omi local screenshot SCREENSHOT_ID --output PATH` parancs lemezre menti a képernyőképet, miközben továbbra is JSON-t ír az stdoutra a parancsfájlok számára. A képernyőkép azonosítója általában a `local search-screen` parancsból vagy a `screenshots` táblára futtatott SQL lekérdezésből származik. Ha a Desktop strukturált hibát ad vissza, például `screenshot_pending`, `screenshot_file_missing` vagy `screenshot_chunk_corrupted`, a JSON mód megőrzi a `reason`, `hint` és `screenshot_id` mezőket a stderr-en, így az ágensek újrapróbálkozhatnak egy régebbi azonosítóval vagy jelenthetik a pontos akadályt. A képfeldolgozó eszközöknek való átadás előtt ellenőrizze a sikeres kimenetet a `file PATH` paranccsal.

## Gyakorlati példa: Python ágensciklus

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Meghívja az omi CLI-t JSON módban, és kivételt dob sikertelen kilépési kód esetén."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # A CLI strukturált hibákat ír a stderr-re JSON módban:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"az omi a következő kóddal lépett ki {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Beolvassa az összes nyitott feladatot, és a 30 napnál régebbieket elvégzettnek jelöli.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Sebességkorlátozások kezelése

Emlékek: 120/óra. Beszélgetések: 25/óra. Kötegelt létrehozás: 15/óra.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # sebességkorlátozás elérve
    err = json.loads(result.stderr)
    # az err["detail"] így néz ki: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Tippek

* Használja a `--profile <név>` kapcsolót, ha ágense több Omi fiókot kezel. Minden profil saját hitelesítő adatokkal és API alapcímmel rendelkezik.
* Használja a `--api-base http://localhost:8080` kapcsolót helyi backend teszteléshez.
* Használja az `OMI_LOCAL_API_URL` és `OMI_LOCAL_TOKEN` környezeti változókat a Desktop API beállításainak felülbírálásához egyetlen futtatás erejéig.
* Használja a `--verbose` kapcsolót hibakereséshez — a `METHOD path → status (Ns)` információt a stderr-re naplózza anélkül, hogy befolyásolná az stdoutot, így a JSON mód érvényes marad.
* Tartalom beszélgetésbe történő átadásához csővezetéken (pipe) keresztül használja a `--text -` kapcsolót:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
