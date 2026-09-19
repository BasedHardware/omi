# omi-cli для агентов

> Практическое руководство для LLM-сред (Claude Code, Cursor, ваших собственных ботов).

## Почему CLI удобен для агентов

* **Стабильный JSON-контракт.** `--json` выводит в stdout валидный JSON-документ и *только* его — без сообщений о прогрессе или спиннеров. Ошибки записываются в stderr в виде `{"error": "...", "detail": "..."}`.
* **Стабильные коды выхода.** `0` — ОК / `1` — ошибка использования / `2` — ошибка разрешений / `3` — ошибка сервера / `4` — превышен лимит запросов / `5` — не найдено. Агенты могут ветвиться по этим кодам без разбора естественного языка сообщений об ошибках.
* **Никаких интерактивных запросов в headless-контекстах.** Передавайте `--yes` (или `-y`) для деструктивных команд; передавайте `--api-key` или задавайте `OMI_API_KEY`, чтобы пропустить интерактивный вход.
* **Устойчивая логика повторных попыток.** Коды `429` и `5xx` повторяются с экспоненциальной задержкой перед сообщением об ошибке.

## Аутентификация (один раз, пользователем)

Пользователь получает API-ключ разработчика в веб-приложении Omi (`https://app.omi.me` → Developer → API Keys) и выполняет одно из:

```bash
omi auth login                          # интерактивная вставка; ключ не попадает в историю оболочки
# oder / ou / ili / or / ή / veya / või / o / ale /
export OMI_API_KEY=omi_dev_...          # временный, удобный для контейнеров
```

## Пять вещей, которые агенты делают чаще всего

### 1. Чтение воспоминаний

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Создание воспоминания

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Чтение разговоров

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Чтение открытых задач

```bash
omi action-item list --json --open
```

### 5. Отметить задачу как выполненную

```bash
omi action-item complete --json a1b2c3d4
```

## Локальный Desktop API

Когда Omi Desktop предоставляет свой локальный API, агенты могут запрашивать историю экрана устройства, сводки, SQL и задачи без использования облачного dev API:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# временный, удобный для контейнеров:
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

Завершайте или удаляйте задачи только по явной просьбе пользователя:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` сохраняет снимок экрана на диск и при этом записывает JSON в stdout для скриптов. ID снимков экрана обычно берутся из `local search-screen` или SQL по таблице `screenshots`. Если Desktop возвращает структурированную ошибку, например `screenshot_pending`, `screenshot_file_missing` или `screenshot_chunk_corrupted`, режим JSON сохраняет поля `reason`, `hint` и `screenshot_id` в stderr, чтобы агенты могли повторить запрос с более ранним ID или сообщить о конкретном препятствии. Проверяйте успешные результаты командой `file PATH` перед передачей в инструменты зрения.

## Практический пример: цикл агента на Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Запустить CLI omi в режиме JSON и выбросить исключение при ошибочных кодах выхода."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI пишет структурированные ошибки в stderr в режиме JSON:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi завершился с кодом {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Прочитать все открытые задачи и отметить старше 30 дней как выполненные.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Обработка ограничений частоты запросов

Воспоминания: 120/час. Разговоры: 25/час. Пакетное создание: 15/час.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # превышен лимит запросов
    err = json.loads(result.stderr)
    # err["detail"] выглядит как: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Советы

* Используйте `--profile <имя>`, если ваш агент управляет несколькими аккаунтами Omi. Каждый профиль имеет свои учётные данные и базовый URL API.
* Используйте `--api-base http://localhost:8080` для тестирования локального бэкенда.
* Используйте `OMI_LOCAL_API_URL` и `OMI_LOCAL_TOKEN`, чтобы переопределить настройки Desktop API профиля для одного запуска.
* Используйте `--verbose` для отладки — записывает `METHOD path → status (Ns)` в stderr, не влияя на stdout, поэтому режим JSON остаётся валидным.
* Для передачи содержимого в разговор через пайп используйте `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
