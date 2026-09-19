# omi-cli для агентов

> Практическое руководство для LLM-оркестраторов (Claude Code, Cursor, ваши собственные боты).

## Почему CLI удобен для агентов

* **Стабильный JSON-контракт.** `--json` выводит в stdout корректный JSON-документ и
  *только* JSON-документ — без сообщений о прогрессе и спиннеров. Ошибки уходят в
  stderr в виде `{"error": "...", "detail": "..."}`.
* **Стабильные коды выхода.** `0` успех / `1` ошибка использования / `2` аутентификация /
  `3` сервер / `4` превышен лимит запросов / `5` не найдено. Агент может ветвиться
  по этим кодам, не разбирая текст ошибок на естественном языке.
* **Никаких интерактивных запросов в headless-режиме.** Передавайте `--yes` (или `-y`)
  разрушающим командам; передавайте `--api-key` или задайте `OMI_API_KEY`, чтобы
  пропустить интерактивный вход.
* **Мягкие повторы.** `429` и `5xx` повторяются с backoff, прежде чем ошибка
  поднимется наверх.

## Аутентификация (один раз, делает человек)

Пользователь получает ключ разработчика в веб-приложении Omi
(`https://app.omi.me` → Developer → API Keys) и делает одно из двух:

```bash
omi auth login                          # интерактивная вставка; ключ не попадает в историю shell
# или
export OMI_API_KEY=omi_dev_...          # временный, удобен в контейнерах
```

## Пять самых частых действий агента

### 1. Прочитать воспоминания

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Создать воспоминание

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Прочитать разговоры

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Прочитать открытые задачи

```bash
omi action-item list --json --open
```

### 5. Отметить задачу выполненной

```bash
omi action-item complete --json a1b2c3d4
```

## Локальный Desktop API

Когда Omi Desktop открывает свой локальный API, агенты могут запрашивать историю
экрана, сводки, SQL и задачи прямо на устройстве, не обращаясь к облачному API
разработчика:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# или, для временных сессий:
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

Завершайте или удаляйте задачи только тогда, когда пользователь явно об этом
попросил:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` записывает скриншот на диск и
по-прежнему печатает JSON в stdout для скриптов. Идентификатор скриншота обычно
приходит из `local search-screen` или из SQL-запроса к таблице `screenshots`.
Если Desktop возвращает структурированную ошибку вроде `screenshot_pending`,
`screenshot_file_missing` или `screenshot_chunk_corrupted`, JSON-режим сохраняет
поля `reason`, `hint` и `screenshot_id` в stderr, чтобы агент мог повторить
запрос с более старым идентификатором или точно сообщить, что мешает. Проверяйте
успешные результаты командой `file PATH`, прежде чем передавать их инструментам
компьютерного зрения.

## Разобранный пример: цикл агента на Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Вызывает omi CLI в JSON-режиме и бросает исключение при ненулевом коде выхода."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # В JSON-режиме CLI печатает структурированные ошибки в stderr:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Прочитать все открытые задачи и закрыть те, что старше 30 дней.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Работа с лимитами запросов

Воспоминания: 120/час. Разговоры: 25/час. Пакетное создание: 15/час.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # превышен лимит
    err = json.loads(result.stderr)
    # err["detail"] выглядит так: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Советы

* Используйте `--profile <name>`, если агент работает с несколькими аккаунтами Omi.
  У каждого профиля свои учётные данные и свой API base.
* Используйте `--api-base http://localhost:8080` для тестов с локальным бэкендом.
* Используйте `OMI_LOCAL_API_URL` и `OMI_LOCAL_TOKEN`, чтобы на один запуск
  переопределить настройки Desktop API, сохранённые в профиле.
* Используйте `--verbose` для отладки — он пишет `METHOD path → status (Ns)` в
  stderr, не трогая stdout, так что JSON-режим остаётся корректным.
* Чтобы передать содержимое в разговор через конвейер, используйте `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
