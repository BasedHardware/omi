# omi-cli за агенте

> Практични водич за окружења заснована на LLM-у (Claude Code, Cursor, ваши прилагођени ботови).

## Зашто је CLI погодан за агенте

* **Стабилан JSON уговор.** Опција `--json` емитује валидан JSON документ на stdout и *искључиво* JSON документ — без порука о напретку, без анимација учитавања. Грешке се шаљу на stderr као `{"error": "...", "detail": "..."}`.
* **Стабилни излазни кодови.** `0` у реду / `1` грешка у употреби / `2` аутентификација / `3` сервер / `4` ограничена брзина / `5` није пронађено. Агенти могу да се гранају на основу ових кодова без анализе грешака на природном језику.
* **Без интерактивних упита у headless окружењима.** Проследите `--yes` (или `-y`) деструктивним командама; проследите `--api-key` или поставите `OMI_API_KEY` да прескочите интерактивну пријаву.
* **Толерантно понашање при поновном покушају.** Грешке `429` и `5xx` се аутоматски понављају са експоненцијалним одлагањем пре него што се врате.

## Аутентификација (једнократно, обавља корисник)

Корисник преузима развојни API кључ из Omi веб апликације (`https://app.omi.me` → Developer → API Keys) и бира једну од две опције:

```bash
omi auth login                          # интерактивно лепљење; кључ не остаје у историји љуске
# или
export OMI_API_KEY=omi_dev_...          # привремено, погодно за контејнере
```

## Пет најчешћих радњи које агенти обављају

### 1. Читање сећања

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Креирање сећања

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Читање разговора

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Читање отворених ставки задатака

```bash
omi action-item list --json --open
```

### 5. Означавање ставке задатка као завршене

```bash
omi action-item complete --json a1b2c3d4
```

## Локални Desktop API

Када Omi Desktop омогући свој локални API, агенти могу да претражују историју екрана на уређају, сажетке, SQL и задатке без коришћења cloud dev API-ја:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# или за привремене сесије:
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

Завршавајте или бришите задатке само када корисник то изричито затражи:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` чува снимак екрана на диск и даље штампа JSON на stdout за скрипте. ID снимка обично долази из `local search-screen` или SQL упита над табелом `screenshots`. Ако Desktop врати структурирану грешку као што је `screenshot_pending`, `screenshot_file_missing` или `screenshot_chunk_corrupted`, JSON режим чува поља `reason`, `hint` и `screenshot_id` на stderr-у, омогућавајући агентима да поново покушају са старијим ID-јем или пријаве тачну препреку. Проверите исправност резултата помоћу `file PATH` пре прослеђивања алатима за визуелну обраду.

## Практичан пример: Python петља агента

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Покреће omi CLI у JSON режиму и подиже изузетак при неуспешним излазним кодовима."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI штампа структуриране грешке на stderr у JSON режиму:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi је завршио са кодом {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Прочитај све отворене ставке задатака и означи све старије од 30 дана као завршене.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Управљање ограничењима брзине

Сећања: 120/сат. Разговори: 25/сат. Групно креирање: 15/сат.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # ограничена брзина
    err = json.loads(result.stderr)
    # err["detail"] изгледа као: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Савети

* Користите `--profile <назив>` ако ваш агент управља са више Omi налога. Сваки профил има сопствене акредитиве и API основу.
* Користите `--api-base http://localhost:8080` за локално тестирање backend-а.
* Користите `OMI_LOCAL_API_URL` и `OMI_LOCAL_TOKEN` да надјачате локална подешавања Desktop API-ја профила за једно покретање.
* Користите `--verbose` за отклањање грешака — бележи `METHOD path → status (Ns)` на stderr без утицаја на stdout, чиме JSON режим остаје валидан.
* За прослеђивање садржаја у разговор путем цеви (pipe), користите `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
