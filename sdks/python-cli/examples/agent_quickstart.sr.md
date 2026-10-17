# omi-cli за агенте

> Практичан водич за LLM-вођене харнесе (Claude Code, Cursor, сопствени ботови).

## Зашто је CLI погодан за агенте

* **Стабилан JSON уговор.** `--json` исписује валидан JSON документ на stdout и *само* JSON — без порука о напретку и спинера. Грешке иду на stderr као `{"error": "...", "detail": "..."}`.
* **Стабилни излазни кодови.** `0` ok / `1` употреба / `2` auth / `3` сервер / `4` rate limited / `5` није пронађено. Агенти могу гранати по њима без парсирања грешки у природном језику.
* **Нема интерактивних упита у headless контекстима.** Проследи `--yes` (или `-y`) деструктивним командама; проследи `--api-key` или постави `OMI_API_KEY` да прескочиш интерактивни логин.
* **Попустљиво понављање.** `429` и `5xx` се понављају са backoff-ом пре него што испливе.

## Аутентикација (једном, од стране човека)

Корисник узима dev API кључ из Omi веб апликације
(`https://app.omi.me` → Developer → API Keys) и или:

```bash
omi auth login                          # интерактивно налепљивање; кључ није у историји шел-а
# # или
export OMI_API_KEY=omi_dev_...          # ефемеран, прилагођен контејнерима
```

## Пет ствари које агенти најчешће раде

### 1. Читање memories

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Креирање memory

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Читање conversations

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Читање отворених action items

```bash
omi action-item list --json --open
```

### 5. Означавање action item као завршен

```bash
omi action-item complete --json a1b2c3d4
```

## Локални Desktop API

Када Omi Desktop изложи свој локални API, агенти могу да питају
on-device screen history, рекапе, SQL и задатке без облачног dev API:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# # или, за ефемерне сесије:
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

Завршавај или бриши задатке само када корисник јасно тражи:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` пише скриншот на диск
и даље штампа JSON на stdout за скрипте. ID скриншота обично долази из
`local search-screen` или SQL над табелом `screenshots`. Ако Desktop врати
структурирану грешку као `screenshot_pending`, `screenshot_file_missing` или
`screenshot_chunk_corrupted`, JSON режим чува `reason`, `hint` и `screenshot_id`
на stderr тако да агент може покушати старији ID или пријавити тачан блокер.
Успешне излазе валидирај са `file PATH` пре слања vision алатима.

## Разрађени пример: Python агент петља

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

# Прочитај све отворене action items и означи завршене оне старије од 30 дана.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Руковање rate limit-овима

Memories: 120/ч. Conversations: 25/ч. Batch креирања: 15/ч.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] изгледа: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Савети

* Користи `--profile <name>` ако агент жонглира више Omi налога. Сваки
  профил има сопствене credentials и API базу.
* Користи `--api-base http://localhost:8080` за локално тестирање backend-а.
* Користи `OMI_LOCAL_API_URL` и `OMI_LOCAL_TOKEN` да преписујеш профил-
  локална Desktop API подешавања за једно покретање.
* Користи `--verbose` за дебаговање — логује `METHOD path → status (Ns)`
  на stderr без утицаја на stdout, па JSON режим остаје валидан.
* За pipe-овање садржаја у conversation користи `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
