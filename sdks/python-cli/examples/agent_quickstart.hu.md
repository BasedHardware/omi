# omi-cli ágensek számára

> Gyakorlati útmutató LLM-alapú környezetekhez (Claude Code, Cursor, egyedi botok).

## Miért ágensbarát a CLI

* **Stabil JSON szerződés.** A `--json` kapcsoló érvényes JSON dokumentumot küld a standard kimenetre (stdout), és *és kizárólag* JSON dokumentumot — nincsenek állapotüzenetek, nincsenek töltésjelzők. A hibák a standard hibakimenetre (stderr) érkeznek `{"error": "...", "detail": "..."}` formátumban.
* **Stabil kilépési kódok.** `0` rendben / `1` használati hiba / `2` hitelesítési hiba / `3` szerverhiba / `4` sebességkorlátozás elérve / `5` nem található. Az ágensek ezen kódok alapján végezhetnek elágazásokat a természetes nyelvű hibaüzenetek elemzése nélkül.
* **Nincsenek interaktív kérdések headless környezetben.** Destruktív parancsokhoz adja meg a `--yes` (vagy `-y`) kapcsolót; interaktív bejelentkezés kihagyásához adja meg a `--api-key` kapcsolót vagy állítsa be az `OMI_API_KEY` környezeti változót.
* **Megbocsátó újrapróbálkozási viselkedés.** A `429` és `5xx` kódok automatikusan újrapróbálásra kerülnek exponenciális visszalépéssel (backoff), mielőtt a hiba megjelenne.

## Hitelesítés (egyszeri, ember által végzett)

A felhasználó fejlesztői API kulcsot szerez az Omi webes alkalmazásból
(`https://app.omi.me` → Developer → API Keys), és az alábbiak egyikét futtatja:

```bash
omi auth login                          # interaktív beillesztés; a kulcs nem kerül a shell előzményeibe
# vagy
export OMI_API_KEY=omi_dev_...          # efemer, konténerbarát
```

## Az öt leggyakoribb művelet, amit az ágensek végeznek

### 1. Emlékek olvasása (memories)

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

### 4. Nyitott feladatok olvasása (action items)

```bash
omi action-item list --json --open
```

### 5. Feladat megjelölése készként

```bash
omi action-item complete --json a1b2c3d4
```

## Helyi asztali API (Local Desktop API)

Amikor az Omi Desktop közzéteszi helyi API-ját, az ágensek lekérdezhetik az eszközön lévő képernyőelőzményeket, összefoglalókat, SQL-t és feladatokat a felhőalapú dev API használata nélkül:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# vagy efemer munkamenetek esetén:
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
omi --json local task complete task_1
```
