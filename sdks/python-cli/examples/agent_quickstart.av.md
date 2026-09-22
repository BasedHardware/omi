# omi-cli агенталъе

> Практикияб нухда-хӀал LLM-аца хӀадурулел харнесалъе (Claude Code, Cursor, дудасул ботал).

## Ко рагье CLI агенталъе гьадулеб

* **Стабилияб JSON договор.** `--json` гьабула JSON документ stdout-алде ва
  *цогидал* JSON документ — прогресс-лъул мессаги гьечӀо, спиннерал гьечӀо.
  ХатӀалал stderr-алде тола `{"error": "...", "detail": "..."}` рекъон.
* **Стабилиял бахъиял кодал.** `0` ok / `1` usage / `2` auth / `3` server /
  `4` rate limited / `5` not found. Агентал гьелъул бокьарал бефсанебу,
  рагӀал мацӀалъул хатӀал парсинг гьабичӀого.
* **Интерактивиял къотӀолал гьечӀо headless контексталда.** Тола `--yes`
  (яги `-y`) деструктивиял командалъе; тола `--api-key` яги рагье
  `OMI_API_KEY` интерактивияб логин дандечӀизе.
* **Хьалараб повторное кӀодо гьаби.** `429` ва `5xx` backoff-аца кӀодо
  гьабулебу бихьизаги цӀика.

## Auth (цо рекъон, инсанаса)

Инсанаса бачӀуна dev API ключ Omi web приложениялдаса
(`https://app.omi.me` → Developer → API Keys) ва кӀицӀе гьабула:

```bash
omi auth login                          # интерактивияб борхатаби; ключ shell историялда гьечӀо
# яги
export OMI_API_KEY=omi_dev_...          # эфемерияб, контейнералъе хъвалъухӀ
```

## Агенталъул унго-ункӀо гьабулеб бицӀан

### 1. Memories хъвасизе

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Memory гьабизе

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Conversations хъвасизе

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. КъотӀолел action items хъвасизе

```bash
omi action-item list --json --open
```

### 5. Action item хӀалтӀун бихьизе

```bash
omi action-item complete --json a1b2c3d4
```

## Локалияб Desktop API

Omi Desktop-аса гьесул локалияб API бихьизабулебу, агентал бефсанебу
on-device экран-лъул история, рекапал, SQL ва задачал къотӀоле, облакияб
dev API хӀалтӀизабичӀого:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# яги, эфемериял сессиялъе:
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

Задачал хӀалтӀизабе яги гьоркье цогида инсанаса гъицӀого къотӀолебу:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` скриншот дискалде тола ва
JSON stdout-алде скрипталъе хӀабизабула. Скриншот-лъул ID цӀикӀкӀун
`local search-screen`-алдаса яги `screenshots` таблицаязул SQL-алдаса тола.
Desktop структурияб хатӀ `screenshot_pending`, `screenshot_file_missing` яги
`screenshot_chunk_corrupted` борхатабулебу, JSON режимаса `reason`, `hint` ва
`screenshot_id` полял stderr-алда хӀалкъола, агенталъулъе цӀика ID кӀодо
гьабизе яги цӀагӀ блокер баян гьабизе. Кьо бахъсал `file PATH`-аца балагье
vision инструменталъе кьезе цӀика.

## Практикияб мисал: Python агент-лъул цикл

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Тола omi CLI JSON режималда, кьо гьечӀеб exit кодалда хатӀ борхатабула."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI структуриял хатӀалал stderr-алде тола JSON режималда:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Балухъел action items кинал хъвасе, 30 къоязда цӀикӀкӀунел хӀалтӀизабе.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Рейт-лимитал кӀодо гьаби

Memories: 120/hr. Conversations: 25/hr. Batch creates: 15/hr.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # рейт лимит
    err = json.loads(result.stderr)
    # err["detail"] гьадинаб бихьизабула: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## МассахӀал

* ХӀалтӀизабе `--profile <name>` дудасул агентаса унго-ункӀо Omi аккаунтал
  бокьаралбу. Амма профилялъул гьесул credential ва API base буго.
* ХӀалтӀизабе `--api-base http://localhost:8080` локалияб backend тесталъе.
* ХӀалтӀизабе `OMI_LOCAL_API_URL` ва `OMI_LOCAL_TOKEN` профилялъул локалиял
  Desktop API параметрал цо рекъон хисизе.
* ХӀалтӀизабе `--verbose` отладкаялъе — гьеса `METHOD path → status (Ns)`
  stderr-алде тола stdout щитӀизабичӀого, JSON режим чӀун квеша.
* Контент беседе къотӀизе, хӀалтӀизабе `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
