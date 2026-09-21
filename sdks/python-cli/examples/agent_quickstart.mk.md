# omi-cli за агенти (Macedonian / Македонски)

> Практичен водич за системи водени од LLM (Claude Code, Cursor, вашите сопствени ботови).

## Зошто CLI е прилагоден за агенти (Why the CLI is agent-friendly)

* **Стабилен JSON договор (Stable JSON contract).** `--json` емитува валиден JSON документ на stdout и *само* JSON документ — без пораки за напредок, без спинери. Грешките одат на stderr како `{"error": "...", "detail": "..."}`.
* **Стабилни излезни кодови (Stable exit codes).** `0` во ред / `1` грешка при користење / `2` автентикација / `3` серверска грешка / `4` ограничена брзина (rate limit) / `5` не е пронајдено. Агентите можат да одлучуваат според овие кодови без анализа на пораки со природен јазик.
* **Без интерактивни прашања во безглави контексти (No interactive prompts in headless contexts).** Проследете `--yes` (или `-y`) за деструктивни команди; проследете `--api-key` или поставете `OMI_API_KEY` за да го прескокнете интерактивното најавување.
* **Толерантно однесување за повторен обид (Forgiving retry behavior).** Грешките `429` и `5xx` автоматски се повторуваат со постепено одложување пред да се појават.

## Автентикација (еднократно, од човек)

Корисникот добива развоен API клуч од веб-апликацијата Omi (`https://app.omi.me` → Developer → API Keys) и или:

```bash
omi auth login                          # интерактивно вметнување; клучот не останува во историјата на терминалот
# или
export OMI_API_KEY=omi_dev_...          # привремено, погодно за контејнери
```

## Петте работи што агентите ги прават најмногу

### 1. Прочитајте спомени (Read memories)

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Создадете спомен (Create a memory)

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Прочитајте разговори (Read conversations)

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Прочитајте отворени ставки за акција (Read open action items)

```bash
omi action-item list --json --open
```

### 5. Означете ставка за акција како завршена (Mark an action item done)

```bash
omi action-item complete --json a1b2c3d4
```

## Локален Desktop API (Local Desktop API)

Кога Omi Desktop го овозможува својот локален API, агентите можат да бараат историја на екранот на уредот, резимеа, SQL и задачи без користење на облачниот API:

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

`omi local screenshot SCREENSHOT_ID --output PATH` ја запишува сликата од екранот на диск и печати JSON на stdout за скрипти. Доколку Desktop врати структурирана грешка (`screenshot_pending`, `screenshot_file_missing` или `screenshot_chunk_corrupted`), JSON режимот ги зачувува полињата `reason`, `hint` и `screenshot_id` на stderr.

## Работен пример: Јамка за Python агент (Worked example: Python agent loop)

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Повикајте го omi CLI во JSON режим, фрлајќи исклучок при неуспешни излезни кодови."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Прочитајте ги сите отворени ставки за акција и означете сè постаро од 30 дена како завршено.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Справување со ограничувања на брзината (Handling rate limits)

Спомени: 120/час. Разговори: 25/час. Групни креирања: 15/час.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # ограничена брзина
    err = json.loads(result.stderr)
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Совети (Tips)

* Користете `--profile <name>` ако вашиот агент управува со повеќе Omi сметки.
* Користете `--api-base http://localhost:8080` за локално тестирање на бекендот.
* Користете `OMI_LOCAL_API_URL` и `OMI_LOCAL_TOKEN` за да ги премостите локалните поставки за Desktop API.
* Користете `--verbose` за дебагирање — се запишува на stderr без да влијае на stdout.
* За препраќање содржина во разговор, користете `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
