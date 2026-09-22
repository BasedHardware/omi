# omi-cli dla agentów

> Praktyczny przewodnik dla środowisk opartych na modelach LLM (Claude Code, Cursor, własne boty).

## Dlaczego CLI jest przyjazne dla agentów

* **Stabilny kontrakt JSON.** Flaga `--json` wypisuje poprawny dokument JSON na standardowe wyjście (stdout) i *wyłącznie* dokument JSON — bez komunikatów o postępie i bez spinnerów. Błędy trafiają na standardowe wyjście błędów (stderr) w formacie `{"error": "...", "detail": "..."}`.
* **Stabilne kody wyjścia.** `0` ok / `1` błąd użycia / `2` błąd uwierzytelnienia / `3` błąd serwera / `4` przekroczenie limitu zapytań / `5` nie znaleziono. Agenci mogą podejmować decyzje na podstawie tych kodów bez konieczności parsowania komunikatów w języku naturalnym.
* **Brak interaktywnych monitów w trybie bezgłowym.** Przekaż `--yes` (lub `-y`) w przypadku poleceń niszczących; przekaż `--api-key` lub ustaw zmienną środowiskową `OMI_API_KEY`, aby pominąć logowanie interaktywne.
* **Elastyczna obsługa ponownych prób.** Kody `429` oraz `5xx` są automatycznie ponawiane z mechanizmem backoff przed zwróceniem błędu.

## Uwierzytelnianie (jednorazowe, wykonywane przez człowieka)

Użytkownik pobiera klucz programisty (API key) z aplikacji webowej Omi
(`https://app.omi.me` → Developer → API Keys) i wykonuje:

```bash
omi auth login                          # wklejanie interaktywne; klucz nie trafia do historii powłoki
# lub
export OMI_API_KEY=omi_dev_...          # efemeryczne, przyjazne dla kontenerów
```

## Pięć najczęstszych czynności wykonywanych przez agentów

### 1. Odczyt wspomnień (memories)

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

### 4. Odczyt otwartych zadań (action items)

```bash
omi action-item list --json --open
```

### 5. Oznaczanie zadania jako ukończone

```bash
omi action-item complete --json a1b2c3d4
```

## Lokalne API pulpitu (Local Desktop API)

Gdy aplikacja Omi Desktop udostępnia swoje lokalne API, agenci mogą odpytywać historię ekranu na urządzeniu, podsumowania, SQL oraz zadania bez korzystania z chmurowego API:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# lub w przypadku sesji efemerycznych:
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

Zadania należy oznaczać jako ukończone lub usuwać wyłącznie na wyraźną prośbę użytkownika:

```bash
omi --json local task complete task_1
```
