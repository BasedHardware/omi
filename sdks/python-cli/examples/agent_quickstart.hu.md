# omi-cli ágensek számára

> Gyakorlati útmutató LLM-vezérelt rendszerekhez (Claude Code, Cursor, saját botok).

## Miért ágensbarát a parancssori felület (CLI)

* **Stabil JSON-szerződés.** A `--json` érvényes JSON-dokumentumot küld a stdout-ra és
  *kizárólag* JSON-dokumentumot — nincsenek folyamatjelzők vagy animációk. A hibák a
  stderr-re érkeznek `{"error": "...", "detail": "..."}` formátumban.
* **Stabil kilépési kódok.** `0` sikeres / `1` használati hiba / `2` hitelesítési hiba / `3` szerverhiba / `4` sebességkorlátozás / `5` nem található. Az ágensek ezek alapján elágazhatnak anélkül, hogy természetes nyelvű hibaüzeneteket kellene elemezniük.
* **Nincsenek interaktív bekérések háttérkörnyezetben.** Destruktív műveletekhez adja meg a `--yes` (vagy `-y`) kapcsolót; interaktív bejelentkezés kihagyásához adja meg a `--api-key` értéket vagy állítsa be a `OMI_API_KEY` környezeti változót.
* **Elnéző újrapróbálkozási viselkedés.** A `429` és `5xx` kódok esetén visszatartási idővel újrapróbálkozik a hiba felszínre hozása előtt.

## Hitelesítés (egyszeri, ember által végzett)

A felhasználó beszerez egy fejlesztői API-kulcsot az Omi webes alkalmazásból
(`https://app.omi.me` → Developer → API Keys), majd:

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

### 4. Nyitott teendők olvasása

```bash
omi action-item list --json --open
```

### 5. Teendő megjelölése befejezettként

```bash
omi action-item complete --json a1b2c3d4
```

## Helyi Asztali API (Desktop API)

Amikor az Omi Desktop elérhetővé teszi a helyi API-ját, az ágensek lekérdezhetik az eszköz képernyőelőzményeit,
összegzéseit, SQL-adatait és feladatait a felhőalapú API használata nélkül:

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

Csak akkor jelöljön meg készként vagy töröljön feladatokat, ha a felhasználó kifejezetten kéri:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

Az `omi local screenshot SCREENSHOT_ID --output PATH` parancs lemezre írja a képernyőképet,
és továbbra is JSON-t ír a stdout-ra a szkriptek számára. A képernyőkép azonosítója általában a
`local search-screen` parancsból vagy a `screenshots` táblán végzett SQL-lekérdezésből származik.
Ha a Desktop strukturált hibát ad vissza, mint például `screenshot_pending`, `screenshot_file_missing`,
vagy `screenshot_chunk_corrupted`, a JSON-mód megőrzi a `reason`, `hint` és `screenshot_id` mezőket
a stderr-en, így az ágensek megpróbálhatnak egy régebbi azonosítót vagy jelenthetik a pontos akadályt.
Érvényesítse a sikeres kimeneteket a `file PATH` paranccsal, mielőtt átadná azokat a vizuális eszközöknek.

## Részletes példa: Python ágens hurok

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Meghívja az omi CLI-t JSON módban, kivételt dobva nem sikeres hibakódok esetén."""
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
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Beolvassa az összes nyitott teendőt, és készként jelöl minden 30 napnál régebbit.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Sebességkorlátozások (rate limits) kezelése

Emlékek: 120/óra. Beszélgetések: 25/óra. Kötegelt létrehozások: 15/óra.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # sebességkorlátozás
    err = json.loads(result.stderr)
    # az err["detail"] így néz ki: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Tippek

* Használja a `--profile <név>` kapcsolót, ha ágense több Omi-fiókot kezel. Minden
  profil saját hitelesítő adatokkal és API-címmel rendelkezik.
* Helyi háttérrendszer teszteléséhez használja a `--api-base http://localhost:8080` beállítást.
* Használja az `OMI_LOCAL_API_URL` és `OMI_LOCAL_TOKEN` változókat a profil helyi
  Desktop API beállításainak felülbírálásához egyetlen futtatás erejéig.
* Hibakereséshez használja a `--verbose` opciót — ez a `METHOD path → status (Ns)` sort a stderr-re írja
  anélkül, hogy befolyásolná a stdout-ot, így a JSON-mód érvényes marad.
* Tartalom beszélgetésbe történő átirányításához (pipe) használja a `--text -` kapcsolót:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
