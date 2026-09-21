# Агенттерге арналған omi-cli

> LLM басқаратын жүйелерге (Claude Code, Cursor, жеке боттарыңыз) арналған практикалық нұсқаулық.

## Неліктен CLI агенттер үшін қолайлы

* **Тұрақты JSON хаттамасы.** `--json` параметрі стандартты шығысқа (stdout) жарамды
  JSON құжатын және *тек* JSON құжатын шығарады — ешқандай орындалу хабарламалары,
  жүктелу анимациялары жоқ. Қателер стандартты қателер ағынына (stderr)
  `{"error": "...", "detail": "..."}` түрінде жіберіледі.
* **Тұрақты шығу кодтары (exit codes).** `0` сәтті / `1` қолдану қатесі / `2` аутентификация /
  `3` сервер қатесі / `4` сұраныс шегінен асу (rate limited) / `5` табылмады. Агенттер табиғи
  тілдегі қателерді талдамай-ақ, осы кодтар негізінде логикалық шешім қабылдай алады.
* **Автономды (headless) орталарда интерактивті сұраулардың болмауы.** Жою немесе өзгерту
  командаларына `--yes` (немесе `-y`) беріңіз; интерактивті кіруді өткізіп жіберу үшін
  `--api-key` беріңіз немесе `OMI_API_KEY` айнымалысын орнатыңыз.
* **Қателерді қайталап тексерудің икемді механизмі.** `429` және `5xx` қателері экранға
  шығарылмас бұрын біртіндеп күту арқылы автоматты түрде қайталанады.

## Аутентификация (адам бір рет орындайды)

Пайдаланушы Omi веб-қолданбасынан әзірлеуші API кілтін алады
(`https://app.omi.me` → Developer → API Keys) және мыналардың бірін таңдайды:

```bash
omi auth login                          # интерактивті қою; кілт терминал тарихына жазылмайды
# немесе
export OMI_API_KEY=omi_dev_...          # уақытша, контейнерлер үшін ыңғайлы
```

## Агенттер жиі орындайтын бес әрекет

### 1. Естеліктерді оқу

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Естелік жасау

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Сөйлесулерді оқу

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Ашық тапсырмаларды оқу

```bash
omi action-item list --json --open
```

### 5. Тапсырманы орындалды деп белгілеу

```bash
omi action-item complete --json a1b2c3d4
```

## Жергілікті Desktop API

Omi Desktop жергілікті API-ін қосқанда, агенттер бұлттық әзірлеуші API-ін пайдаланбай-ақ
құрылғыдағы экран тарихын, қорытындыларды, SQL деректерін және тапсырмаларды сұрай алады:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# немесе уақытша сессиялар үшін:
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

Тапсырмаларды тек пайдаланушы нақты сұраған кезде ғана орындаңыз немесе жойыңыз:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` скриншотты дискіге жазады және
скрипттер үшін stdout-қа JSON басып шығаруды жалғастырады. Скриншот идентификаторы әдетте
`local search-screen` немесе `screenshots` кестесі бойынша SQL сұрауынан алынады. Егер Desktop
`screenshot_pending`, `screenshot_file_missing` немесе `screenshot_chunk_corrupted` сияқты
құрылымдық қате қайтарса, JSON режимі stderr ішінде `reason`, `hint` және `screenshot_id`
өрістерін сақтайды, осылайша агенттер ескі ID-мен қайталап көре алады немесе нақты кедергіні
хабарлай алады. Сәтті нәтижелерді визуалды құралдарға жібермес бұрын `file PATH` арқылы тексеріңіз.

## Жұмыс мысалы: Python агент циклі

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """JSON режимінде omi CLI шақырады, қате кодтары кезінде ерекшелік тудырады."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI JSON режимінде stderr-ге құрылымдалған қателерді шығарады:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Барлық ашық тапсырмаларды оқып, 30 күннен асқандарын орындалды деп белгілеңіз.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Сұраныс шектеулерін басқару

Естеліктер: 120/сағ. Сөйлесулер: 25/сағ. Топтық жасау: 15/сағ.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # сұраныс шегінен асты
    err = json.loads(result.stderr)
    # err["detail"] мынадай: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Кеңестер

* Егер агентіңіз бірнеше Omi тіркелгісімен жұмыс істесе, `--profile <name>` параметрін
  пайдаланыңыз. Әр профильдің өз тіркелгі деректері мен API негізі болады.
* Жергілікті серверді сынау үшін `--api-base http://localhost:8080` пайдаланыңыз.
* Бір реттік іске қосу үшін профильдің жергілікті Desktop API параметрлерін қайта анықтауға
  `OMI_LOCAL_API_URL` және `OMI_LOCAL_TOKEN` пайдаланыңыз.
* Түзету (debugging) үшін `--verbose` пайдаланыңыз — ол stdout-қа әсер етпестен stderr-ге
  `METHOD path → status (Ns)` жазады, осылайша JSON режимі жарамды болып қалады.
* Мазмұнды сөйлесуге жіберу үшін `--text -` пайдаланыңыз:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
