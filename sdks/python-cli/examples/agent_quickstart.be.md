# omi-cli для агентаў

> Практычнае кіраўніцтва для сістэм на базе LLM (Claude Code, Cursor, вашы ўласныя боты).

## Чаму CLI зручны для агентаў

* **Стабільны JSON-кантракт.** Сцяг `--json` выводзіць валідны JSON-дакумент у stdout і
  *толькі* JSON-дакумент — без паведамленняў пра прагрэс, без спінераў. Памылкі выводзяцца ў
  stderr у фармаце `{"error": "...", "detail": "..."}`.
* **Стабільныя коды выхаду (Exit Codes).** `0` паспяхова / `1` выкарыстанне / `2` аўтэнтыфікацыя / `3` сервер / `4` ліміт
  запытаў / `5` не знойдзена. Агенты могуць галінавацца па гэтых кодах без аналізу
  памылак на натуральнай мове.
* **Без інтэрактыўных запытаў у headless-асяроддзях.** Перадайце `--yes` (або `-y`)
  дэструктыўным камандам; перадайце `--api-key` або задайце `OMI_API_KEY`, каб прапусціць
  інтэрактыўны ўваход.
* **Прадказальныя паўторныя спробы.** Памылкі `429` і `5xx` аўтаматычна паўтараюцца з
  экспанентнай затрымкай перад з'яўленнем.

## Аўтэнтыфікацыя (адзін раз, чалавекам)

Карыстальнік атрымлівае API-ключ распрацоўшчыка з вэб-праграмы Omi
(`https://app.omi.me` → Developer → API Keys) і робіць адно з двух:

```bash
omi auth login                          # інтэрактыўная ўстаўка; ключ не захоўваецца ў гісторыі
# або
export OMI_API_KEY=omi_dev_...          # часовы, зручны для кантэйнераў
```

## Пяць дзеянняў, якія агенты выконваюць часцей за ўсё

### 1. Чытанне ўспамінаў

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Стварэнне ўспаміну

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Чытанне размоў

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Чытанне адкрытых задач

```bash
omi action-item list --json --open
```

### 5. Пазначэнне задачы як выкананай

```bash
omi action-item complete --json a1b2c3d4
```

## Лакальны Desktop API

Калі Omi Desktop адкрывае свой лакальны API, агенты могуць рабіць запыты да гісторыі экрана
на прыладзе, рэзюмэ, SQL і задач без выкарыстання воблачнага API распрацоўшчыка:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# або для часовых сесій:
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

Выконвайце або выдаляйце задачы толькі тады, калі карыстальнік выразна пра гэта просіць:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

Каманда `omi local screenshot SCREENSHOT_ID --output PATH` запісвае скрыншот на
дыск і па-ранейшаму выводзіць JSON у stdout для скрыптоў. ID скрыншота звычайна
паходзіць з `local search-screen` або SQL-запыту да табліцы `screenshots`. Калі Desktop
вяртае структураваную памылку, напрыклад `screenshot_pending`, `screenshot_file_missing`,
або `screenshot_chunk_corrupted`, рэжым JSON захоўвае палі `reason`, `hint` і
`screenshot_id` у stderr, каб агенты маглі паўтарыць стары ID або паведаміць пра
дакладную перашкоду. Правярайце паспяховыя вынікі з дапамогай `file PATH` перад перадачай
у інструменты зроку.

## Практычны прыклад: цыкл агента на Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Выклікаць omi CLI у рэжыме JSON з узбуджэннем памылкі пры непаспяховых кодах выхаду."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI выводзіць структураваныя памылкі ў stderr у рэжыме JSON:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Прачытаць усе адкрытыя задачы і пазначыць выкананымі ўсе задачы, старэйшыя за 30 дзён.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Кіраванне лімітамі запытаў (Rate limits)

Успаміны: 120/гадз. Размовы: 25/гадз. Пакетнае стварэнне: 15/гадз.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # перавышаны ліміт запытаў
    err = json.loads(result.stderr)
    # err["detail"] выглядае як: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Парады

* Выкарыстоўвайце `--profile <імя>`, калі ваш агент кіруе некалькімі акаўнтамі Omi. Кожны
  профіль мае свае ўліковыя даныя і базу API.
* Выкарыстоўвайце `--api-base http://localhost:8080` для лакальнага тэсціравання бэкенда.
* Выкарыстоўвайце `OMI_LOCAL_API_URL` і `OMI_LOCAL_TOKEN` для перавызначэння налад Desktop API
  лакальнага профілю на адзін запуск.
* Выкарыстоўвайце `--verbose` для адладкі — гэта запісвае `METHOD path → status (Ns)` у stderr
  без уплыву на stdout, захоўваючы валіднасць рэжыму JSON.
* Для перанакіравання кантэнту ў размову выкарыстоўвайце `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
