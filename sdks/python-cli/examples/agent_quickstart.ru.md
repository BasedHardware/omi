# omi-cli для агентов

> Практическое руководство по интеграции с LLM-харнесами (Claude Code, Cursor, собственные боты).

## Почему этот CLI удобен для агентов

* **Стабильный контракт JSON.** Флаг `--json` выводит в stdout валидный документ JSON и *только* JSON — никаких сообщений о прогрессе и анимаций загрузки (спиннеров). Ошибки выводятся в stderr в формате `{"error": "...", "detail": "..."}`.
* **Стабильные коды завершения (Exit codes).** `0` — успешно / `1` — ошибка использования / `2` — ошибка авторизации / `3` — ошибка сервера / `4` — превышен лимит запросов (rate limited) / `5` — не найдено. Агенты могут ветвить логику на основе этих кодов без необходимости парсинга сообщений на естественном языке.
* **Отсутствие интерактивных запросов в headless-режиме.** Передавайте `--yes` (или `-y`) для деструктивных команд; передавайте `--api-key` или задайте переменную `OMI_API_KEY`, чтобы пропустить интерактивный вход.
* **Автоматические повторные попытки (Retry).** Ошибки `429` и `5xx` автоматически повторяются с экспоненциальной задержкой перед тем, как вернуть ошибку клиенту.

## Авторизация (разовая настройка человеком)

Пользователь получает API-ключ разработчика в веб-приложении Omi (`https://app.omi.me` → Developer → API Keys) и выполняет одно из действий:

```bash
omi auth login                          # интерактивная вставка; ключ не сохраняется в истории shell
# или
export OMI_API_KEY=omi_dev_...          # временная сессия, удобно для контейнеров
```

## Пять основных операций, которые агенты выполняют чаще всего

### 1. Чтение воспоминаний

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Создание воспоминания

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Чтение диалогов

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Чтение открытых задач

```bash
omi action-item list --json --open
```

### 5. Отметка задачи как выполненной

```bash
omi action-item complete --json a1b2c3d4
```

## Локальный Desktop API

Когда Omi Desktop предоставляет локальный API, агенты могут напрямую запрашивать историю экрана, сводки, SQL и задачи на устройстве без использования облачного API:

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

Выполняйте или удаляйте задачи только тогда, когда пользователь явно об этом попросил:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

Команда `omi local screenshot SCREENSHOT_ID --output PATH` сохраняет снимок экрана на диск и выводит JSON в stdout для скриптов. Идентификатор снимка обычно берется из `local search-screen` или SQL-запроса к таблице `screenshots`. Если Desktop возвращает структурированную ошибку (например, `screenshot_pending`, `screenshot_file_missing` или `screenshot_chunk_corrupted`), режим JSON сохраняет поля `reason`, `hint` и `screenshot_id` в stderr, чтобы агенты могли повторить попытку с более ранним ID или сообщить точную причину сбоя. Проверяйте успешный результат с помощью `file PATH` перед передачей в инструменты компьютерного зрения.

## Практический пример: цикл Python-агента

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Вызывает omi CLI в режиме JSON, вызывая исключение при ненулевом коде возврата."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # В режиме JSON CLI выводит структурированные ошибки в stderr:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Читает все открытые задачи и отмечает выполненными те, которым больше 30 дней.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Обработка ограничений скорости

Воспоминания: 120/час. Диалоги: 25/час. Пакетное создание: 15/час.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # превышен лимит запросов
    err = json.loads(result.stderr)
    # err["detail"] выглядит как: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Полезные советы

* Используйте флаг `--profile <name>`, если ваш агент управляет несколькими учетными записями Omi. Каждый профиль имеет собственные учетные данные и базовый URL API.
* Для локального тестирования бэкенда используйте `--api-base http://localhost:8080`.
* Используйте переменные `OMI_LOCAL_API_URL` и `OMI_LOCAL_TOKEN`, чтобы переопределить локальные настройки Desktop API для одного запуска.
* Используйте `--verbose` для отладки — этот параметр выводит логи вида `METHOD path → status (Ns)` в stderr, не влияя на stdout, благодаря чему режим JSON остается валидным.
* Для передачи содержимого в диалог через пайп используйте `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
