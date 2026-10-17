# omi-cli dla agentów

> Praktyczny przewodnik dla harnessów sterowanych LLM (Claude Code, Cursor, własne boty).

## Dlaczego CLI jest przyjazne agentom

* **Stabilny kontrakt JSON.** `--json` emituje na stdout poprawny dokument JSON i *tylko* JSON — bez komunikatów postępu i spinnerów. Błędy trafiają na stderr jako `{"error": "...", "detail": "..."}`.
* **Stabilne kody wyjścia.** `0` ok / `1` użycie / `2` auth / `3` serwer / `4` rate limited / `5` nie znaleziono. Agenty mogą na nich rozgałęziać bez parsowania błędów w języku naturalnym.
* **Brak interaktywnych promptów w kontekstach headless.** Do komend destrukcyjnych podaj `--yes` (lub `-y`); podaj `--api-key` albo ustaw `OMI_API_KEY`, aby pominąć interaktywne logowanie.
* **Wybaczające ponawianie.** `429` i `5xx` są ponawiane z backoffem zanim wypłyną.

## Auth (jednorazowo, przez człowieka)

Użytkownik pobiera dev API key z aplikacji webowej Omi
(`https://app.omi.me` → Developer → API Keys) i albo:

```bash
omi auth login                          # wklejenie interaktywne; klucz nie w historii shella
# # albo
export OMI_API_KEY=omi_dev_...          # efemeryczny, przyjazny kontenerom
```

## Pięć najczęstszych działań agentów

### 1. Odczyt memories

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Utworzenie memory

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Odczyt conversations

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Odczyt otwartych action items

```bash
omi action-item list --json --open
```

### 5. Oznaczenie action item jako zrobiony

```bash
omi action-item complete --json a1b2c3d4
```

## Lokalne API Desktop

Gdy Omi Desktop udostępnia lokalne API, agenty mogą odpytywać screen history,
recapy, SQL i zadania na urządzeniu bez chmurowego dev API:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# # albo, dla sesji efemerycznych:
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

Ukończaj lub usuwaj zadania tylko gdy użytkownik wyraźnie o to prosi:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` zapisuje screenshot na
dysk i nadal drukuje JSON na stdout dla skryptów. ID screenshota zwykle pochodzi
z `local search-screen` lub SQL po tabeli `screenshots`. Jeśli Desktop zwróci
ustrukturyzowany błąd jak `screenshot_pending`, `screenshot_file_missing` czy
`screenshot_chunk_corrupted`, tryb JSON zachowuje na stderr pola `reason`, `hint`
i `screenshot_id`, więc agent może ponowić starsze ID albo zgłosić dokładny
bloker. Udane wyniki sprawdź `file PATH` przed przekazaniem do narzędzi wizji.

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

# Wczytaj wszystkie otwarte action items i ukończ starsze niż 30 dni.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Obsługa rate limitów

Memories: 120/godz. Conversations: 25/godz. Tworzenia zbiorcze: 15/godz.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] wygląda tak: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Wskazówki

* Użyj `--profile <name>` jeśli agent obsługuje kilka kont Omi. Każdy profil
  ma własne poświadczenia i bazę API.
* Użyj `--api-base http://localhost:8080` do lokalnych testów backendu.
* Użyj `OMI_LOCAL_API_URL` i `OMI_LOCAL_TOKEN`, aby nadpisać profilowe
  ustawienia Desktop API na jedno uruchomienie.
* Użyj `--verbose` do debugowania — loguje `METHOD path → status (Ns)` na stderr
  bez wpływu na stdout, więc tryb JSON pozostaje ważny.
* Do pipowania treści do conversation użyj `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
