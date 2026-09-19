# omi-cli за агенти

> Практическо ръководство за среди, управлявани от LLM (Claude Code, Cursor, ваши собствени ботове).

## Защо CLI е подходящ за агенти

* **Стабилен JSON договор.** Флагът `--json` извежда валиден JSON документ на stdout и *единствено* JSON документ — без съобщения за напредък или индикатори за зареждане. Грешките се изпращат към stderr като `{"error": "...", "detail": "..."}`.
* **Стабилни изходни кодове.** `0` ок / `1` грешка при употреба / `2` автентикация / `3` сървър / `4` ограничение на скоростта / `5` не е намерено. Агентите могат да се разклоняват въз основа на тези кодове, без да анализират съобщения на естествен език.
* **Без интерактивни подкани в headless среда.** Подайте `--yes` (или `-y`) към деструктивните команди; подайте `--api-key` или задайте `OMI_API_KEY`, за да пропуснете интерактивното влизане.
* **Толерантно поведение при повторен опит.** Грешки `429` и `5xx` се повтарят автоматично с експоненциално отлагане, преди да бъдат изведени.

## Автентикация (еднократно, от потребителя)

Потребителят получава разработчески API ключ от уеб приложението Omi (`https://app.omi.me` → Developer → API Keys) и избира един от вариантите:

```bash
omi auth login                          # интерактивно поставяне; ключът не се запазва в историята на обвивката
# или
export OMI_API_KEY=omi_dev_...          # временно, удобно за контейнери
```

## Петте действия, които агентите извършват най-често

### 1. Четене на спомени

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Създаване на спомен

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Четене на разговори

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Четене на отворени задачи

```bash
omi action-item list --json --open
```

### 5. Маркиране на задача като завършена

```bash
omi action-item complete --json a1b2c3d4
```

## Локален Desktop API

Когато Omi Desktop предостави своя локален API, агентите могат да правят справки в историята на екрана на устройството, обобщения, SQL и задачи, без да използват облачния dev API:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# или за временни сесии:
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

Завършвайте или изтривайте задачи само когато потребителят изрично го поиска:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` записва екранната снимка на диска и продължава да извежда JSON на stdout за скриптове. ID на екранната снимка обикновено идва от `local search-screen` или SQL заявка към таблицата `screenshots`. Ако Desktop върне структурирана грешка като `screenshot_pending`, `screenshot_file_missing` или `screenshot_chunk_corrupted`, JSON режимът запазва полетата `reason`, `hint` и `screenshot_id` на stderr, позволявайки на агентите да опитат по-старо ID или да докладват точния проблем. Проверявайте успешните файлове с `file PATH`, преди да ги предадете на визуални инструменти.

## Практически пример: Python цикъл на агент

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Извиква omi CLI в JSON режим, хвърляйки изключение при неуспешни изходни кодове."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI извежда структурирани грешки на stderr в JSON режим:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi приключи с код {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Прочита всички отворени задачи и маркира по-старите от 30 дни като завършени.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Управление на ограниченията за скорост

Спомени: 120/час. Разговори: 25/час. Пакетно създаване: 15/час.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # ограничение на скоростта
    err = json.loads(result.stderr)
    # err["detail"] изглежда така: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Съвети

* Използвайте `--profile <име>`, ако вашият агент управлява няколко акаунта в Omi. Всеки профил има свои собствени идентификационни данни и базов API адрес.
* Използвайте `--api-base http://localhost:8080` за локално тестване на бекенда.
* Използвайте `OMI_LOCAL_API_URL` и `OMI_LOCAL_TOKEN`, за да замените локалните настройки на Desktop API за едно изпълнение.
* Използвайте `--verbose` за дебъгване — записва `METHOD path → status (Ns)` на stderr, без да засяга stdout, запазвайки валиден JSON режима.
* За пренасочване на съдържание в разговор чрез конвейер (pipe), използвайте `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
