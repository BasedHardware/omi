# omi-cli AI-ügynökök számára

> Gyakorlati útmutató LLM-vezérelt rendszerekhez (Claude Code, Cursor, saját botok).

## Miért ügynökbarát a CLI

* **Stabil JSON-szerződés.** A `--json` kapcsoló érvényes JSON-dokumentumot küld az stdout-ra és
  *kizárólag* JSON-dokumentumot — folyamatjelző üzenetek és pörgő animációk nélkül. A hibák a
  stderr-re érkeznek `{"error": "...", "detail": "..."}` formátumban.
* **Stabil kilépési kódok.** `0` rendben / `1` használati hiba / `2` hitelesítés / `3` szerverhiba /
  `4` sebességkorlát túllépése / `5` nem található. Az ügynökök ezek alapján közvetlenül elágazhatnak
  a természetes nyelvű hibaüzenetek elemzése nélkül.
* **Nincsenek interaktív bekérések headless környezetben.** Destruktív parancsokhoz adja át a `--yes`
  (vagy `-y`) kapcsolót; adja át a `--api-key` kapcsolót vagy állítsa be az `OMI_API_KEY` változót
  az interaktív bejelentkezés kihagyásához.
* **Elnéző újrapróbálkozási viselkedés.** A `429`-es és `5xx`-es hibákat a rendszer automatikusan
  újrapróbálja várakozási idővel (backoff), mielőtt hibát jelezne.

## Hitelesítés (egyszeri, az ember által)

A felhasználó beszerez egy fejlesztői API-kulcsot az Omi webes alkalmazásból
(`https://app.omi.me` → Developer → API Keys), majd vagy:

```bash
omi auth login                          # interaktív beillesztés; a kulcs nem kerül be a shell előzményeibe
# vagy
export OMI_API_KEY=omi_dev_...          # efemer, konténerbarát
```

## Az öt leggyakoribb ügynökművelet

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

### 4. Nyitott teendők olvasása

```bash
omi action-item list --json --open
```

### 5. Teendő megjelölése befejezettként

```bash
omi action-item complete --json a1b2c3d4
```

## Helyi Desktop API

Amikor az Omi Desktop elérhetővé teszi helyi API-ját, az ügynökök lekérdezhetik az eszközön tárolt
képernyő-előzményeket, összefoglalókat, SQL-adatokat és feladatokat a felhőalapú fejlesztői API nélkül:

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

Csak akkor fejezzen be vagy töröljön feladatokat, ha a felhasználó kifejezetten kéri:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

Az `omi local screenshot SCREENSHOT_ID --output PATH` parancs lemezre menti a képernyőképet,
miközben JSON kimenetet ír az stdout-ra a szkriptek számára. A képernyőkép-azonosító általában
a `local search-screen` parancsból vagy a `screenshots` táblára futtatott SQL lekérdezésből származik.
Ha a Desktop strukturált hibát ad vissza, például `screenshot_pending`, `screenshot_file_missing`
vagy `screenshot_chunk_corrupted`, a JSON mód megőrzi a `reason`, `hint` és `screenshot_id` mezőket
az stderr-en, így az ügynökök megpróbálhatnak egy régebbi azonosítót, vagy jelenthetik a pontos akadályt.
Ellenőrizze a sikeres kimeneteket a `file PATH` paranccsal, mielőtt átadná azokat a képelemző eszközöknek.

## Részletes példa: Python ügynökciklus

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

## Sebességkorlátok kezelése (Rate Limits)

Emlékek: 120/óra. Beszélgetések: 25/óra. Kötegelt létrehozás: 15/óra.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Tippek

* Használja a `--profile <name>` kapcsolót, ha ügynöke több Omi-fiókot kezel. Minden
  profil saját hitelesítő adatokkal és API-bázissal rendelkezik.
* Használja az `--api-base http://localhost:8080` kapcsolót helyi háttérrendszer teszteléséhez.
* Használja az `OMI_LOCAL_API_URL` és `OMI_LOCAL_TOKEN` környezeti változókat a profil helyi
  Desktop API beállításainak felülbírálásához egyetlen futtatás erejéig.
* Hibakereséshez használja a `--verbose` kapcsolót — naplózza a `METHOD path → status (Ns)`
  hívásokat az stderr-re anélkül, hogy befolyásolná az stdout-ot, így a JSON mód érvényes marad.
* Tartalom beszélgetésbe történő csővezetékes továbbításához (piping) használja a `--text -` kapcsolót:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
