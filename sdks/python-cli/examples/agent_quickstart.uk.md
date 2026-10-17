# omi-cli для агентів

> Практичний посібник для LLM-керованих harnessів (Claude Code, Cursor, власні боти).

## Чому CLI зручний для агентів

* **Стабільний JSON-контракт.** `--json` видає на stdout валідний JSON-документ і *лише* JSON — без повідомлень прогресу чи спінерів. Помилки йдуть на stderr як `{"error": "...", "detail": "..."}`.
* **Стабільні коди виходу.** `0` ok / `1` використання / `2` auth / `3` сервер / `4` rate limited / `5` не знайдено. Агенти можуть розгалужуватися за ними без парсингу природномовних помилок.
* **Жодних інтерактивних запитів у headless-контекстах.** Передавайте `--yes` (або `-y`) руйнівним командам; передайте `--api-key` або встановіть `OMI_API_KEY`, щоб пропустити інтерактивний вхід.
* **Поблажлива повторна поведінка.** `429` і `5xx` повторюються з backoff перед появою.

## Автентифікація (одноразово, людиною)

Користувач отримує dev API key у веб-застосунку Omi
(`https://app.omi.me` → Developer → API Keys) і або:

```bash
omi auth login                          # інтерактивне вставлення; ключ не в історії shell
# # або
export OMI_API_KEY=omi_dev_...          # ефемерний, зручний для контейнерів
```

## П'ять речей, які агенти роблять найчастіше

### 1. Читання memories

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Створення memory

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Читання conversations

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Читання відкритих action items

```bash
omi action-item list --json --open
```

### 5. Позначити action item виконаним

```bash
omi action-item complete --json a1b2c3d4
```

## Локальний Desktop API

Коли Omi Desktop відкриває локальний API, агенти можуть запитувати
on-device screen history, recaps, SQL і задачі без хмарного dev API:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# # або, для ефемерних сесій:
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

Завершуйте або видаляйте задачі лише коли користувач чітко просить:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` записує скріншот на диск
і далі друкує JSON на stdout для скриптів. ID скріншота зазвичай приходить з
`local search-screen` або SQL по таблиці `screenshots`. Якщо Desktop повертає
структуровану помилку типу `screenshot_pending`, `screenshot_file_missing` чи
`screenshot_chunk_corrupted`, режим JSON зберігає `reason`, `hint` і
`screenshot_id` на stderr, щоб агент міг повторити старіший ID або повідомити
точний блокер. Успішні результати валідуйте `file PATH` перед передачею
інструментам комп'ютерного зору.

## Приклад: цикл Python-агента

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

# Прочитайте всі відкриті action items і завершіть старші за 30 днів.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Обробка rate limits

Memories: 120/год. Conversations: 25/год. Batch-створення: 15/год.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] має вигляд: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Поради

* Використовуйте `--profile <name>`, якщо агент жонглює кількома акаунтами Omi.
  Кожен профіль має власні credentials і API base.
* Використовуйте `--api-base http://localhost:8080` для локального тестування бекенду.
* Використовуйте `OMI_LOCAL_API_URL` і `OMI_LOCAL_TOKEN`, щоб перевизначити
  профільні налаштування Desktop API на один запуск.
* Використовуйте `--verbose` для налагодження — логує `METHOD path → status (Ns)`
  на stderr без впливу на stdout, тому JSON-режим лишається валідним.
* Щоб пропускати вміст у conversation, використовуйте `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
