# omi-cli dlŏ agentōw

> Praktyczny przewodnik dlŏ harnessōw sterowanych bez LLM (Claude Code, Cursor, twoje włŏsne boty).

## Dlŏczego CLI je przijŏzny dlŏ agentōw

* **Stabylny kontrakt JSON.** `--json` wysyłŏ poprawny dokument JSON na stdout i
  *inō* dokument JSON — żŏdnych kōmunikatōw ô postępie, żŏdnych spinnerōw.
  Feler idzie na stderr jako `{"error": "...", "detail": "..."}`.
* **Stabylne kody wyjściŏ.** `0` OK / `1` użycie / `2` autoryzacyjŏ / `3`
  serwer / `4` limit szybkości / `5` niy znŏdzione. Agenty mogōm na tym bazować
  bez parsowaniŏ felerōw w naturalnyj gŏdce.
* **Żŏdnych interaktywnych pytōń w kōntekstach headless.** Podaj `--yes` (abo
  `-y`) do destrukcyjnych kōmandōw; podaj `--api-key` abo ustaw `OMI_API_KEY`,
  coby pōminōńć interaktywne logowanie.
* **Wybaczajōnce zachowanie retry.** `429` i `5xx` sōm prōbowane na nowo z
  backoffym zanim sie pokŏżōm.

## Autoryzacyjŏ (jedyn rŏz, bez człowieka)

Użytkownik dostŏwŏ klucz API dev z aplikacyje web Omi
(`https://app.omi.me` → Developer → API Keys) i potym abo:

```bash
omi auth login                          # interaktywne wklajaniy; klucz niy idzie do historyje shella
# abo
export OMI_API_KEY=omi_dev_...          # efemeryczny, przijŏzny dlŏ kōntenerōw
```

## Piyńć rzeczōw, kere agenty robiōm nojczyńścij

### 1. Czytać pamiyńci

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Stworzić pamiyńć

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Czytać kōnwersacyje

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Czytać ôtwarte pozycyje akcyje

```bash
omi action-item list --json --open
```

### 5. Ôdznaczyć pozycyjõ akcyje jako zrobiōnõ

```bash
omi action-item complete --json a1b2c3d4
```

## Lokalne API Desktop

Kiedy Omi Desktop wystŏwiŏ swojo lokalne API, agenty mogōm pytŏć ô historyjõ
ekranu na urzōndzyniu, podsumowania, SQL i zadania bez użyciŏ chmurowego API
dev:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# abo, dlŏ efemerycznych sesyjōw:
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

Ukończ abo skasuj zadania ino wtedy, kej użytkownik jasno ô to poprosi:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` zapisuje zrzut ekranu na
dysk i wciōnż drukuje JSON na stdout dlŏ skryptōw. ID zrzutu nojczyńścij
pochodzi z `local search-screen` abo z SQL-a po tabeli `screenshots`. Jeźli
Desktop wrōci strukturalny feler taki jak `screenshot_pending`,
`screenshot_file_missing` abo `screenshot_chunk_corrupted`, tryb JSON zachowuje
pola `reason`, `hint` i `screenshot_id` na stderr, tak iże agenty mogōm
sprōbować starszy ID abo zgłosić dokładny bloker. Weryfikuj udane efekty bez
`file PATH` zanim je podŏsz dalij do nŏczyńŏw wizyjnych.

## Przikłŏd: pynla agynta we Pythonie

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Wywołuj CLI omi w trybie JSON, rzucajōnc przi kodach wyjściŏ inkszych niż sukces."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI wypisujŏ strukturalne felery na stderr w trybie JSON:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Czytej wszyske ôtwarte pozycyje akcyje i ôdznaczaj jako zrobiōne te starsze niż 30 dni.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Ôbsługa limitōw szybkości

Pamiyńci: 120/godz. Kōnwersacyje: 25/godz. Wsadowe tworzyniy: 15/godz.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # limit szybkości
    err = json.loads(result.stderr)
    # err["detail"] wyglōndŏ tak: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Rady

* Używej `--profile <name>`, jeźli twōj agent ôbsługuje pora kōnt Omi. Kożdy
  profil mŏ swoja poświadczyniŏ i bazã API.
* Używej `--api-base http://localhost:8080` do testowaniŏ lokalnego backendu.
* Używej `OMI_LOCAL_API_URL` i `OMI_LOCAL_TOKEN`, coby nadpisać lokalne
  ustawiynia Desktop API profilu na jedyn przebiyg.
* Używej `--verbose` do debugowaniŏ — loguje `METHOD path → status (Ns)` na
  stderr bez wpływaniŏ na stdout, tak iże tryb JSON ôstŏwŏ sie poprawny.
* Coby przekazować treść do kōnwersacyje, używej `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
