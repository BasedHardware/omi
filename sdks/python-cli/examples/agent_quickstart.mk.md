# omi-cli за агенти

> Практичен водич за системи управувани од LLM (Claude Code, Cursor, ваши сопствени ботови).

## Зошто CLI е погоден за агенти

* **Стабилен JSON договор.** `--json` емитува валиден JSON документ на stdout и
  *само* JSON документ — без пораки за прогрес, без анимации за вчитување. Грешките одат
  на stderr како `{"error": "...", "detail": "..."}`.
* **Стабилни излезни кодови (exit codes).** `0` во ред / `1` грешка при користење / `2` автентикација /
  `3` грешка на сервер / `4` надминато ограничување на барања (rate limited) / `5` не е пронајдено. Агентите
  можат да се насочуваат според овие кодови без потреба од парсирање на грешки од природен јазик.
* **Без интерактивни барања во контексти без графички интерфејс (headless).** Проследете `--yes`
  (или `-y`) на деструктивните команди; проследете `--api-key` или поставете `OMI_API_KEY` за да го
  прескокнете интерактивното најавување.
* **Флексибилно повторно обидување.** Грешките `429` и `5xx` автоматски се повторуваат со постепено
  одложување (backoff) пред да се прикажат.

## Автентикација (еднократно, од страна на човек)

Корисникот добива развоен API клуч од веб-апликацијата на Omi
(`https://app.omi.me` → Developer → API Keys) и избира едно од следниве:

```bash
omi auth login                          # интерактивно лепење; клучот не останува во историјата на школката
# или
export OMI_API_KEY=omi_dev_...          # привремено, погодно за контејнери
```

## Петте работи што агентите најчесто ги прават

### 1. Читање спомени

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Креирање спомен

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Читање разговори

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Читање отворени задачи

```bash
omi action-item list --json --open
```

### 5. Означување задача како завршена

```bash
omi action-item complete --json a1b2c3d4
```

## Локален Desktop API

Кога Omi Desktop го активира својот локален API, агентите можат да бараат историја на екранот
на уредот, резимеа, SQL податоци и задачи без да користат облачен развоен API:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# или, за привремени сесии:
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

Завршувајте или бришете задачи само кога корисникот јасно го бара тоа:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` го запишува скриншотот на диск и сè уште
печати JSON на stdout за скрипти. Идентификаторот на скриншотот обично доаѓа од `local search-screen`
или SQL барање врз табелата `screenshots`. Доколку Desktop врати структуриран неуспех како
`screenshot_pending`, `screenshot_file_missing` или `screenshot_chunk_corrupted`, JSON режимот ги
зачувува полињата `reason`, `hint` и `screenshot_id` на stderr за агентите да можат да се обидат со
постар ID или точно да ја пријават пречката. Потврдете ги успешните излези со `file PATH` пред да ги
проследите на визуелни алатки.

## Практичен пример: Python циклус на агент

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Го повикува omi CLI во JSON режим, фрлајќи исклучок при неуспешни излезни кодови."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI печати структурирани грешки на stderr во JSON режим:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Прочитајте ги сите отворени задачи и означете ги како завршени оние постари од 30 дена.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Управување со ограничувањата на барања (Rate Limits)

Спомени: 120/час. Разговори: 25/час. Групно креирање: 15/час.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # ограничувањето е надминато
    err = json.loads(result.stderr)
    # err["detail"] изгледа вака: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Совети

* Користете `--profile <name>` доколку вашиот агент управува со повеќе Omi сметки.
  Секој профил има своја автентикација и базен API.
* Користете `--api-base http://localhost:8080` за локално тестирање на серверот.
* Користете `OMI_LOCAL_API_URL` и `OMI_LOCAL_TOKEN` за да ги премостите локалните
  поставки за Desktop API за едно извршување.
* Користете `--verbose` за дебагирање — ги бележи `METHOD path → status (Ns)` на stderr
  без да влијае на stdout, па JSON режимот останува валиден.
* За пренасочување на содржина во разговор користете `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
