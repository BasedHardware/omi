# omi-cli գործակալների (agents) համար

> Գործնական ուղեցույց LLM-ով աշխատող համակարգերի համար (Claude Code, Cursor, ձեր սեփական բոտերը):

## Ինչու է CLI-ն հարմար գործակալների համար

* **Կայուն JSON պայմանագիր:** `--json` դրոշակը stdout-ում արտածում է վավեր JSON փաստաթուղթ
  և *միայն* JSON փաստաթուղթ — առանց առաջընթացի հաղորդագրությունների կամ սպիներների: Սխալները
  ուղարկվում են stderr որպես `{"error": "...", "detail": "..."}`:
* **Ելքի կայուն կոդեր (Exit Codes):** `0` հաջող / `1` օգտագործում / `2` վավերացում / `3` սերվեր / `4` հարցումների
  սահմանափակում / `5` չի գտնվել: Գործակալները կարող են ճյուղավորվել ըստ դրանց՝ առանց բնական
  լեզվով սխալները վերլուծելու:
* **Առանց ինտերակտիվ հարցումների headless միջավայրերում:** Փոխանցեք `--yes` (կամ `-y`)
  ջնջող հրամաններին; փոխանցեք `--api-key` կամ սահմանեք `OMI_API_KEY` ինտերակտիվ մուտքը
  բաց թողնելու համար:
* **Ներողամիտ կրկնափորձի վարքագիծ:** `429` և `5xx` սխալները ինքնաբերաբար կրկնվում են
  աստիճանական դադարով նախքան սխալ գրանցելը:

## Վավերացում (մեկ անգամ, մարդու կողմից)

Օգտատերը ստանում է ծրագրավորողի API բանալի Omi վեբ հավելվածից
(`https://app.omi.me` → Developer → API Keys) և կատարում հետևյալներից մեկը.

```bash
omi auth login                          # ինտերակտիվ տեղադրում; բանալին չի պահպանվում պատմության մեջ
# կամ
export OMI_API_KEY=omi_dev_...          # կարճաժամկետ, հարմար կոնտեյներների համար
```

## Հինգ գործողություններ, որոնք գործակալներն ամենաշատն են կատարում

### 1. Կարդալ հիշողությունները

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Ստեղծել հիշողություն

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Կարդալ խոսակցությունները

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Կարդալ բաց առաջադրանքները

```bash
omi action-item list --json --open
```

### 5. Նշել առաջադրանքը որպես կատարված

```bash
omi action-item complete --json a1b2c3d4
```

## Տեղական Desktop API

Երբ Omi Desktop-ը հասանելի է դարձնում իր տեղական API-ն, գործակալները կարող են հարցում կատարել
սարքի էկրանի պատմությանը, ամփոփումներին, SQL-ին և առաջադրանքներին՝ առանց ամպային API-ի.

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# կամ կարճաժամկետ սեսիաների համար.
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

Ավարտեք կամ ջնջեք առաջադրանքները միայն այն դեպքում, երբ օգտատերը հստակ խնդրում է.

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` հրամանը գրում է սքրինշոթը սկավառակի
վրա և շարունակում է տպել JSON stdout-ում սկրիպտների համար: Սքրինշոթի ID-ն սովորաբար
ստացվում է `local search-screen`-ից կամ `screenshots` աղյուսակի SQL հարցումից: Եթե Desktop-ը
վերադարձնում է կառուցվածքային սխալ, օրինակ՝ `screenshot_pending`, `screenshot_file_missing`,
կամ `screenshot_chunk_corrupted`, JSON ռեժիմը պահպանում է `reason`, `hint`, և
`screenshot_id` դաշտերը stderr-ում, որպեսզի գործակալները կարողանան կրկին փորձել հին ID-ն
կամ զեկուցել հստակ խնդիրը: Վավերացրեք հաջող ելքերը `file PATH` հրամանով՝ նախքան դրանք
տեսողական գործիքներին փոխանցելը:

## Գործնական օրինակ. Python գործակալի ցիկլ

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Կանչել omi CLI-ն JSON ռեժիմով՝ բարձրացնելով սխալ ոչ հաջող ելքի կոդերի դեպքում:"""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI-ն տպում է կառուցվածքային սխալներ stderr-ում JSON ռեժիմում.
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Կարդալ բոլոր բաց առաջադրանքները և ավարտված նշել 30 օրից հին ցանկացած առաջադրանք:
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Հարցումների սահմանաչափի (Rate limits) կառավարում

Հիշողություններ՝ 120/ժամ: Խոսակցություններ՝ 25/ժամ: Խմբային ստեղծում՝ 15/ժամ:

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # սահմանաչափը գերազանցվել է
    err = json.loads(result.stderr)
    # err["detail"] ունի հետևյալ տեսքը. "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Խորհուրդներ

* Օգտագործեք `--profile <անուն>`, եթե ձեր գործակալը կառավարում է մի քանի Omi հաշիվներ:
  Յուրաքանչյուր պրոֆիլ ունի իր սեփական հավատարմագրերը և API բազան:
* Օգտագործեք `--api-base http://localhost:8080` տեղական բեքենդի թեստավորման համար:
* Օգտագործեք `OMI_LOCAL_API_URL` և `OMI_LOCAL_TOKEN`՝ մեկ գործարկման համար տեղական
  Desktop API-ի կարգավորումները վերասահմանելու համար:
* Օգտագործեք `--verbose` դեբագի համար — այն գրանցում է `METHOD path → status (Ns)`
  stderr-ում՝ չազդելով stdout-ի վրա, հետևաբար JSON ռեժիմը մնում է վավեր:
* Բովանդակությունը խոսակցության մեջ ուղղորդելու համար (pipe) օգտագործեք `--text -`.
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
