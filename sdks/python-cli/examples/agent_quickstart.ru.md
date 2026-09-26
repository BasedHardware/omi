# omi-cli для ИИ-агентов

> Практическое руководство для сред под управлением LLM (Claude Code, Cursor или собственные боты автоматизации).

## Почему этот CLI удобен для агентов

* **Стабильный протокол JSON.** Флаг `--json` выводит один валидный JSON-документ в stdout и *только* JSON-документ — без сообщений о ходе выполнения и без спиннеров. Ошибки выводятся в stderr в формате `{"error": "...", "detail": "..."}`.
* **Предсказуемые коды завершения.** `0` успех / `1` ошибка использования / `2` ошибка аутентификации / `3` ошибка сервера / `4` превышен лимит запросов (rate limited) / `5` ресурс не найден. Агенты могут ветвить логику напрямую по кодам завершения без синтаксического анализа естественного языка.
* **Неинтерактивный режим по умолчанию в headless-средах.** Передайте `--yes` (или `-y`) для деструктивных команд; передайте `--api-key` или задайте переменную окружения `OMI_API_KEY`, чтобы пропустить интерактивный вход.
* **Встроенные повторные попытки.** Коды ошибок `429` и `5xx` автоматически повторяются с экспоненциальной задержкой перед возвратом ошибки вызывающей стороне.

## Аутентификация (Однократно, выполняется человеком)

Пользователь получает ключ разработчика API в веб-приложении Omi (`https://app.omi.me` → Developer → API Keys) и выполняет одно из следующих действий:

```bash
omi auth login                          # интерактивная вставка; ключ не сохраняется в истории оболочки
# либо
export OMI_API_KEY=omi_dev_...          # временно, подходит для контейнеров
```

## Пять основных операций агента

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

### 5. Отметка задачи выполненной

```bash
omi action-item complete --json a1b2c3d4
```

## Local Desktop API (Локальный Desktop API)

Когда приложение Omi Desktop открывает локальный API, агенты могут запрашивать историю экрана, сводки дня, локальную базу данных SQL и задачи прямо на устройстве без обращения к облачному dev API:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# либо для временных сессий:
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

Локальные изменения (задачи):

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

## Пример рабочего процесса: Цикл агента на Python

```python
import json
import subprocess
import sys

def run_omi(*args: str) -> dict | list:
    """Запуск omi CLI в режиме JSON с вызовом исключения при ненулевом коде завершения."""
    cmd = ["omi", "--json", *args]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        # CLI выводит структурированные ошибки в stderr в режиме JSON:
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"raw": result.stderr}
        raise RuntimeError(f"omi завершился с ошибкой (exit {result.returncode}): {err}")
    return json.loads(result.stdout)

# Прочитать все открытые задачи и пометить выполненными те, что старше 30 дней.
from datetime import datetime, timezone, timedelta

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = run_omi("action-item", "list", "--open")
for item in items:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        print(f"Завершение старой задачи: {item['id']} ({item['description']})")
        run_omi("action-item", "complete", item["id"])
```

## Обработка ограничений частоты запросов (Rate Limits)

```python
if result.returncode == 4:                             # превышен лимит запросов
    err = json.loads(result.stderr)
    # err["detail"] имеет вид: "Retry in 12s. ..."
    # omi CLI уже выполнил 3 повторные попытки внутри; если код 4 всё ещё возвращается,
    # приостановите вызовы на указанное время.
```

Текущие лимиты облачного dev API:
* Чтение (GET): 120 запросов / мин
* Запись (POST/PUT/DELETE): 25 запросов / мин
* Семантический поиск: 15 запросов / мин

Локальные лимиты (через Desktop API): искусственные ограничения отсутствуют; ограничено производительностью хост-машины.

## Советы и рекомендации

* Используйте `--profile <name>`, если агент переключается между несколькими аккаунтами Omi (например, тест и прод). Учётные данные хранятся раздельно в `~/.config/omi/profiles/<name>.json`.
* Для модульных тестов с имитацией сервера (mock): передавайте `--api-base http://localhost:8080`.
* Не разбирайте неструктурированный текст stdout — форматирование текста предназначено для человека и может меняться между версиями. Всегда используйте `--json` в скриптах автоматизации.
