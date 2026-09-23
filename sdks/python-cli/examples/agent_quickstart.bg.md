# omi-cli за агенти

> Практическо ръководство за LLM-управлявани harness-и (Claude Code, Cursor, вашите ботове).

## Защо CLI е удобен за агенти

* **Стабилен JSON договор.** `--json` извежда валиден JSON документ в stdout и
  *само* JSON документ — без съобщения за напредък, без спинери. Грешките отиват в
  stderr като `{"error": "...", "detail": "..."}`.
* **Стабилни exit кодове.** `0` ok / `1` usage / `2` auth / `3` server / `4`
  rate limited / `5` не е намерено. Агентите могат да се разклоняват по тях без
  анализиране на грешки на естествен език.
* **Без интерактивни prompt-и в headless контексти.** Подайте `--yes` (или `-y`) на
  деструктивни команди; подайте `--api-key` или задайте `OMI_API_KEY`, за да
  пропуснете интерактивния вход.
* **Прощаващо поведение при повторения.** `429` и `5xx` се повтарят с backoff
  преди да се покажат.

## Auth (веднъж, от човека)

Потребителят получава dev API ключ от Omi уеб приложението
(`https://app.omi.me` → Developer → API Keys) и или:

```bash
omi auth login                          # interactive paste; key not in shell history
# or
export OMI_API_KEY=omi_dev_...          # ephemeral, container-friendly
```

## Петте неща, които агентите правят най-често

### 1. Четене на спомени

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Създаване на спомен

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Четене на разговори

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Четене на отворени action items

```bash
omi action-item list --json --open
```

### 5. Маркиране на action item като завършен

```bash
omi action-item complete --json a1b2c3d4
```

## Локален Desktop API

Когато Omi Desktop изложи своя локален API, агентите могат да питат за историята
на екрана на устройството, recap, SQL и задачи без използване на облачния dev API:

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

Завършвайте или изтривайте задачи само когато потребителят ясно помоли:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` записва екранната снимка на
диска и все още отпечатва JSON в stdout за скриптове. ID-то на снимката обикновено
идва от `local search-screen` или SQL над таблицата `screenshots`. Ако Desktop
върне структурирана грешка като `screenshot_pending`, `screenshot_file_missing`
или `screenshot_chunk_corrupted`, JSON режимът запазва полетата `reason`, `hint`
и `screenshot_id` в stderr, за да могат агентите да опитат по-старо ID или да
докладват точната пречка. Проверявайте успешните изходи с `file PATH`, преди да
ги предавате на vision инструменти.

## Практичен пример: Python agent loop

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

## Обработка на rate limits

Спомени: 120/час. Разговори: 25/час. Групови създавания: 15/час.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Съвети

* Използвайте `--profile <име>` ако вашият агент управлява множество Omi профили.
  Всеки профил има своите credentials и API base.
* Използвайте `--api-base http://localhost:8080` за локално тестване на backend.
* Използвайте `OMI_LOCAL_API_URL` и `OMI_LOCAL_TOKEN`, за да презапишете
  профил-локалните Desktop API настройки за едно изпълнение.
* Използвайте `--verbose` за отстраняване на грешки — записва `METHOD path → status (Ns)` в stderr,
  без да влияе на stdout, така че JSON режимът остава валиден.
* за захранване на съдържание в разговор, използвайте `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
