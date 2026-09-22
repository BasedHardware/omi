# omi-cli dla agentów

> Praktyczny przewodnik po środowiskach opartych na modelach LLM (Claude Code, Cursor, własne boty).

## Dlaczego CLI jest idealne dla agentów

* **Stabilny kontrakt JSON.** Flaga `--json` wypisuje poprawny dokument JSON na standardowe wyjście `stdout` i
  *wyłącznie* dokument JSON: bez komunikatów o postępie czy wskaźników ładowania. Błędy trafiają do
  `stderr` jako `{"error": "...", "detail": "..."}`.
* **Przewidywalne kody wyjścia.** `0` sukces / `1` błąd użycia / `2` błąd uwierzytelniania / `3` błąd serwera / `4` przekroczenie
  limitu zapytań (rate limit) / `5` nie znaleziono. Agenci mogą rozgałęziać logikę na podstawie tych kodów bez potrzeby parsowania
  komunikatów w języku naturalnym.
* **Brak monitów interaktywnych w trybie headless.** Przekaż `--yes` (lub `-y`) w przypadku
  poleceń destrukcyjnych; przekaż `--api-key` lub ustaw zmienną `OMI_API_KEY`, aby pominąć
  interaktywne logowanie.
* **Odporność na chwilowe awarie.** Błędy `429` i `5xx` są automatycznie ponawiane z wykładniczym opóźnieniem
  przed zwróceniem błędu.

## Uwierzytelnianie (jednorazowe, wykonywane przez człowieka)

Użytkownik pobiera klucz API programisty z aplikacji internetowej Omi
(`https://app.omi.me` → Developer → API Keys) i wykonuje jedną z opcji:

```bash
omi auth login                          # interaktywne wklejenie; klucz nie trafia do historii powłoki
# lub
export OMI_API_KEY=omi_dev_...          # ulotne, idealne dla kontenerów
```

## Pięć najczęstszych akcji dla agentów

### 1. Odczyt wspomnień (memories)

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Tworzenie wspomnienia

```bash
omi memory create --json "Użytkownik preferuje tryb ciemny" --category lifestyle
```

### 3. Odczyt rozmów (conversations)

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Odczyt otwartych zadań (action items)

```bash
omi action-item list --json --open
```

### 5. Oznaczanie zadania jako ukończone

```bash
omi action-item complete --json a1b2c3d4
```

## Lokalne API Desktop

Gdy Omi Desktop udostępnia swoje lokalne API, agenci mogą odpytywać historię
ekranu na urządzeniu, podsumowania, SQL oraz zadania bez korzystania z chmurowego API:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# lub dla sesji tymczasowych:
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

Oznaczaj jako ukończone lub usuwaj zadania tylko wtedy, gdy użytkownik wyraźnie o to poprosi:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

Polecenie `omi local screenshot SCREENSHOT_ID --output PATH` zapisuje zrzut ekranu na dysku i
nadal wypisuje JSON na `stdout` dla skryptów. Identyfikator zrzutu ekranu pochodzi zazwyczaj z
`local search-screen` lub zapytania SQL do tabeli `screenshots`. Jeśli aplikacja Desktop
zwróci błąd strukturalny, taki jak `screenshot_pending`, `screenshot_file_missing`
lub `screenshot_chunk_corrupted`, tryb JSON zachowuje pola `reason`, `hint` oraz
`screenshot_id` w strumieniu `stderr`, umożliwiając agentom ponowienie próby z poprzednim ID lub zgłoszenie
dokładnej przyczyny blokady. Sprawdź poprawność plików wyjściowych za pomocą `file PATH` przed przekazaniem
ich do modeli wizyjnych.

## Praktyczny przykład: pętla agenta w języku Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Wywołuje CLI omi w trybie JSON, zgłaszając wyjątek w przypadku niezerowego kodu wyjścia."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI wypisuje ustrukturyzowane błędy na stderr w trybie JSON:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi zakończyło działanie z kodem {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Odczytuje wszystkie otwarte zadania i oznacza jako zakończone te starsze niż 30 dni.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Obsługa limitów zapytań (rate limits)

Wspomnienia: 120/h. Rozmowy: 25/h. Tworzenie wsadowe: 15/h.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # osiągnięto limit zapytań
    err = json.loads(result.stderr)
    # err["detail"] ma postać: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Porady

* Użyj `--profile <nazwa>`, jeśli twój agent zarządza wieloma kontami Omi. Każdy
  profil przechowuje własne dane uwierzytelniające i bazowy adres API.
* Użyj `--api-base http://localhost:8080` do testowania z lokalnym backendem.
* Użyj `OMI_LOCAL_API_URL` i `OMI_LOCAL_TOKEN`, aby nadpisać konfigurację lokalnego API Desktop
  danego profilu dla pojedynczego uruchomienia.
* Użyj `--verbose` do debugowania: rejestruje `METHOD path status (Ns)` w `stderr`
  bez wpływu na `stdout`, zachowując poprawność strumienia JSON.
* Aby przesłać treść do rozmowy za pomocą potoku (pipe), użyj `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
