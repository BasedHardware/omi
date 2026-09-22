# omi-cli барои агентҳо

> Дастури амалӣ барои системаҳои зери идораи LLM (Claude Code, Cursor, ботҳои шахсӣ).

## Чаро CLI барои агентҳо мувофиқ аст

* **Шартномаи устувори JSON.** Параметри `--json` ба баромади стандартӣ (stdout) ҳуҷҷати
  дурусти JSON ва *танҳо* ҳуҷҷати JSON-ро мебарорад — бидуни паёмҳои иҷроиш ё аниматсияҳо.
  Хатогиҳо ба ҷараёни стандартии хатогӣ (stderr) дар шакли `{"error": "...", "detail": "..."}`
  фиристода мешаванд.
* **Кодҳои устувори баромад (exit codes).** `0` муваффақ / `1` хатои истифода / `2` аутентификатсия /
  `3` хатои сервер / `4` маҳдудияти дархост (rate limited) / `5` ёфт нашуд. Агентҳо метавонанд
  бидуни таҳлили хатогиҳои матнӣ мустақиман аз рӯи ин кодҳо амал кунанд.
* **Набудани дархостҳои интерактивӣ дар муҳитҳои бе сарлавҳа (headless).** Ба фармонҳои тағйирдиҳанда
  `--yes` (ё `-y`) илова кунед; барои гузаштан аз вуруди интерактивӣ `--api-key`-ро фиристед ё
  тағйирёбандаи `OMI_API_KEY`-ро танзим кунед.
* **Рафтори мусоиди такрори санҷиш.** Хатогиҳои `429` ва `5xx` пеш аз намоиш дода шудан бо фосилаи
  афзоянда ба таври худкор дубора кӯшиш карда мешаванд.

## Аутентификатсия (як маротиба аз ҷониби корбар)

Корбар калиди API-и таҳиягарро аз барномаи веби Omi мегирад
(`https://app.omi.me` → Developer → API Keys) ва яке аз ин амалҳоро иҷро мекунад:

```bash
omi auth login                          # гузоштани интерактивӣ; калид дар таърихи терминал намемонад
# ё
export OMI_API_KEY=omi_dev_...          # муваққатӣ, мувофиқ барои контейнерҳо
```

## Панҷ амали асосие, ки агентҳо иҷро мекунанд

### 1. Хониши хотираҳо

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Эҷоди хотира

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Хониши гуфтугӯҳо

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Хониши вазифаҳои боз

```bash
omi action-item list --json --open
```

### 5. Анҷом додани вазифа

```bash
omi action-item complete --json a1b2c3d4
```

## API-и маҳаллии Desktop

Вақте ки Omi Desktop API-и маҳаллии худро фаъол мекунад, агентҳо метавонанд таърихи экран,
хулосаҳо, маълумоти SQL ва вазифаҳоро дар дохили дастгоҳ бе истифодаи API-и абрӣ дархост кунанд:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# ё барои сессияҳои муваққатӣ:
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

Вазифаҳоро танҳо ҳангоме ки корбар мушаххас дархост мекунад, анҷом диҳед ё нест кунед:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` акси экранро ба диск менависад ва
барои скриптҳо ба stdout баровардани JSON-ро давом медиҳад. Идентификатори акси экран маъмулан
аз `local search-screen` ё дархости SQL аз ҷадвали `screenshots` ба даст меояд. Агар Desktop
хатои сохториро ба мисли `screenshot_pending`, `screenshot_file_missing` ё `screenshot_chunk_corrupted`
баргардонад, ҳолати JSON майдонҳои `reason`, `hint` ва `screenshot_id`-ро дар stderr нигоҳ медорад,
то агентҳо тавонанд бо ID-и пешина такрор кунанд ё монеаи дақиқро гузориш диҳанд. Натиҷаҳои бомуваффақиятро
пеш аз интиқол ба абзорҳои биноӣ бо `file PATH` санҷед.

## Намунаи амалӣ: Сикли агенти Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """omi CLI-ро дар ҳолати JSON даъват мекунад ва ҳангоми хато истисно эҷод мекунад."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI дар ҳолати JSON хатогиҳои сохториро ба stderr мебарорад:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Ҳама вазифаҳои кушодаро хонед ва онҳоеро, ки аз 30 рӯз калонанд, анҷомшуда қайд кунед.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Идоракунии маҳдудиятҳои дархост

Хотираҳо: 120/соат. Гуфтугӯҳо: 25/соат. Эҷоди дастаҷамъӣ: 15/соат.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # маҳдудияти дархост фаро расид
    err = json.loads(result.stderr)
    # err["detail"] чунин менамояд: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Маслиҳатҳо

* Агар агенти шумо бо якчанд ҳисоби Omi кор кунад, аз `--profile <ном>` истифода баред.
  Ҳар як профил эътиборнома ва пойгоҳи API-и шахсии худро дорад.
* Барои санҷиши сервери маҳаллӣ `--api-base http://localhost:8080`-ро истифода баред.
* Барои иҷрои якдафъаина танзимоти маҳаллии Desktop API-ро бо `OMI_LOCAL_API_URL` ва
  `OMI_LOCAL_TOKEN` иваз намоед.
* Барои ислоҳи хатогиҳо (debugging) `--verbose`-ро истифода баред — он бе таъсир ба stdout
  маълумоти `METHOD path → status (Ns)`-ро ба stderr менависад ва ҳолати JSON халалдор намешавад.
* Барои интиқоли мундариҷа ба гуфтугӯ `--text -`-ро истифода баред:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
