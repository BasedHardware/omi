# omi-cli для агентов

> Практическое руководство для LLM-управляемых harness'ов (Claude Code, Cursor, свои боты).

## Почему CLI удобен для агентов

* **Стабильный JSON-контракт.** `--json` выводит в stdout валидный JSON-документ и *только* JSON — без прогресс-сообщений и спиннеров. Ошибки идут в stderr как `{"error": "...", "detail": "..."}`.
* **Стабильные коды выхода.** `0` ok / `1` использование / `2` auth / `3` сервер / `4` rate limited / `5` не найдено. Агенты могут ветвиться по ним без парсинга текстовых ошибок.
* **Никаких интерактивных запросов в headless-контекстах.** Передавайте `--yes` (или `-y`) деструктивным командам; передавайте `--api-key` или задайте `OMI_API_KEY`, чтобы пропустить интерактивный вход.
* **Снисходительные повторы.** `429` и `5xx` повторяются с backoff до появления.

## Аутентификация (однократно, человеком)

Пользователь получает dev API key в веб-приложении Omi
(`https://app.omi.me` → Developer → API Keys) и либо:

```bash
omi auth login                          # интерактивная вставка; ключ не в истории shell
# # или
export OMI_API_KEY=omi_dev_...          # эфемерный, удобен в контейнерах
```

## Пять самых частых действий агентов

### 1. Чтение memories

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Создание memory

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Чтение conversations

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Чтение открытых action items

```bash
omi action-item list --json --open
```

### 5. Пометить action item выполненным

```bash
omi action-item complete --json a1b2c3d4
```

## Локальный Desktop API

Когда Omi Desktop открывает локальный API, агенты могут запрашивать
on-device screen history, recaps, SQL и задачи без облачного dev API:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# # или, для эфемерных сессий:
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

Завершайте или удаляйте задачи только когда пользователь явно просит:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` пишет скриншот на диск
и по-прежнему печатает JSON в stdout для скриптов. ID скриншота обычно берётся
из `local search-screen` или SQL по таблице `screenshots`. Если Desktop возвращает
структурированную ошибку вроде `screenshot_pending`, `screenshot_file_missing`
или `screenshot_chunk_corrupted`, режим JSON сохраняет поля `reason`, `hint` и
`screenshot_id` в stderr, чтобы агент мог повторить более старый ID или сообщить
точный блокер. Успешные результаты проверяйте `file PATH` перед передачей
vision-инструментам.

## Пример: цикл Python-агента

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

# Прочитайте все открытые action items и завершите старше 30 дней.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Обработка rate limits

Memories: 120/ч. Conversations: 25/ч. Batch-создания: 15/ч.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] выглядит так: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Советы

* Используйте `--profile <name>`, если агент жонглирует несколькими аккаунтами
  Omi. У каждого профиля свои credentials и API base.
* Используйте `--api-base http://localhost:8080` для локального тестирования бэкенда.
* Используйте `OMI_LOCAL_API_URL` и `OMI_LOCAL_TOKEN`, чтобы переопределить
  профильные настройки Desktop API на один запуск.
* Используйте `--verbose` для отладки — логирует `METHOD path → status (Ns)`
  в stderr, не влияя на stdout, поэтому JSON-режим остаётся валидным.
* Для пайпа контента в conversation используйте `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
