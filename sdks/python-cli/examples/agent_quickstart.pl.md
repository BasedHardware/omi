# omi-cli dla agentów

> Praktyczny przewodnik dla środowisk opartych na LLM (Claude Code, Cursor, własne boty).

## Dlaczego CLI jest przyjazne dla agentów

* **Stabilny kontrakt JSON.** Opcja `--json` wysyła na stdout prawidłowy dokument JSON i *wyłącznie* dokument JSON — żadnych komunikatów o postępie, żadnych animacji ładowania (spinnerów). Błędy trafiają na stderr w formacie `{"error": "...", "detail": "..."}`.
* **Stabilne kody wyjścia.** `0` sukces / `1` błąd składni/użycia / `2` błąd uwierzytelnienia / `3` błąd serwera / `4` przekroczenie limitu zapytań (rate limited) / `5` nie znaleziono. Agenci mogą rozgałęziać logikę na podstawie tych kodów bez konieczności parsowania błędów w języku naturalnym.
* **Brak interaktywnych monitów w środowiskach headless.** Dodaj `--yes` (lub `-y`) do poleceń destrukcyjnych; przekaż `--api-key` lub ustaw zmienną środowiskową `OMI_API_KEY`, aby pominąć interaktywne logowanie.
* **Elastyczna obsługa ponownych prób.** Błędy `429` i `5xx` są automatycznie ponawiane z wykładniczym opóźnieniem (exponential backoff) przed ich zgłoszeniem.

## Uwierzytelnianie (jednorazowo, przez człowieka)

Użytkownik pobiera klucz API programisty z aplikacji internetowej Omi (`https://app.omi.me` → Developer → API Keys) i wybiera jedną z opcji:

```bash
omi auth login                          # interaktywne wklejenie; klucz nie trafia do historii powłoki
# lub
export OMI_API_KEY=omi_dev_...          # sesja tymczasowa, wygodna w kontenerach
```

## Pięć najczęstszych operacji wykonywanych przez agentów

### 1. Odczyt wspomnień

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Tworzenie wspomnienia

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Odczyt konwersacji

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Odczyt otwartych zadań

```bash
omi action-item list --json --open
```

### 5. Oznaczanie zadania jako ukończonego

```bash
omi action-item complete --json a1b2c3d4
```

## Lokalne API Desktop

Gdy Omi Desktop udostępnia swoje lokalne API, agenci mogą odpytywać historię ekranu na urządzeniu, podsumowania, SQL oraz zadania bez korzystania z chmurowego API deweloperskiego:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# lub w przypadku sesji tymczasowych:
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

Zadania należy kończyć lub usuwać tylko wtedy, gdy użytkownik wyraźnie o to poprosi:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

Polecenie `omi local screenshot SCREENSHOT_ID --output PATH` zapisuje zrzut ekranu na dysku i nadal wypisuje JSON na stdout dla skryptów. Identyfikator zrzutu ekranu zazwyczaj pochodzi z `local search-screen` lub zapytania SQL do tabeli `screenshots`. Jeśli Desktop zwróci ustrukturyzowany błąd (taki jak `screenshot_pending`, `screenshot_file_missing` lub `screenshot_chunk_corrupted`), tryb JSON zachowuje pola `reason`, `hint` i `screenshot_id` na stderr, umożliwiając agentom ponowienie próby ze starszym ID lub zgłoszenie dokładnej przyczyny blokady. Przed przekazaniem plików wyjściowych do narzędzi wizyjnych zweryfikuj je za pomocą `file PATH`.

## Praktyczny przykład: pętla agenta w Pythonie

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Wywołuje omi CLI w trybie JSON, zgłaszając wyjątek w przypadku niezerowego kodu wyjścia."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # W trybie JSON CLI wypisuje ustrukturyzowane błędy na stderr:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Odczytuje wszystkie otwarte zadania i oznacza jako ukończone te starsze niż 30 dni.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Obsługa limitów zapytań

Wspomnienia: 120/godz. Konwersacje: 25/godz. Tworzenie wsadowe: 15/godz.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # osiągnięto limit zapytań
    err = json.loads(result.stderr)
    # err["detail"] ma postać: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Przydatne wskazówki

* Używaj flagi `--profile <name>`, jeśli Twój agent zarządza wieloma kontami Omi. Każdy profil ma własne poświadczenia i bazowy adres API.
* Do lokalnych testów backendu używaj `--api-base http://localhost:8080`.
* Użyj zmiennych `OMI_LOCAL_API_URL` oraz `OMI_LOCAL_TOKEN`, aby nadpisać lokalne ustawienia Desktop API dla pojedynczego uruchomienia.
* Używaj `--verbose` do debugowania — rejestruje `METHOD path → status (Ns)` na stderr bez wpływu na stdout, dzięki czemu tryb JSON pozostaje prawidłowy.
* Aby przesłać treść do konwersacji za pomocą potoku, użyj `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
