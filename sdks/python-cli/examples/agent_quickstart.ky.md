# Агенттер үчүн omi-cli

> LLM башкарган системалар (Claude Code, Cursor, жеке ботторуңуз) үчүн практикалык колдонмо.

## Эмне үчүн CLI агенттер үчүн ыңгайлуу

* **Туруктуу JSON протоколу.** `--json` параметри стандарттык чыгууга (stdout) жарактуу
  JSON документин жана *гана* JSON документин чыгарат — эч кандай аткарылуу билдирүүлөрү,
  жүктөлүү анимациялары жок. Каталар стандарттык каталар агымына (stderr)
  `{"error": "...", "detail": "..."}` түрүндө жөнөтүлөт.
* **Туруктуу чыгуу коддору (exit codes).** `0` ийгиликтүү / `1` колдонуу катасы / `2` аутентификация /
  `3` сервер катасы / `4` суроо-талап чегинен ашуу (rate limited) / `5` табылган жок. Агенттер табигый
  тилдеги каталарды талдабастан, түздөн-түз ушул коддорго таянып чечим кабыл алат.
* **Автономдуу (headless) чөйрөлөрдө интерактивдүү суроолордун жоктугу.** Өчүрүү же өзгөртүү
  буйруктарына `--yes` (же `-y`) бериңиз; интерактивдүү кирүүнү өткөрүп жиберүү үчүн
  `--api-key` бериңиз же `OMI_API_KEY` чөйрө өзгөрмөсүн орнотуңуз.
* **Каталарды кайталап текшерүүнүн ийкемдүү механизми.** `429` жана `5xx` каталары экранга
  чыгарылганга чейин акырындык менен күтүү аркылуу автоматтык түрдө кайталанат.

## Аутентификация (адам бир жолу аткарат)

Колдонуучу Omi веб-тиркемесинен иштеп чыгуучу API ачкычын алат
(`https://app.omi.me` → Developer → API Keys) жана төмөнкүлөрдүн бирин тандайт:

```bash
omi auth login                          # интерактивдүү чаптоо; ачкыч терминал тарыхына жазылбайт
# же
export OMI_API_KEY=omi_dev_...          # убактылуу, контейнерлер үчүн ыңгайлуу
```

## Агенттер эң көп аткарган беш аракет

### 1. Эскерүүлөрдү окуу

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Эскерүү түзүү

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Маектерди окуу

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Ачык тапшырмаларды окуу

```bash
omi action-item list --json --open
```

### 5. Тапшырманы аткарылды деп белгилөө

```bash
omi action-item complete --json a1b2c3d4
```

## Жергиликтүү Desktop API

Omi Desktop жергиликтүү API'син иштеткенде, агенттер булут иштеп чыгуучу API'син колдонбостон
түзмөктөгү экран тарыхын, корутундуларды, SQL маалыматтарын жана тапшырмаларды сурай алат:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# же убактылуу сессиялар үчүн:
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

Тапшырмаларды колдонуучу так суранганда гана аткарыңыз же өчүрүңүз:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` скриншотту дискке жазат жана
скрипттер үчүн stdout'ко JSON чыгарууну улантат. Скриншот идентификатору адатта
`local search-screen` же `screenshots` жадыбалы боюнча SQL суроосунан алынат. Эгер Desktop
`screenshot_pending`, `screenshot_file_missing` же `screenshot_chunk_corrupted` сыяктуу
түзүмдүк ката кайтарса, JSON режими stderr ичинде `reason`, `hint` жана `screenshot_id`
талааларын сактайт, ошентип агенттер эски ID менен кайра аракет кыла алат же тоскоолдукту так
билдире алат. Ийгиликтүү натыйжаларды визуалдык куралдарга жөнөтүүдөн мурун `file PATH` аркылуу текшериңиз.

## Иштөө мисалы: Python агент цикли

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """JSON режиминде omi CLI чакырат, ката коддору учурунда ката козгойт."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI JSON режиминде stderr'ге түзүмдөштүрүлгөн каталарды чыгарат:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Бардык ачык тапшырмаларды окуп, 30 күндөн эски болгондорун аткарылды деп белгилеңиз.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Суроо-талап чектөөлөрүн башкаруу

Эскерүүлөр: 120/саат. Маектер: 25/саат. Топтук түзүү: 15/саат.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # суроо-талап чегинен ашты
    err = json.loads(result.stderr)
    # err["detail"] мындай көрүнөт: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Кеңештер

* Эгер агент бир нече Omi аккаунту менен иштесе, `--profile <name>` параметрин
  колдонуңуз. Ар бир профилдин өз эсептик дайындары жана API базасы болот.
* Жергиликтүү серверди сыноо үчүн `--api-base http://localhost:8080` колдонуңуз.
* Бир жолку иштетүү үчүн профилдин жергиликтүү Desktop API параметрлерин кайра аныктоого
  `OMI_LOCAL_API_URL` жана `OMI_LOCAL_TOKEN` колдонуңуз.
* Түзөтүү (debugging) үчүн `--verbose` колдонуңуз — ал stdout'ко таасир этпестен stderr'ге
  `METHOD path → status (Ns)` жазат, ошондуктан JSON режими бузулбайт.
* Мазмунду маекке багыттоо үчүн `--text -` колдонуңуз:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
