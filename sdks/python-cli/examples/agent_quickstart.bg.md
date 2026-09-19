# omi-cli за агенти

> Практическо ръководство за инструменти, управлявани от LLM (Claude Code, Cursor, ваши собствени ботове).

## Защо CLI е удобен за агенти

* **Стабилен JSON договор.** Флагът `--json` извежда валиден JSON документ в stdout и
  *единствено* JSON документ — без съобщения за напредък или анимации. Грешките се извеждат в
  stderr като `{"error": "...", "detail": "..."}`.
* **Стабилни кодове за изход.** `0` успешно / `1` грешка при използване / `2` автентикация / `3` сървърна грешка / `4` ограничение на заявките / `5` не е намерено. Агентите могат да разклоняват логиката си въз основа на тези кодове, без да анализират съобщения на естествен език.
* **Без интерактивни подкани в автоматизирани среди.** Подайте `--yes` (или `-y`) за
  деструктивни команди; подайте `--api-key` или задайте `OMI_API_KEY`, за да пропуснете интерактивното влизане.
* **Толерантно поведение при повторен опит.** Кодовете `429` и `5xx` се опитват отново с прогресивно забавяне,
  преди да се върне грешка.

## Автентикация (еднократно, от човек)

Потребителят получава API ключ за разработчици от уеб приложението на Omi
(`https://app.omi.me` → Developer → API Keys) и прави едно от следните:

```bash
omi auth login                          # интерактивно поставяне; ключът не се записва в историята на обвивката
# или
export OMI_API_KEY=omi_dev_...          # временно, подходящо за контейнери
```

## Петте неща, които агентите правят най-често

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

### 4. Четене на отворени задачи за изпълнение

```bash
omi action-item list --json --open
```

### 5. Маркиране на задача като завършена

```bash
omi action-item complete --json a1b2c3d4
```

## Локално API за десктоп (Desktop API)

Когато Omi Desktop предостави своето локално API, агентите могат да правят заявки към историята на екрана на устройството,
резюмета, SQL и задачи, без да използват облачното API:

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

Завършвайте или изтривайте задачи само когато потребителят изрично поиска това:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

Командата `omi local screenshot SCREENSHOT_ID --output PATH` записва екранната снимка на
диска и продължава да извежда JSON в stdout за скриптове. Идентификаторът на екранната снимка обикновено
произлиза от `local search-screen` или от SQL заявка към таблицата `screenshots`. Ако Desktop
върне структурирана грешка като `screenshot_pending`, `screenshot_file_missing`
или `screenshot_chunk_corrupted`, режимът JSON запазва полетата `reason`, `hint` и
`screenshot_id` в stderr, така че агентите да могат да опитат отново с по-стар идентификатор или да съобщят
за точната пречка. Проверявайте успешните изходи с `file PATH`, преди да ги подадете към визуални инструменти.

## Практически пример: цикъл на агент в Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Извиква omi CLI в режим JSON, хвърляйки грешка при неуспешни кодове."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI извежда структурирани грешки в stderr в режим JSON:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Прочита всички отворени задачи и маркира тези над 30 дни като завършени.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Управление на ограниченията на скоростта (rate limits)

Спомени: 120/час. Разговори: 25/час. Пакетно създаване: 15/час.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # ограничение на заявките
    err = json.loads(result.stderr)
    # err["detail"] изглежда така: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Съвети

* Използвайте `--profile <име>`, ако вашият агент управлява няколко профила в Omi. Всеки
  профил има свои собствени идентификационни данни и базов адрес на API.
* Използвайте `--api-base http://localhost:8080` за тестване с локален бекенд.
* Използвайте `OMI_LOCAL_API_URL` и `OMI_LOCAL_TOKEN`, за да замените локалните настройки
  на Desktop API на профила за еднократно изпълнение.
* Използвайте `--verbose` за отстраняване на грешки — записва `METHOD path → status (Ns)` в stderr
  без да засяга stdout, като така режимът JSON остава валиден.
* За подаване на съдържание към разговор чрез конвейер използвайте `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
