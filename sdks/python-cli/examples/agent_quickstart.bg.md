# omi-cli за агенти

> Практическо ръководство за среди, управлявани от LLM (Claude Code, Cursor, собствени ботове).

## Защо CLI е удобен за агенти

* **Стабилен JSON договор.** Флагът `--json` извежда валиден JSON документ в stdout и
  *единствено* JSON документ — без съобщения за напредък, без спинери. Грешките отиват в
  stderr във формат `{"error": "...", "detail": "..."}`.
* **Стабилни изходни кодове (exit codes).** `0` успешно / `1` грешка при употреба / `2` грешка при автентикация / `3` грешка на сървъра / `4` надвишен
  лимит на заявките (rate limited) / `5` не е намерено. Агентите могат да разклоняват логиката си въз основа на тези кодове, без да анализират съобщения на естествен език.
* **Без интерактивни подкани в автоматичен режим (headless).** Подавайте `--yes` (или `-y`)
  за деструктивни команди; подавайте `--api-key` или задайте `OMI_API_KEY`, за да пропуснете
  интерактивното влизане.
* **Толерантно поведение при повторни опити.** Грешки от тип `429` и `5xx` се повтарят автоматично с експоненциално
  отлагане (backoff), преди да се върне грешка.

## Автентикация (еднократно, от човека)

Потребителят получава API ключ за разработчици от уеб приложението на Omi
(`https://app.omi.me` → Developer → API Keys) и избира една от следните опции:

```bash
omi auth login                          # интерактивно поставяне; ключът не остава в историята на обвивката
# или
export OMI_API_KEY=omi_dev_...          # временна променлива, удобна за контейнери
```

## Петте най-често извършвани действия от агентите

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

### 5. Отбелязване на задача като завършена

```bash
omi action-item complete --json a1b2c3d4
```

## Локален Desktop API

Когато Omi Desktop предоставя своя локален API, агентите могат да правят заявки към историята
на екрана на устройството, обобщения, SQL и задачи, без да изразходват облачния API:

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

Командата `omi local screenshot SCREENSHOT_ID --output PATH` записва екранната снимка
на диска и продължава да извежда JSON в stdout за скриптове. Идентификаторът на екранната снимка
обикновено идва от `local search-screen` или SQL заявка към таблицата `screenshots`. Ако Desktop
върне структурирана грешка като `screenshot_pending`, `screenshot_file_missing` или
`screenshot_chunk_corrupted`, режимът JSON запазва полетата `reason`, `hint` и
`screenshot_id` в stderr, така че агентите да могат да опитат отново с по-стар идентификатор или да докладват
точния проблем. Проверявайте успешните файлове с `file PATH`, преди да ги подадете на инструменти за компютърно зрение.

## Практически пример: цикъл на агент на Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Извиква omi CLI в режим JSON, хвърляйки изключение при ненулев изходен код."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI отпечатва структурирани грешки в stderr в режим JSON:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi завърши с код {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Четене на всички отворени задачи и отбелязване като завършени на тези, които са по-стари от 30 дни.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Управление на лимитите на заявките (Rate limits)

Спомени: 120/час. Разговори: 25/час. Пакетно създаване: 15/час.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # лимитът на заявките е достигнат
    err = json.loads(result.stderr)
    # err["detail"] изглежда така: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Съвети

* Използвайте `--profile <name>`, ако вашият агент управлява няколко акаунта в Omi. Всеки
  профил има свои собствени идентификационни данни и API база.
* Използвайте `--api-base http://localhost:8080` за тестване с локален бекенд.
* Използвайте `OMI_LOCAL_API_URL` и `OMI_LOCAL_TOKEN`, за да замените локалните настройки
  на Desktop API на профила за единично изпълнение.
* Използвайте `--verbose` за отстраняване на грешки — записва `METHOD път → статус (Ns)` в stderr
  без да засяга stdout, запазвайки валиден формат JSON.
* За подаване на съдържание в разговор чрез конвейер (pipe), използвайте `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
