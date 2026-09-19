# omi-cli за AI агенте

> Практични водич за окружења вођена великим језичким моделима (Claude Code, Cursor, сопствени ботови).

## Зашто је CLI погодан за агенте

* **Стабилан JSON уговор.** Заставица `--json` емитује важећи JSON документ на stdout и
  *искључиво* JSON документ — без порука о напретку, без анимација учитавања. Грешке се
  шаљу на stderr као `{"error": "...", "detail": "..."}`.
* **Стабилни излазни кодови.** `0` у реду / `1` грешка у употреби / `2` аутентификација /
  `3` грешка сервера / `4` прекорачено ограничење захтева / `5` није пронађено. Агенти се
  могу гранати директно на основу ових кодова без анализе порука на природном језику.
* **Без интерактивних упита у headless окружењима.** Проследите `--yes` (или `-y`) деструктивним
  командама; проследите `--api-key` или поставите променљиву `OMI_API_KEY` да бисте прескочили
  интерактивну пријаву.
* **Толерантно понашање при поновним покушајима.** Грешке `429` и `5xx` аутоматски се поново
  покушавају уз експоненцијално одлагање (backoff) пре него што се пријаве.

## Аутентификација (једнократна, од стране човека)

Корисник преузима развојни API кључ са Omi веб апликације
(`https://app.omi.me` → Developer → API Keys) и извршава једно од следећег:

```bash
omi auth login                          # интерактивно лепљење; кључ се не чува у историји командне линије
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

Када Omi Desktop омогући свој локални API, агенти могу слати упите за локалну историју екрана
уређаја, резимее, SQL податке и задатке без коришћења cloud dev API-ја:

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

Завршавајте или бришите задатке само када корисник то изричито захтева:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

Команда `omi local screenshot SCREENSHOT_ID --output PATH` чува снимак екрана на диску
и наставља да исписује JSON на stdout за потребе скрипти. ID снимка екрана обично долази из
`local search-screen` или SQL упита над табелом `screenshots`. Ако Desktop врати структурирану
грешку попут `screenshot_pending`, `screenshot_file_missing` или `screenshot_chunk_corrupted`,
JSON режим чува поља `reason`, `hint` и `screenshot_id` на stderr-у, тако да агенти могу покушати
старији ID или пријавити тачну препреку. Проверите успешне излазе помоћу команде `file PATH`
пре него што их проследите алатима за рачунарски вид.

## Практичан пример: Python петља за агенте

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

## Управљање ограничењима захтева (Rate Limits)

Сећања: 120/сат. Разговори: 25/сат. Групна креирања: 15/сат.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Савети

* Користите `--profile <name>` ако ваш агент управља са више Omi налога. Сваки
  профил има сопствене акредитиве и API базу.
* Користите `--api-base http://localhost:8080` за локално тестирање backend-а.
* Користите променљиве окружења `OMI_LOCAL_API_URL` и `OMI_LOCAL_TOKEN` да бисте заменили
  локална подешавања Desktop API-ја профила за једно покретање.
* Користите `--verbose` за отклањање грешака — бележи `METHOD path → status (Ns)` на stderr
  без утицаја на stdout, тако да JSON режим остаје важећи.
* За прослеђивање садржаја у разговор користите `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
