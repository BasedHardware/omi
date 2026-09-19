# omi-cli agentidele

> Praktiline juhend LLM-põhistele tööriistadele (Claude Code, Cursor, teie enda robotid).

## Miks CLI on agendisõbralik

* **Stabiilne JSON-leping.** `--json` väljastab stdout-i kehtiva JSON-dokumendi ja
  *ainult* JSON-dokumendi — ilma edenemisteadete või laadimisikoonideta. Vead väljastatakse
  stderr-i kujul `{"error": "...", "detail": "..."}`.
* **Stabiilsed väljumiskoodid.** `0` korras / `1` kasutusviga / `2` autentimine / `3` serveri viga / `4` päringupiirang / `5` ei leitud. Agendid saavad nende põhjal haruneda ilma loomuliku keele veateateid analüüsimata.
* **Taustakontekstis puuduvad interaktiivsed viibad.** Edastage `--yes` (või `-y`)
  destruktiivsetele käskudele; interaktiivse sisselogimise vahelejätmiseks edastage `--api-key` või määrake `OMI_API_KEY`.
* **Vigu andestav uuesti proovimine.** Koodide `429` ja `5xx` korral proovitakse enne vea kuvamist
  automaatselt viivitusega uuesti.

## Autentimine (ühekordne, inimese poolt)

Kasutaja hangib Omi veebirakendusest arendaja API-võtme
(`https://app.omi.me` → Developer → API Keys) ja teeb ühe järgmistest:

```bash
omi auth login                          # interaktiivne kleepimine; võtit ei salvestata käsuajalukku
# või
export OMI_API_KEY=omi_dev_...          # ajutine, konteinerisõbralik
```

## Viis asja, mida agendid kõige sagedamini teevad

### 1. Loe mälestusi

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Loo mälestus

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Loe vestlusi

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Loe avatud tegevusüksusi

```bash
omi action-item list --json --open
```

### 5. Märgi tegevusüksus tehtuks

```bash
omi action-item complete --json a1b2c3d4
```

## Kohalik Töölaua API (Desktop API)

Kui Omi Desktop teeb kättesaadavaks oma kohaliku API, saavad agendid pärida seadme ekraaniajalugu,
kokkuvõtteid, SQL-i ja ülesandeid ilma pilve-API-t kasutamata:

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

Märkige ülesandeid tehtuks või kustutage neid ainult siis, kui kasutaja seda selgelt palub:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

Käsk `omi local screenshot SCREENSHOT_ID --output PATH` kirjutab kuvatõmmise
kettale ja väljastab skriptide jaoks stdout-i endiselt JSON-i. Kuvatõmmise ID pärineb tavaliselt
käsust `local search-screen` või SQL-päringust tabelist `screenshots`. Kui Desktop
tagastab struktureeritud tõrke nagu `screenshot_pending`, `screenshot_file_missing`
või `screenshot_chunk_corrupted`, säilitab JSON-režiim väljad `reason`, `hint` ja
`screenshot_id` stderr-is, võimaldades agentidel proovida vanemat ID-d või teatada
täpsest takistusest. Enne visuaalsetele tööriistadele edastamist kinnitage õnnestunud väljundid käsuga `file PATH`.

## Läbitöötatud näide: Pythoni agenditsükkel

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Käivita omi CLI JSON-režiimis, tekitades tõrgete korral erindi."""
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
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Loe kõik avatud tegevusüksused ja märgi üle 30 päeva vanused tehtuks.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Päringupiirangute (rate limits) haldamine

Mälestused: 120/tund. Vestlused: 25/tund. Hulgiloomised: 15/tund.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # päringupiirang ületatud
    err = json.loads(result.stderr)
    # err["detail"] näeb välja selline: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Näpunäited

* Kasutage lippu `--profile <nimi>`, kui teie agent haldab mitut Omi kontot. Igal
  profiilil on oma autentimisandmed ja API baasaadress.
* Kohaliku taustaprogrammi testimiseks kasutage `--api-base http://localhost:8080`.
* Kasutage muutujaid `OMI_LOCAL_API_URL` ja `OMI_LOCAL_TOKEN`, et tühistada profiili kohalikud
  Desktop API seaded ühe käivituse ajaks.
* Silumiseks kasutage lippu `--verbose` — see logib `METHOD path → status (Ns)` stderr-i
  ilma stdout-i mõjutamata, tagades JSON-režiimi kehtivuse.
* Sisu suunamiseks vestlusse kasutage lippu `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
