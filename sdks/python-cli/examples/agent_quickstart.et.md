# omi-cli agentidele

> Praktiline juhend LLM-i juhitud harnessidele (Claude Code, Cursor, teie enda botidele).

## Miks CLI on agentidele sõbralik

* **Stabiilne JSON-leping.** `--json` väljastab stdout-i kehtiva JSON-dokumendi ja
  *ainult* JSON-dokumendi — edenemissõnumeid ega spinnereid pole. Vead lähevad
  stderr-i kui `{"error": "...", "detail": "..."}`.
* **Stabiilsed väljumiskoodid.** `0` korras / `1` kasutus / `2` auth / `3` server /
  `4` kiiruse piirang / `5` ei leitud. Agendid saavad nende põhjal hargneda ilma
  loomuliku keele vigu parsimata.
* **Interaktiivseid viipasid pole headless-kontekstides.** Edastage `--yes` (või `-y`)
  destruktiivsetele käskudele; edastage `--api-key` või seadistage `OMI_API_KEY`,
  et vahele jätta interaktiivne sisselogimine.
* **Andestav kordamiskäitumine.** `429` ja `5xx` korratakse backoff-iga enne
  pinnale tulekut.

## Auth (üks kord, inimese poolt)

Kasutaja saab dev API-võtme Omi veebirakendusest
(`https://app.omi.me` → Developer → API Keys) ja kas:

```bash
omi auth login                          # interaktiivne kleepimine; võti ei jää shell-i ajalukku
# või
export OMI_API_KEY=omi_dev_...          # ajutine, ideaalne konteineritele
```

## Viis asja, mida agendid kõige rohkem teevad

### 1. Mälude lugemine

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Mälu loomine

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Vestluste lugemine

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Avatud tegevuskohtade lugemine

```bash
omi action-item list --json --open
```

### 5. Tegevuskoha märkimine tehtuks

```bash
omi action-item complete --json a1b2c3d4
```

## Kohalik Desktop API

Kui Omi Desktop avab oma kohaliku API, saavad agendid päringuid teha seadme
ekraanide ajaloo, kokkuvõtete, SQL-i ja ülesannete kohta ilma pilve dev API-t
kasutamata:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# või, ajutiste seansside jaoks:
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

Lõpetage või kustutage ülesanded ainult siis, kui kasutaja seda selgelt palub:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` kirjutab ekraanipildi kettale
ja prindib siiski JSON-i stdout-i skriptide jaoks. Ekraanipildi ID tuleb tavaliselt
`local search-screen`-ist või SQL-ist `screenshots` tabeli pealt. Kui Desktop
tagastab struktureeritud vea nagu `screenshot_pending`, `screenshot_file_missing`
või `screenshot_chunk_corrupted`, säilitab JSON-režiim `reason`, `hint` ja
`screenshot_id` väljad stderr-is, et agendid saaksid proovida vanema ID-ga või
teavitada täpsest takistusest. Kontrollige edukaid väljundeid `file PATH`-iga
enne edastamist visioonitööriistadele.

## Läbitud näide: Pythoni agendi tsükkel

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Invoke the omi CLI in JSON mode, raising on non-success exit codes."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # The CLI prints structured errors to stderr in JSON mode:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Read all open action items and mark anything older than 30 days complete.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Kiiruse piirangute haldamine

Mälud: 120/t. Vestlused: 25/t. Pakkloomised: 15/t.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Nipid

* Kasutage `--profile <name>`, kui teie agent haldab mitut Omi kontot. Igal
  profiilil on oma mandaadid ja API baas.
* Kasutage `--api-base http://localhost:8080` kohalikeks backendi testideks.
* Kasutage `OMI_LOCAL_API_URL` ja `OMI_LOCAL_TOKEN`, et asendada profiili
  kohaliku Desktop API seaded ühe käivituse jaoks.
* Kasutage `--verbose` silumiseks — see logib `METHOD path → status (Ns)` stderr-i
  stdout-i mõjutamata, nii et JSON-režiim jääb kehtima.
* Sisu vestlusse pipe'imiseks kasutage `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
