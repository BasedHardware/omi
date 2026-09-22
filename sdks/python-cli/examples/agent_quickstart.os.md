# omi-cli агенттæн

> Практикон гайд LLM-æй хъомылгонд системæтæн (Claude Code, Cursor, дæ хæдивæг боттæ).

## Цæмæй CLI агенттæн æмбон у

* **Стабилон JSON контракт.** `--json` рарвысы валидон JSON документ stdout-æн
  æмæ *æрмæст* JSON документ — прогрессы фыстытæ нæй, спиннертæ нæй.
  Рæдыдтæ цæуынц stderr-æн куыд `{"error": "...", "detail": "..."}`.
* **Стабилон рахизы кодтæ.** `0` ok / `1` usage / `2` auth / `3` server /
  `4` rate limited / `5` not found. Агенттæ гæнæн сæхи равзарынц
  æхсæнадæмон æвзагы рæдыдтæ парс кæныны.
* **Интерактивон фарстытæ headless контекстты нæй.** Рат `--yes` (кæнæ `-y`)
  сафтгæнæг командæтæн; рат `--api-key` кæнæ æвæр `OMI_API_KEY` интерактивон
  логин тынгæй ауыныл.
* **Æмбæхсыддæг æрбайдæг.** `429` æмæ `5xx` æрбайдагæй кæнынц backoff-æй,
  æвдисынæн цыдæрдæм.

## Auth (иу хатт, адæймаджы)

Архайæг райсы dev API æвзæрстæ Omi web æфсымæрæй
(`https://app.omi.me` → Developer → API Keys) æмæ кæны иу дæрæй:

```bash
omi auth login                          # интерактивон æфст; æвзæрстæ shell-ы историйы нæ уа
# кæнæ
export OMI_API_KEY=omi_dev_...          # эфемерон, контейнертæн æмбон
```

## Фондз хъуыдыйæдты, агенттæ кæй фылдæр кæнынц

### 1. Æнусбардзинæдтæ кæсын

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Æнусбардзинæд саразын

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Дзурдзытæ кæсын

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Байгом архайдты иууæлтæ кæсын

```bash
omi action-item list --json --open
```

### 5. Архайды иууæл æххæстгондыл нысан кæнын

```bash
omi action-item complete --json a1b2c3d4
```

## Локалон Desktop API

Кæд Omi Desktop йæ локалон API æвдисы, уæд агенттæ гæнæн æмæ æрбафсæн
девайсы экраны истори, æмбарынæдтæ (recaps), SQL æмæ хъуыдыйæдтæ (tasks),
облакон dev API архайныне:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# кæнæ, эфемерон сесситæн:
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

Хъуыдыйæдтæ æххæст кæнæ сæфт кæн æрмæст кæд архайæг тынг æвзæрстæй афтæ
фæрсæн:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` фыссæй скриншот дискæн æмæ
JSON stdout-æн скрипттæн рарвысы. Скриншоты ID æгæнæн райсы
`local search-screen`-æй кæнæ `screenshots` таблицæйы SQL-æй. Кæд Desktop
структурон рæдыд рарвысы куыд `screenshot_pending`, `screenshot_file_missing`,
кæнæ `screenshot_chunk_corrupted`, уæд JSON режим `reason`, `hint` æмæ
`screenshot_id` уалдзæгтæ stderr-ы хæццæ кæны, цæмæй агенттæ гæнæн зæронд
ID-æй æрбайдæг кæнай кæнæ æцæгæй блокер фæхабар кæнай. Уæвæн рахизтæ
`file PATH`-æй проверка кæн vision инструменттæн раттынæн разæй.

## Архайгонд мысыл: Python агенты цикл

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Æмбарын omi CLI JSON режимы, рæдыд схæццæ кæны кæд рахизы код æмбарзонд нæ уа."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI структурон рæдыдтæ stderr-æн фыссæй JSON режимы:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Кæс алы байгом архайды иууæл æмæ æххæст кæн æппæты, 30 бонæй зæронддæр сты.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Rate limit-ты æмбарынад

Memories: 120/hr. Conversations: 25/hr. Batch creates: 15/hr.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # рейт-лимит
    err = json.loads(result.stderr)
    # err["detail"] æвзæр у афтæ: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Æмбæхсынæдтæ

* Архай `--profile <ном>` кæд дæ агент цалдæр Omi аккаунты архайы. Алы
  профилы йæхи credential æмæ API base ис.
* Архай `--api-base http://localhost:8080` локалон backend тест кæныны тыххæй.
* Архай `OMI_LOCAL_API_URL` æмæ `OMI_LOCAL_TOKEN` профилы локалон Desktop API
  параметртæ иу æххæстыл фæивын.
* Архай `--verbose` отладкæйы тыххæй — уый фыссæй `METHOD path → status (Ns)`
  stderr-æн, stdout нæ фæивы, æмæ JSON режим валидон баззайы.
* Контент дзурдзыты раттынæн, архай `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
