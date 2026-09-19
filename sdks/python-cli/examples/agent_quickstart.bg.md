# omi-cli за AI агенти

> Практическо ръководство за среди, управлявани от LLM (Claude Code, Cursor, собствени ботове).

## Защо CLI е удобен за агенти

* **Стабилен JSON договор.** Флагът `--json` извежда валиден JSON документ в stdout и
  *единствено* JSON документ — без съобщения за напредък, без спинъри. Грешките се
  изпращат в stderr като `{"error": "...", "detail": "..."}`.
* **Стабилни кодове за изход.** `0` успех / `1` грешка при използване / `2` автентикация /
  `3` грешка на сървъра / `4` лимит на заявките / `5` не е намерено. Агентите могат да
  разклоняват логиката си директно без синтактичен анализ на съобщения на естествен език.
* **Без интерактивни подкани в headless среда.** Подавайте `--yes` (или `-y`) за деструктивни
  команди; подавайте `--api-key` или задайте променливата `OMI_API_KEY`, за да пропуснете
  интерактивното влизане.
* **Толерантно поведение при повторни опити.** Грешки от тип `429` и `5xx` се опитват повторно
  автоматично с експоненциално забавяне (backoff), преди да бъдат докладвани.

## Автентикация (еднократна, от човек)

Потребителят получава API ключ за разработчици от уеб приложението на Omi
(`https://app.omi.me` → Developer → API Keys) и изпълнява:

```bash
omi auth login                          # интерактивно поставяне; ключът не се записва в историята на shell
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

### 4. Четене на отворени задачи за действие

```bash
omi action-item list --json --open
```

### 5. Маркиране на задача като изпълнена

```bash
omi action-item complete --json a1b2c3d4
```

## Локално Desktop API

Когато Omi Desktop активира своето локално API, агентите могат да правят справки в историята
на екрана на устройството, обобщения, SQL и задачи без използване на облачното dev API:

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

Командата `omi local screenshot SCREENSHOT_ID --output PATH` записва екранната снимка на
диска и продължава да извежда JSON в stdout за скриптове. Идентификаторът на екранната снимка
обикновено идва от `local search-screen` или SQL заявка към таблицата `screenshots`. Ако Desktop
върне структурирана грешка като `screenshot_pending`, `screenshot_file_missing` или
`screenshot_chunk_corrupted`, JSON режимът запазва полетата `reason`, `hint` и `screenshot_id`
в stderr, така че агентите да могат да опитат по-стар ID или да съобщят точния проблем.
Проверявайте успешните резултати с `file PATH`, преди да ги подадете към инструменти за компютърно зрение.

## Практически пример: Python цикъл за агент

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

## Справяне с лимитите на заявките (Rate Limits)

Спомени: 120/час. Разговори: 25/час. Пакетни създавания: 15/час.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Съвети

* Използвайте `--profile <name>`, ако вашият агент управлява няколко акаунта на Omi. Всеки
  профил има свои собствени идентификационни данни и API база.
* Използвайте `--api-base http://localhost:8080` за локални тестове на backend.
* Използвайте `OMI_LOCAL_API_URL` и `OMI_LOCAL_TOKEN`, за да презапишете локалните настройки
  на Desktop API на профила за едно конкретно изпълнение.
* Използвайте `--verbose` за дебъгване — записва `METHOD path → status (Ns)` в stderr
  без да засяга stdout, така че JSON режимът остава валиден.
* За пренасочване на съдържание в разговор използвайте `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
