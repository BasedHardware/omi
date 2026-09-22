# omi-cli dla agentów

> Praktyczny przewodnik dla sterowanych LLM środowisk (Claude Code, Cursor, własne boty).

## Dlaczego CLI jest przyjazne dla agentów

* **Stabilny kontrakt JSON.** `--json` wypisuje poprawny dokument JSON na stdout i
  *tylko* dokument JSON — bez komunikatów postępu, bez spinnerów. Błędy trafiają na
  stderr jako `{"error": "...", "detail": "..."}`.
* **Stabilne kody wyjścia.** `0` OK / `1` użycie / `2` uwierzytelnianie / `3` serwer /
  `4` limit szybkości / `5` nie znaleziono. Agenci mogą się na nich gałęziować bez
  parsowania błędów w języku naturalnym.
* **Brak interaktywnych pytań w trybie bezobsługowym.** Przekaż `--yes` (lub `-y`)
  poleceniom destrukcyjnym; przekaż `--api-key` albo ustaw `OMI_API_KEY`, aby pominąć
  interaktywne logowanie.
* **Wyrozumiałe ponawianie.** `429` i `5xx` są ponawiane z backoffem, zanim błąd
  zostanie zwrócony.

## Uwierzytelnianie (jednorazowo, przez człowieka)

Użytkownik pobiera klucz API deweloperskiego z aplikacji webowej Omi
(`https://app.omi.me` → Developer → API Keys) i wybiera jedną z opcji:

```bash
omi auth login                          # interactive paste; key not in shell history
# or
export OMI_API_KEY=omi_dev_...          # ephemeral, container-friendly
```

## Pięć rzeczy, które agenci robią najczęściej

### 1. Odczyt wspomnień

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Utworzenie wspomnienia

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Odczyt rozmów

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Odczyt otwartych zadań

```bash
omi action-item list --json --open
```

### 5. Oznaczenie zadania jako wykonanego

```bash
omi action-item complete --json a1b2c3d4
```

## Lokalne API Desktopu

Gdy Omi Desktop udostępnia lokalne API, agenci mogą pytać o historię ekranu,
podsumowania, SQL i zadania na urządzeniu, bez chmury i API deweloperskiego:

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

Uzupełniaj lub usuwaj zadania tylko wtedy, gdy użytkownik wyraźnie o to prosi:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` zapisuje zrzut ekranu na dysk
i nadal wypisuje JSON na stdout dla skryptów. ID zrzutu zwykle pochodzi z
`local search-screen` albo z SQL nad tabelą `screenshots`. Jeśli Desktop zwróci
ustrukturyzowany błąd, taki jak `screenshot_pending`, `screenshot_file_missing`
lub `screenshot_chunk_corrupted`, tryb JSON zachowuje pola `reason`, `hint` oraz
`screenshot_id` na stderr, aby agent mógł ponowić starsze ID albo zgłosić
dokładną przeszkodę. Zweryfikuj udane wyjście poleceniem `file PATH`, zanim
przekażesz je narzędziom widzenia.

## Przykład: pętla agenta w Pythonie

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

## Obsługa limitów szybkości

Wspomnienia: 120/godz. Rozmowy: 25/godz. Tworzenie wsadowe: 15/godz.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Wskazówki

* Używaj `--profile <nazwa>`, jeśli agent obsługuje wiele kont Omi. Każdy
  profil ma własne poświadczenia i bazowy adres API.
* Do testów lokalnego backendu używaj `--api-base http://localhost:8080`.
* `OMI_LOCAL_API_URL` i `OMI_LOCAL_TOKEN` nadpisują ustawienia Desktop API
  z profilu na jedno uruchomienie.
* Do debugowania używaj `--verbose` — loguje `METHOD path → status (Ns)` na stderr
  bez wpływania na stdout, więc tryb JSON pozostaje poprawny.
* Aby wpiąć treść do rozmowy, użyj `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
