# omi-cli для агентів

> Практичний посібник для середовищ на базі LLM (Claude Code, Cursor, власні боти).

## Чому CLI зручний для агентів

* **Стабільний контракт JSON.** `--json` виводить дійсний документ JSON у stdout і
  *тільки* документ JSON — без повідомлень про прогрес, без спінерів. Помилки надходять у
  stderr у форматі `{"error": "...", "detail": "..."}`.
* **Стабільні коди завершення.** `0` успіх / `1` помилка використання / `2` помилка автентифікації /
  `3` помилка сервера / `4` ліміт запитів / `5` не знайдено. Агенти можуть виконувати розгалуження
  на основі цих кодів без розбору повідомлень природною мовою.
* **Жодних інтерактивних запитів у headless-середовищах.** Передавайте `--yes` (або `-y`) для
  деструктивних команд; передавайте `--api-key` або встановіть `OMI_API_KEY`, щоб пропустити
  інтерактивний вхід.
* **Стійка поведінка повторних спроб.** Помилки `429` та `5xx` автоматично
  повторюються з очікуванням (backoff) перед поверненням.

## Автентифікація (одноразово, людиною)

Користувач отримує ключ API розробника у вебдодатку Omi
(`https://app.omi.me` → Developer → API Keys) та вибирає один із варіантів:

```bash
omi auth login                          # інтерактивна вставка; ключ не зберігається в історії shell
# або
export OMI_API_KEY=omi_dev_...          # тимчасовий, зручний для контейнерів
```

## П'ять дій, які агенти виконують найчастіше

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

### 4. Читання відкритих пунктів дій

```bash
omi action-item list --json --open
```

### 5. Позначення пункту дій як виконаного

```bash
omi action-item complete --json a1b2c3d4
```

## Локальний Desktop API

Коли Omi Desktop надає доступ до свого локального API, агенти можуть запитувати історію
екрана на пристрої, підсумки, SQL та завдання без використання хмарного dev API:

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

Завершуйте або видаляйте завдання лише тоді, коли користувач чітко про це просить:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` записує знімок екрана на
диск і водночас виводить JSON у stdout для скриптів. Ідентифікатор знімка екрана зазвичай
отримують із `local search-screen` або через SQL до таблиці `screenshots`. Якщо Desktop
повертає структуровану помилку, таку як `screenshot_pending`, `screenshot_file_missing`
або `screenshot_chunk_corrupted`, режим JSON зберігає поля `reason`, `hint` та
`screenshot_id` у stderr, щоб агенти могли повторити спробу зі старішим ID або повідомити про
точну проблему. Перевіряйте успішні результати за допомогою `file PATH` перед передачею
їх інструментам комп'ютерного зору.

## Практичний приклад: цикл агента на Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Викликає omi CLI у режимі JSON, генеруючи виняток у разі помилкових кодів виходу."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # У режимі JSON CLI виводить структуровані помилки в stderr:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Прочитати всі відкриті пункти дій і позначити виконаними ті, що старіші за 30 днів.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Обробка обмежень швидкості

Спогади: 120/год. Розмови: 25/год. Пакетні створення: 15/год.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # перевищено ліміт запитів
    err = json.loads(result.stderr)
    # err["detail"] має вигляд: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Корисні поради

* Використовуйте `--profile <name>`, якщо ваш агент керує кількома обліковими записами Omi. Кожен
  профіль має власні облікові дані та базову адресу API.
* Використовуйте `--api-base http://localhost:8080` для локального тестування бекенда.
* Використовуйте `OMI_LOCAL_API_URL` та `OMI_LOCAL_TOKEN`, щоб перевизначити налаштування
  Desktop API для окремого запуску.
* Використовуйте `--verbose` для налагодження — логує `METHOD path → status (Ns)` у stderr
  без впливу на stdout, зберігаючи валідність режиму JSON.
* Для передачі вмісту в розмову використовуйте `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
