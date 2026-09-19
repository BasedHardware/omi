# omi-cli для агентів

> Практичний посібник для інтеграції з LLM-гарнесами (Claude Code, Cursor, власні боти).

## Чому цей CLI зручний для агентів

* **Стабільний контракт JSON.** Прапорець `--json` виводить у stdout валідний документ JSON і *тільки* документ JSON — жодних повідомлень про прогрес чи спінерів завантаження. Помилки надсилаються у stderr у форматі `{"error": "...", "detail": "..."}`.
* **Стабільні коди завершення.** `0` — успіх / `1` — помилка використання / `2` — помилка авторизації / `3` — помилка сервера / `4` — перевищено ліміт запитів (rate limited) / `5` — не знайдено. Агенти можуть розгалужувати логіку на основі цих кодів без парсингу повідомлень природною мовою.
* **Відсутність інтерактивних запитів у headless-режимі.** Передавайте `--yes` (або `-y`) для деструктивних команд; передавайте `--api-key` або встановіть змінну середовища `OMI_API_KEY`, щоб пропустити інтерактивний вхід.
* **Гнучка поведінка повторних спроб.** Помилки `429` та `5xx` автоматично повторюються з експоненційною затримкою (exponential backoff) перед поверненням виклику.

## Авторизація (одноразово, людиною)

Користувач отримує ключ API розробника у веб-додатку Omi (`https://app.omi.me` → Developer → API Keys) і виконує одну з дій:

```bash
omi auth login                          # інтерактивна вставка; ключ не зберігається в історії shell
# або
export OMI_API_KEY=omi_dev_...          # тимчасова сесія, зручно для контейнерів
```

## П'ять основних операцій, які агенти виконують найчастіше

### 1. Читання спогадів

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Створення спогаду

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Читання діалогів

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Читання відкритих завдань

```bash
omi action-item list --json --open
```

### 5. Позначення завдання як виконаного

```bash
omi action-item complete --json a1b2c3d4
```

## Локальний Desktop API

Коли Omi Desktop надає свій локальний API, агенти можуть запитувати історію екрана, підсумки, SQL та завдання безпосередньо на пристрої без використання хмарного API розробника:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# або для тимчасових сесій:
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

Виконуйте або видаляйте завдання лише тоді, коли користувач чітко про це попросив:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

Команда `omi local screenshot SCREENSHOT_ID --output PATH` записує знімок екрана на диск і продовжує виводити JSON у stdout для скриптів. Ідентифікатор знімка зазвичай надходить із `local search-screen` або SQL-запиту до таблиці `screenshots`. Якщо Desktop повертає структуровану помилку (наприклад, `screenshot_pending`, `screenshot_file_missing` або `screenshot_chunk_corrupted`), режим JSON зберігає поля `reason`, `hint` і `screenshot_id` у stderr, щоб агенти могли повторити спробу з попереднім ID або повідомити про точну причину блокування. Перевіряйте успішні вихідні файли за допомогою `file PATH` перед передачею в інструменти комп'ютерного зору.

## Практичний приклад: цикл Python-агента

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Викликає omi CLI в режимі JSON, піднімаючи виняток при неуспішних кодах завершення."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI виводить структуровані помилки в stderr у режимі JSON:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Читає всі відкриті завдання та позначає виконаними ті, які старіші за 30 днів.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Обробка обмежень швидкості

Спогади: 120/год. Діалоги: 25/год. Пакетне створення: 15/год.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # ліміт запитів досягнуто
    err = json.loads(result.stderr)
    # err["detail"] виглядає так: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Корисні поради

* Використовуйте `--profile <name>`, якщо ваш агент керує кількома обліковими записами Omi. Кожен профіль має власні облікові дані та базову адресу API.
* Для локального тестування бекенда використовуйте `--api-base http://localhost:8080`.
* Використовуйте `OMI_LOCAL_API_URL` та `OMI_LOCAL_TOKEN`, щоб перевизначити локальні налаштування Desktop API профілю для одного запуску.
* Використовуйте `--verbose` для налагодження — це записує `METHOD path → status (Ns)` у stderr, не впливаючи на stdout, завдяки чому режим JSON залишається валідним.
* Для передачі вмісту в діалог через конвеєр використовуйте `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
