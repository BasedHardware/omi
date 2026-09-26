# i-omi-cli yama-agent

> Umhlahlandlela osebenzayo wama-harness e-LLM (Claude Code, Cursor, ama-bot akho).

## Kungani i-CLI ilungele ama-agent

* **Isivumelwano se-JSON esizinzile.** I-`--json` ikhipha idokhumenti ye-JSON evumelekile
  ku-stdout futhi *idokhumenti ye-JSON kuphela* — ayikho imilayezo yenqubekela phambili,
  awekho ama-spinner. Amaphutha aya ku-stderr njengo `{"error": "...", "detail": "..."}`.
* **Amakhodi okuphuma azinzile.** `0` kuhle / `1` ukusetshenziswa / `2` ukuqinisekisa /
  `3` iseva / `4` umkhawulo wejubane / `5` akutholakalanga. Ama-agent angahlukanisa
  kulawa makhodi ngaphandle kokuhlaziya amaphutha olimi lwemvelo.
* **Awekho ama-prompt okusebenzisana ezimweni ze-headless.** Dlulisa i-`--yes` (noma `-y`)
  kumakhomandi abhubhisayo; dlulisa i-`--api-key` noma setha i-`OMI_API_KEY` ukuze weqe
  ukungena okusebenzisanayo.
* **Ukuziphatha kokuzama kabusha okubekezelayo.** Ama-`429` nama-`5xx` azanywa kabusha
  nge-backoff ngaphambi kokuvela.

## Ukuqinisekisa (kanye, ngumuntu)

Umsebenzisi uthola ukhiye we-dev API kusuka ku-Omi web app
(`https://app.omi.me` → Developer → API Keys) bese kwenza okukodwa kwalokhu:

```bash
omi auth login                          # ukunamathisela okusebenzisanayo; ukhiye awukho emlandweni we-shell
# noma
export OMI_API_KEY=omi_dev_...          # kwesikhashana, kufanelekile ku-container
```

## Izinto ezinhlanu ama-agent azenza kakhulu

### 1. Funda ama-memory

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Dala i-memory

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Funda izingxoxo

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Funda izinto zesenzo ezivuliwe

```bash
omi action-item list --json --open
```

### 5. Maka into yesenzo njengeqediwe

```bash
omi action-item complete --json a1b2c3d4
```

## I-Local Desktop API

Uma i-Omi Desktop iveza i-local API yayo, ama-agent angabuza umlando wesikrini
osukudivayisi, ama-recap, i-SQL, nemisebenzi ngaphandle kokusebenzisa i-cloud dev API:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# noma, kumaseshini esikhashana:
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

Qedela noma susa imisebenzi kuphela uma umsebenzisi ecela ngokusobala:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

I-`omi local screenshot SCREENSHOT_ID --output PATH` ibhala isithombe-skrini kudiski
futhi isaphrinta i-JSON ku-stdout yama-script. I-ID yesithombe-skrini ivamise ukuvela
ku-`local search-screen` noma i-SQL kuthebula le-`screenshots`. Uma i-Desktop ibuyisela
ukwehluleka okuhlelekile okufana ne-`screenshot_pending`, `screenshot_file_missing`,
noma i-`screenshot_chunk_corrupted`, imodi ye-JSON igcina izinkambu ze-`reason`,
`hint`, ne-`screenshot_id` ku-stderr ukuze ama-agent akwazi ukuzama kabusha i-ID endala
noma ukubika isithiyo esiqondile. Qinisekisa imiphumela ephumelelayo nge-`file PATH`
ngaphambi kokudlulisela kumathuluzi okubona.

## Isibonelo esisetshenziwe: I-loop ye-agent ye-Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Biza i-omi CLI kumodi ye-JSON, ukhipha i-exception kumakhodi okuphuma angaphumelelanga."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # I-CLI iphrinta amaphutha ahlelekile ku-stderr kumodi ye-JSON:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Funda zonke izinto zesenzo ezivuliwe futhi umake noma yini endala kunezinsuku ezingu-30 njengeqediwe.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Ukubhekana nemikhawulo yejubane

Ama-memory: 120/hr. Izingxoxo: 25/hr. Ukudalwa kweqoqo: 15/hr.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # umkhawulo wejubane
    err = json.loads(result.stderr)
    # i-err["detail"] ibukeka kanje: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Amathiphu

* Sebenzisa i-`--profile <name>` uma i-agent yakho iphethe ama-akhawunti amaningi
  e-Omi. Iphrofayela ngayinye inokufakazela kwayo kanye nesisekelo se-API.
* Sebenzisa i-`--api-base http://localhost:8080` ekuhloleni i-backend yasendaweni.
* Sebenzisa i-`OMI_LOCAL_API_URL` ne-`OMI_LOCAL_TOKEN` ukweqa izilungiselelo
  ze-Desktop API zephrofayela ngokwesikhathi esisodwa.
* Sebenzisa i-`--verbose` ekulungiseni amaphutha — iloga i-`METHOD path → status (Ns)`
  ku-stderr ngaphandle kokuphazamisa i-stdout, ngakho imodi ye-JSON ihlala ivumelekile.
* Ukuze udlulise okuqukethwe engxoxweni ngepayipi, sebenzisa i-`--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
