# omi-cli agentidele (Estonian)

> Praktiline juhend LLM-põhistele süsteemidele (Claude Code, Cursor, kohandatud botid).

## Miks see CLI sobib ideaalselt agentidele

* **Stabiilne JSON leping.** `--json` väljastab standardsesse väljundisse (stdout) ainult kehtiva JSON-dokumendi — ilma edenemisteadete või laadimisanimatsioonideta (spinners). Veateated suunatakse standardsesse veavoogu (stderr) kujul `{"error": "...", "detail": "..."}`.
* **Stabiilsed väljundkoodid (Exit codes).** `0` korras / `1` vale kasutus / `2` autentimisviga / `3` serveri viga / `4` päringupiirang ületatud (rate limited) / `5` ei leitud. Agendid saavad teha harunemisotsuseid nende koodide põhjal ilma loomuliku keele teateid analüüsimata.
* **Ei mingeid interaktiivseid viipasid taustarežiimis (headless).** Edastage ohtlikele käskudele lipp `--yes` (või `-y`); edastage `--api-key` või määrake keskkonnamuutuja `OMI_API_KEY`, et vältida interaktiivset sisselogimist.
* **Vigadele vastupidav korduskaitse.** Koodide `429` ja `5xx` puhul tehakse enne vea tagastamist automaatselt korduskatsed eksponentsiaalse viivitusega.

## Autentimine (ühekordne, inimese poolt)

Kasutaja hangib arendaja API võtme Omi veebirakendusest (`https://app.omi.me` → Developer → API Keys) ning seadistab selle:

```bash
omi auth login                          # interaktiivne kleepimine; võti ei jää kesta ajalukku
# või
export OMI_API_KEY=omi_dev_...          # ajutine, sobib konteineritesse (Docker)
```

## Viis peamist toimingut, mida agendid teevad

### 1. Mälestuste lugemine

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Mälestuse loomine

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Vestluste lugemine

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Avatud tegevusüksuste lugemine

```bash
omi action-item list --json --open
```

### 5. Tegevusüksuse lõpetatuks märkimine

```bash
omi action-item complete --json a1b2c3d4
```

## Kohalik töölaua API (Local Desktop API)

Kui Omi Desktop rakendus avab oma kohaliku API, saavad agendid pärida seadmesisest ekraaniajalugu, kokkuvõtteid, SQL-andmeid ja ülesandeid ilma pilve dev-API-t kasutamata:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# või ajutiste seansside jaoks:
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

Märkige ülesanded lõpetatuks või kustutage neid ainult siis, kui kasutaja seda otseselt palub:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

Käsk `omi local screenshot SCREENSHOT_ID --output PATH` salvestab ekraanipildi kettale ning väljastab skriptide jaoks stdout-i kaudu JSON-i. Ekraanipildi ID pärineb tavaliselt käsust `local search-screen` või SQL-päringust üle tabeli `screenshots`. Kui Desktop tagastab struktureeritud tõrke (nt `screenshot_pending`, `screenshot_file_missing` või `screenshot_chunk_corrupted`), säilitab JSON-režiim väljad `reason`, `hint` ja `screenshot_id` stderr-is, võimaldades agentidel proovida vanemat ID-d või teatada täpsest takistusest. Enne failide edastamist visioonitööriistadele kontrollige väljundit käsuga `file PATH`.

## Praktiline näide: Pythoni agendi tsükkel

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Kutsu omi CLI välja JSON-režiimis, tekitades vea mittetulusal väljundkoodil."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI väljastab JSON-režiimis struktureeritud vead stderr-i:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi väljus koodiga {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Loe kõik avatud tegevusüksused ja märgi üle 30 päeva vanused lõpetatuks.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Päringupiirangute käsitlemine (Rate Limits)

Mälestused: 120/tunnis. Vestlused: 25/tunnis. Hulgiloomised (batch): 15/tunnis.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # päringupiirang ületatud
    err = json.loads(result.stderr)
    # err["detail"] näidis: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Nõuanded

* Kasutage `--profile <nimi>`, kui teie agent haldab mitut Omi kontot. Igal profiilil on oma mandaat ja API baasaadress.
* Kasutage `--api-base http://localhost:8080` kohaliku tagarakenduse testimiseks.
* Kasutage muutujaid `OMI_LOCAL_API_URL` ja `OMI_LOCAL_TOKEN`, et alistada profiili kohalikud töölaua API seaded ühe käituse jaoks.
* Silumiseks kasutage lippu `--verbose` — see logib `METHOD tee → olek (Ns)` stderr-i ilma stdout-i mõjutamata, säilitades JSON-režiimi kehtivuse.
* Sisu suunamiseks vestlusesse toru kaudu (piping) kasutage `--text -`:
  ```bash
  cat koosoleku_markmed.md | omi conversation create --text - --text-source other_text
  ```
