# omi-cli для агентів

> Практичний посібник для LLM-керованих harness'ів (Claude Code, Cursor, власні боти).

## Чому CLI дружній до агентів

* **Стабільний JSON-контракт.** `--json` виводить валідний JSON-документ у stdout і
  *лише* JSON-документ — без повідомлень про прогрес, без спінерів. Помилки йдуть у
  stderr як `{"error": "...", "detail": "..."}`.
* **Стабільні коди виходу.** `0` ok / `1` usage / `2` auth / `3` server / `4`
  rate limited / `5` не знайдено. Агенти можуть розгалужуватися на них без
  парсингу помилок природною мовою.
* **Без інтерактивних prompt'ів у headless-контекстах.** Передавайте `--yes` (або `-y`)
  деструктивним командам; передавайте `--api-key` або задайте `OMI_API_KEY`, щоб
  пропустити інтерактивний вхід.
* **Вибачлива поведінка повторів.** `429` і `5xx` повторюються з backoff
  перед показом.

## Auth (один раз, людиною)

Користувач отримує dev API-ключ з веб-додатка Omi
(`https://app.omi.me` → Developer → API Keys) і або:

```bash
omi auth login                          # interactive paste; key not in shell history
# or
export OMI_API_KEY=omi_dev_...          # ephemeral, container-friendly
```

## П'ять речей, які агенти роблять найчастіше

### 1. Читання спогадів

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Створення спогаду

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Читання розмов

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Читання відкритих action items

```bash
omi action-item list --json --open
```

### 5. Позначення action item як виконаного

```bash
omi action-item complete --json a1b2c3d4
```

## Локальний Desktop API

Коли Omi Desktop відкриває свій локальний API, агенти можуть запитувати історію
екрана пристрою, recap, SQL і завдання без використання хмарного dev API:

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

Завершуйте або видаляйте завдання лише коли користувач чітко просить:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` записує скриншот на диск і
досі друкує JSON у stdout для скриптів. ID скриншоту зазвичай надходить із
`local search-screen` або SQL над таблицею `screenshots`. Якщо Desktop
повертає структуровану помилку на кшталт `screenshot_pending`,
`screenshot_file_missing` або `screenshot_chunk_corrupted`, JSON-режим зберігає
поля `reason`, `hint` і `screenshot_id` в stderr, щоб агенти могли повторити
зі старішим ID або повідомити точну перешкоду. Перевіряйте успішні виводи
`file PATH` перед передачею у vision-інструменти.

## Практичний приклад: Python agent loop

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

## Обробка rate limits

Спогади: 120/год. Розмови: 25/год. Пакетне створення: 15/год.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Поради

* Використовуйте `--profile <ім'я>` якщо ваш агент керує кількома обліковими
  записами Omi. Кожен профіль має власні облікові дані та API base.
* Використовуйте `--api-base http://localhost:8080` для локального тестування backend.
* Використовуйте `OMI_LOCAL_API_URL` і `OMI_LOCAL_TOKEN`, щоб перевизначити
  локальні налаштування Desktop API профілю для одного запуску.
* Використовуйте `--verbose` для налагодження — логує `METHOD path → status (Ns)` в stderr,
  не впливаючи на stdout, тож JSON-режим залишається валідним.
* Щоб передати вміст у розмову, використовуйте `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
