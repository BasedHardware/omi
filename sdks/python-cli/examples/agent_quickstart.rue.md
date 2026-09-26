# omi-cli про аґентів

> Практічный провідник про LLM-керованы гарнесы (Claude Code, Cursor, ваші властны боты).

## Чом є CLI приязна про аґентів

* **Стабілный JSON-контракт.** `--json` высылать платный JSON-документ на
  stdout і *лем* JSON-документ — жаданых повідомлінь о поступі, жаданых
  спінерів. Хыбы йдуть на stderr як `{"error": "...", "detail": "..."}`.
* **Стабілны кодівохода.** `0` ОК / `1` ужытя / `2` автентифікація / `3`
  сервер / `4` ліміт швыдкості / `5` не найдено. Аґенты можуть на том
  ґрунтовати без парсованя хыб у природным языку.
* **Жаданы інтерактівны вопросы у headless-контекстах.** Передайте `--yes`
  (або `-y`) деструктівным командам; передайте `--api-key` або наставте
  `OMI_API_KEY`, чтобы обыйти інтерактівный лоґін.
* **Толерантноє поведіня повторів.** `429` і `5xx` ся повторюють із backoff-ом
  перед тым, як ся показати.

## Автентифікація (єден раз, через чоловіка)

Хоснователь дістане dev API-ключ з веб-аплікації Omi
(`https://app.omi.me` → Developer → API Keys) і пак або:

```bash
omi auth login                          # інтерактівне вложіня; ключ ся не дістане до історії shell-а
# або
export OMI_API_KEY=omi_dev_...          # ефемерный, приязный про контейнеры
```

## Пять річей, котры аґенты роблять найчастїше

### 1. Чітати памяти

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Створити память

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Чітати конверзації

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Чітати отворены акції

```bash
omi action-item list --json --open
```

### 5. Означіти акцію як докончену

```bash
omi action-item complete --json a1b2c3d4
```

## Локальный Desktop API

Коли Omi Desktop выставить свій локальный API, аґенты можуть ся допытовати
історії екрана на пристрої, рекапів, SQL і задач без хоснованя хмарного API
dev:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# або, про ефемерны сесії:
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

Докінчте або зотріте задачі лем тогды, коли хоснователь ясно о то попросить:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` зайпісує скріншот на діск і
дале выпечатує JSON на stdout про скріпты. ID скріншота звычайно приходить із
`local search-screen` або з SQL по табелці `screenshots`. Коли Desktop верне
структуровану хыбу як `screenshot_pending`, `screenshot_file_missing` або
`screenshot_chunk_corrupted`, JSON-режім заховує поля `reason`, `hint` і
`screenshot_id` на stderr, так же аґенты можуть повторити зі старшым ID або
звістити точну переказу. Валідуйте успішны выступы з `file PATH` перед тым,
як їх передати до візійных інструментів.

## Приклад: петля аґента в Python-і

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Выкликать omi CLI в JSON-режімі, кідаючі на неуспішных кодівоходах."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI выпечатує структурованы хыбы на stderr в JSON-режімі:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Чітайте вшыткы отворены акції і означте як докончены ті, што старшы як 30 днів.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Обробка лімітів швыдкості

Памяти: 120/год. Конверзації: 25/год. Ґруповы творіня: 15/год.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # ліміт швыдкості
    err = json.loads(result.stderr)
    # err["detail"] выглядать так: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Тіпы

* Ужывайте `--profile <name>`, кідь ваш аґент обслугує веце Omi-контів. Каждый
  профіль має властны credential і API-базу.
* Ужывайте `--api-base http://localhost:8080` про тестованя локального
  backend-а.
* Ужывайте `OMI_LOCAL_API_URL` і `OMI_LOCAL_TOKEN`, чтобы перебити локальны
  Desktop API-наставліня профілю на єдно спущіня.
* Ужывайте `--verbose` про дебаґованя — лоґує `METHOD path → status (Ns)` на
  stderr без вплыву на stdout, так же JSON-режім зістає платный.
* Про передачу зміста до конверзації ужывайте `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
