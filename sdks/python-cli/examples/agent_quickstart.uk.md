# omi-cli для агентів

> Практичний посібник для середовищ на основі LLM (Claude Code, Cursor, власні боти).

## Чому CLI зручний для агентів

* **Стабільний контракт JSON.** Прапорець `--json` виводить коректний документ JSON у stdout і *виключно* документ JSON — жодних повідомлень про прогрес, жодних спінерів. Помилки направляються в stderr у форматі `{"error": "...", "detail": "..."}`.
* **Стабільні коди завершення.** `0` успішно / `1` помилка використання / `2` помилка авторизації / `3` помилка сервера / `4` перевищено ліміт запитів / `5` не знайдено. Агенти можуть виконувати розгалуження без парсингу тексту.
* **Жодних інтерактивних запитів у headless-режимі.** Передавайте `--yes` (або `-y`) для деструктивних команд; передавайте `--api-key` або встановлюйте `OMI_API_KEY` для пропуску інтерактивного входу.
* **Гнучке повторення запитів.** Помилки `429` та `5xx` автоматично повторюються з експоненційною затримкою (backoff).

## Авторизація (одноразова, виконується людиною)

Користувач отримує API-ключ розробника у веб-додатку Omi
(`https://app.omi.me` → Developer → API Keys) і виконує:

```bash
omi auth login                          # інтерактивне вставляння; ключ не потрапляє в історію оболонки
# або
export OMI_API_KEY=omi_dev_...          # ефемерне, зручне для контейнерів
```

## П'ять найчастіших дій агентів

### 1. Читання спогадів (memories)

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

### 4. Читання відкритих завдань (action items)

```bash
omi action-item list --json --open
```

### 5. Позначення завдання як виконаного

```bash
omi action-item complete --json a1b2c3d4
```

## Локальний API робочого столу (Local Desktop API)

Коли Omi Desktop надає свій локальний API, агенти можуть опитувати історію екрана, підсумки, SQL та завдання без хмарного API:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# або для ефемерних сесій:
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

Завершуйте або видаляйте завдання лише тоді, коли користувач явно про це просить:

```bash
omi --json local task complete task_1
```
