# omi-cli dla agentów

> Praktyczny przewodnik po środowiskach opartych na LLM (Claude Code, Cursor, własne boty).

## Dlaczego CLI jest przyjazne dla agentów

* **Stabilny kontrakt JSON.** Opcja `--json` zwraca na stdout poprawny dokument JSON i
  *wyłącznie* dokument JSON — żadnych komunikatów o postępie, żadnych animacji ładowania. Błędy trafiają
  na stderr w formacie `{"error": "...", "detail": "..."}`.
* **Stabilne kody wyjścia.** `0` sukces / `1` błąd użycia / `2` błąd uwierzytelnienia /
  `3` błąd serwera / `4` przekroczenie limitu zapytań / `5` nie znaleziono. Agenci mogą podejmować decyzje
  na podstawie kodów bez analizowania komunikatów w języku naturalnym.
* **Brak interaktywnych monitów w środowiskach bezgłowych (headless).** Przekaż `--yes` (lub `-y`)
  do poleceń niszczących; przekaż `--api-key` lub ustaw `OMI_API_KEY`, aby pominąć logowanie interaktywne.
* **Wybaczające ponawianie zapytań.** Błędy `429` i `5xx` są automatycznie ponawiane
  z wykładniczym opóźnieniem (backoff) przed ich zgłoszeniem.

## Uwierzytelnianie (jednorazowe, wykonywane przez człowieka)

Użytkownik pobiera klucz API dewelopera z aplikacji internetowej Omi
(`https://app.omi.me` → Developer → API Keys), a następnie wybiera jedno z rozwiązań:

```bash
omi auth login                          # interaktywne wklejanie; klucz nie trafia do historii powłoki
# lub
export OMI_API_KEY=omi_dev_...          # tymczasowe, przyjazne dla kontenerów
```

## Pięć najczęstszych operacji wykonywanych przez agentów

### 1. Odczytywanie wspomnień

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Tworzenie wspomnienia

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Odczytywanie konwersacji

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Odczytywanie otwartych zadań (action items)

```bash
omi action-item list --json --open
```

### 5. Oznaczanie zadania jako ukończone

```bash
omi action-item complete --json a1b2c3d4
```

## Lokalne Desktop API

Gdy aplikacja Omi Desktop udostępnia swoje lokalne API, agenci mogą odpytywać historię ekranu,
podsumowania, bazę SQL oraz zadania bezpośrednio na urządzeniu, bez konieczności korzystania z chmurowego dev API:

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

Oznaczaj zadania jako ukończone lub usuwaj je wyłącznie wtedy, gdy użytkownik wyraźnie tego zażąda:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

Polecenie `omi local screenshot SCREENSHOT_ID --output PATH` zapisuje zrzut ekranu na dysku i
wciąż wypisuje JSON na stdout na potrzeby skryptów. Identyfikator zrzutu ekranu pochodzi zazwyczaj
z `local search-screen` lub zapytania SQL do tabeli `screenshots`. Jeśli Desktop zwróci błąd
strukturalny, taki jak `screenshot_pending`, `screenshot_file_missing` lub `screenshot_chunk_corrupted`,
tryb JSON zachowuje pola `reason`, `hint` oraz `screenshot_id` na stderr, umożliwiając agentom ponowienie
próby ze starszym ID lub precyzyjne zaraportowanie problemu. Przed przekazaniem do narzędzi wizyjnych
zweryfikuj poprawność pliku za pomocą `file PATH`.

## Praktyczny przykład: pętla agenta w języku Python

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

## Obsługa limitów zapytań (rate limits)

Wspomnienia: 120/godz. Konwersacje: 25/godz. Tworzenie wsadowe: 15/godz.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Przydatne wskazówki

* Użyj `--profile <nazwa>`, jeśli Twój agent obsługuje wiele kont Omi. Każdy
  profil posiada własne dane uwierzytelniające oraz bazowy adres API.
* Użyj `--api-base http://localhost:8080` do lokalnych testów backendu.
* Użyj `OMI_LOCAL_API_URL` oraz `OMI_LOCAL_TOKEN`, aby nadpisać lokalne ustawienia Desktop API
  dla pojedynczego uruchomienia.
* Użyj `--verbose` do debugowania — rejestruje `METHOD path → status (Ns)` na stderr
  bez wpływu na stdout, dzięki czemu tryb JSON zachowuje pełną poprawność.
* Aby przesłać treść do konwersacji za pomocą potoku, użyj `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
