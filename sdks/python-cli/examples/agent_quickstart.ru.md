# omi-cli для агентов

> Практическое руководство для сред на базе LLM (Claude Code, Cursor, собственные боты).

## Почему CLI идеально подходит для агентов

* **Стабильный контракт JSON.** Флаг `--json` выводит валидный JSON-документ в `stdout` и
  *только* JSON-документ: никаких сообщений о прогрессе или спиннеров. Ошибки выводятся в
  `stderr` в формате `{"error": "...", "detail": "..."}`.
* **Стабильные коды завершения.** `0` успех / `1` ошибка использования / `2` аутентификация / `3` сервер / `4` превышение
  лимита запросов (rate limit) / `5` не найдено. Агенты могут ветвить логику по кодам возврата без необходимости парсить
  сообщения на естественном языке.
* **Без интерактивных запросов в headless-режиме.** Передавайте `--yes` (или `-y`) для
  деструктивных команд; передавайте `--api-key` или задайте `OMI_API_KEY`, чтобы пропустить
  интерактивный вход.
* **Устойчивость к сбоям.** Ошибки `429` и `5xx` автоматически повторяются с экспоненциальной задержкой
  перед возвратом управления.

## Аутентификация (однократно, выполняется человеком)

Пользователь получает API-ключ разработчика в веб-приложении Omi
(`https://app.omi.me` → Developer → API Keys) и выполняет одно из действий:

```bash
omi auth login                          # интерактивная вставка; ключ не сохраняется в истории шелла
# или
export OMI_API_KEY=omi_dev_...          # эфемерный ключ, отлично подходит для контейнеров
```

## Пять основных действий для агентов

### 1. Чтение воспоминаний (memories)

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Создание воспоминания

```bash
omi memory create --json "Пользователь предпочитает темную тему" --category lifestyle
```

### 3. Чтение диалогов

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Чтение открытых задач (action items)

```bash
omi action-item list --json --open
```

### 5. Отметка задачи как выполненной

```bash
omi action-item complete --json a1b2c3d4
```

## Локальный API Desktop

Когда Omi Desktop предоставляет локальный API, агенты могут запрашивать историю
экрана на устройстве, сводки, SQL и задачи без обращения к облачному API разработчика:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# или для временных сессий:
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

Выполняйте или удаляйте задачи только тогда, когда пользователь прямо об этом попросил:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

Команда `omi local screenshot SCREENSHOT_ID --output PATH` сохраняет снимок экрана на диск и
продолжает выводить JSON в `stdout` для скриптов. Идентификатор снимка обычно поступает из
`local search-screen` или SQL-запроса к таблице `screenshots`. Если Desktop возвращает
структурированную ошибку, такую как `screenshot_pending`, `screenshot_file_missing`
или `screenshot_chunk_corrupted`, режим JSON сохраняет поля `reason`, `hint` и
`screenshot_id` в `stderr`, позволяя агентам повторить попытку с предыдущим ID или сообщить
точную причину сбоя. Проверяйте успешные файлы с помощью `file PATH` перед передачей
в инструменты компьютерного зрения.

## Практический пример: цикл агента на Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Вызывает omi CLI в режиме JSON, возбуждая исключение при ненулевых кодах возврата."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI выводит структурированные ошибки в stderr в режиме JSON:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi завершился с кодом {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Читаем все открытые задачи и завершаем те, которым больше 30 дней.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Обработка лимитов запросов (rate limits)

Воспоминания: 120/ч. Диалоги: 25/ч. Пакетные создания: 15/ч.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # превышен лимит запросов
    err = json.loads(result.stderr)
    # err["detail"] имеет вид: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Советы

* Используйте `--profile <name>`, если ваш агент управляет несколькими аккаунтами Omi. Каждый
  профиль хранит свои учетные данные и базовый URL API.
* Используйте `--api-base http://localhost:8080` для тестирования с локальным бэкендом.
* Используйте `OMI_LOCAL_API_URL` и `OMI_LOCAL_TOKEN` для переопределения настроек локального Desktop API
  профиля на время одного запуска.
* Используйте `--verbose` для отладки: выводит `METHOD path status (Ns)` в `stderr`,
  не засоряя `stdout` и сохраняя валидный JSON-поток.
* Для передачи содержимого в диалог через pipe используйте `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
