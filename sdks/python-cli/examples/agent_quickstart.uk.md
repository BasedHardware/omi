# omi-cli для агентів

> Практичний посібник для систем на базі LLM (Claude Code, Cursor, власні боти).

## Чому CLI зручний для агентів

* **Стабільний контракт JSON.** Прапорець `--json` виводить у stdout валідний JSON-документ і
  *тільки* JSON-документ — жодних повідомлень про перебіг, жодних спінерів. Помилки надсилаються
  до stderr у форматі `{"error": "...", "detail": "..."}`.
* **Стабільні коди завершення.** `0` успіх / `1` помилка використання / `2` помилка автентифікації /
  `3` помилка сервера / `4` обмеження частоти запитів / `5` не знайдено. Агенти можуть будувати логіку
  на основі цих кодів без парсингу тексту помилок природною мовою.
* **Жодних інтерактивних запитів у headless-середовищах.** Передавайте `--yes` (або `-y`) для
  деструктивних команд; передавайте `--api-key` або задавайте `OMI_API_KEY`, щоб пропустити інтерактивний вхід.
* **Толерантна поведінка повторних спроб.** Помилки `429` та `5xx` автоматично повторюються
  з експоненційним відкладенням (backoff) перед поверненням.

## Автентифікація (одноразово, користувачем)

Користувач отримує ключ API розробника у веб-додатку Omi
(`https://app.omi.me` → Developer → API Keys) і виконує одну з дій:

```bash
omi auth login                          # інтерактивна вставка; ключ не зберігається в історії оболонки
# або
export OMI_API_KEY=omi_dev_...          # тимчасово, зручно для контейнерів
```

## П'ять операцій, які агенти виконують найчастіше

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

### 4. Читання відкритих завдань

```bash
omi action-item list --json --open
```

### 5. Позначення завдання як виконаного

```bash
omi action-item complete --json a1b2c3d4
```

## Локальний Desktop API

Коли Omi Desktop відкриває свій локальний API, агенти можуть запитувати історію екрана,
підсумки, дані SQL та завдання безпосередньо з пристрою, не звертаючись до хмарного dev API:

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

Завершуйте або видаляйте завдання лише за чітким запитом користувача:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

Команда `omi local screenshot SCREENSHOT_ID --output PATH` записує знімок екрана на диск і
продовжує виводити JSON у stdout для скриптів. Ідентифікатор знімка екрана зазвичай надходить
із `local search-screen` або SQL-запиту до таблиці `screenshots`. Якщо Desktop повертає
структуровану помилку, таку як `screenshot_pending`, `screenshot_file_missing` або
`screenshot_chunk_corrupted`, режим JSON зберігає поля `reason`, `hint` і `screenshot_id`
у stderr, що дозволяє агентам спробувати старіший ID або точно повідомити про перешкоду.
Перевіряйте успішні результати за допомогою `file PATH` перед передачею їх інструментам комп'ютерного зору.

## Практичний приклад: цикл агента на Python

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

## Обробка обмежень частоти запитів (rate limits)

Спогади: 120/год. Розмови: 25/год. Пакетні створення: 15/год.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Поради

* Використовуйте `--profile <ім'я>`, якщо ваш агент керує кількома обліковими записами Omi.
  Кожен профіль має власні облікові дані та базову адресу API.
* Використовуйте `--api-base http://localhost:8080` для тестування локального бекенду.
* Використовуйте `OMI_LOCAL_API_URL` та `OMI_LOCAL_TOKEN` для перекриття локальних налаштувань
  Desktop API профілю на один запуск.
* Використовуйте `--verbose` для налагодження — прапорець записує `METHOD path → status (Ns)` у stderr,
  не впливаючи на stdout, завдяки чому вивід режиму JSON залишається коректним.
* Для передачі вмісту в розмову через конвеєр (pipe) використовуйте `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
