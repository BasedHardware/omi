# omi-cli про аґентів

> Практічный путіводитель про harness-ы ведені LLM (Claude Code, Cursor, ваші власні боты).

## Чому CLI приятельскый про аґентів

* **Стабілный JSON-контракт.** `--json` выдавалов валідный JSON-документ на stdout і
  *тільки* JSON-документ — жадны повідомлїня про поступ, жадны спіннеры. Хыбы
  ідуть на stderr як `{"error": "...", "detail": "..."}`.
* **Стабілны коды выходу.** `0` добрій / `1` хоснованя / `2` auth / `3` сервер /
  `4` ліміт швыдкости / `5` не найджене. Аґенты можуть ся розгалювати на них без
  аналізованя хыб в природнїм языку.
* **Жадны інтерактівны промпты в headless-контекстах.** Подай `--yes` (або `-y`)
  до деструктівных команд; подай `--api-key` або настав `OMI_API_KEY`, жебы
  обыти інтерактівне лоґованя.
* **Поблажливе повторйованя.** `429` і `5xx` ся повторюють з backoff-ом первйнж
  выйду.

## Auth (раз, од чоловіка)

Хоснователь бере dev API-ключ з Омі web-аплікатуры
(`https://app.omi.me` → Developer → API Keys) і або:

```bash
omi auth login                          # інтерактівне вставляня; ключ не остает в гісторії шелла
# або
export OMI_API_KEY=omi_dev_...          # ефемерный, ідеалный про контейнеры
```

## Пять річей, што аґенты роблять найвеце

### 1. Чітаня памятї

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Створїня памятї

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Чітаня бесїд

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Чітаня отвореных пунктів дїї

```bash
omi action-item list --json --open
```

### 5. Означованя пункту дїї як зробленый

```bash
omi action-item complete --json a1b2c3d4
```

## Локалне Desktop-API

Кеды Omi Desktop выставлят свою локалну API, аґенты можуть пытати історію
екрану пристроя, рекапітулації, SQL і роботы без хоснованя хмарового dev-API:

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

Докончіт або вымазати роботы тільки кеды хоснователь ясно просить:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` пише screenshot на диск і
дале друкує JSON на stdout про скрипты. ID screenshot-у звычайно приходить з
`local search-screen` або SQL над таблёв `screenshots`. Кеды Desktop верне
структуровану хыбу як `screenshot_pending`, `screenshot_file_missing` або
`screenshot_chunk_corrupted`, режим JSON заховує поля `reason`, `hint` і
`screenshot_id` на stderr, жебы аґенты могли повторіти з старшым ID або
доложіти точный блокадор. Валідуйте добры выходы з `file PATH` первйнж
передачёй до візуалных інструментів.

## Працованый приклад: аґентовый цикл в Python-ї

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

## Заряджаня лімітами швыдкости

Памятї: 120/год. Бесїды: 25/год. Створїня в батчах: 15/год.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Рады

* Хоснуй `--profile <name>`, кеды ваш аґент заряджує много Омі-конт. Каждый
  профіль має свої креденції і базу API.
* Хоснуй `--api-base http://localhost:8080` про локалны backend-тесты.
* Хоснуй `OMI_LOCAL_API_URL` і `OMI_LOCAL_TOKEN`, жебы надписати локалны
  Desktop-API-наставлїня профіля про єдно выконаня.
* Хоснуй `--verbose` про дебагованя — записує `METHOD path → status (Ns)` на
  stderr без вплыву на stdout, через што режим JSON остает валідный.
* Жебы переправити зміст до бесїды, хоснуй `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
