# omi-cli fyrir gervigreindarfulltrúa

> Hagnýt handbók fyrir LLM-drifin kerfi (Claude Code, Cursor, eigin vélmenni).

## Hvers vegna CLI er hentugt fyrir gervigreindarfulltrúa

* **Stöðugur JSON-samningur.** `--json` rofinn skilar gildu JSON-skjali á stdout og
  *eingöngu* JSON-skjali — engin framvinduskilaboð, engir hleðsluhringir. Villur eru sendar
  á stderr sem `{"error": "...", "detail": "..."}`.
* **Stöðug skilakóðar.** `0` í lagi / `1` notkunarvilla / `2` auðkenning / `3` netþjónsvilla /
  `4` beiðnatakmörkun náð / `5` fannst ekki. Fulltrúar geta greinst beint út frá þessum kóðum
  án þess að þurfa að þátta textavillur á náttúrulegu máli.
* **Engar gagnvirkar kvaðningar í headless-umhverfi.** Sendu `--yes` (eða `-y`) með eyðandi
  skipunum; sendu `--api-key` eða skilgreindu `OMI_API_KEY` til að sleppa gagnvirkri innskráningu.
* **Umgjörð sem sýnir þolinmæði við endurteknar tilraunir.** Villur af gerðinni `429` og `5xx`
  eru endurteknar sjálfkrafa með veldisvísis biðtíma (backoff) áður en þær eru tilkynntar.

## Auðkenning (í eitt skipti, af manneskju)

Notandinn sækir forritara API-lykil úr Omi-vefforritinu
(`https://app.omi.me` → Developer → API Keys) og gerir annað hvort:

```bash
omi auth login                          # gagnvirk líming; lykillinn er ekki vistaður í skeljasögu
# eða
export OMI_API_KEY=omi_dev_...          # tímabundið, hentugt fyrir gáma
```

## Fimm algengustu aðgerðir fulltrúa

### 1. Lesa minningar

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Búa til minningu

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Lesa samtöl

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Lesa opna aðgerðaliði

```bash
omi action-item list --json --open
```

### 5. Merkja aðgerðalið sem lokið

```bash
omi action-item complete --json a1b2c3d4
```

## Staðbundið Desktop API

Þegar Omi Desktop virkjar staðbundið API sitt geta fulltrúar lagt fram fyrirspurnir um
skjásögu tækisins, samantektir, SQL-gögn og verkefni án þess að nota skýja-dev API:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# eða fyrir tímabundnar lotur:
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

Ljúktu eða eyddu verkefnum aðeins þegar notandinn biður sérstaklega um það:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

Skipunin `omi local screenshot SCREENSHOT_ID --output PATH` vistar skjámynd á diski
og prentar áfram JSON á stdout fyrir skriftur. Skjámyndar-ID kemur venjulega úr
`local search-screen` eða SQL-fyrirspurn á `screenshots` töfluna. Ef Desktop skilar skipulögðu
fráviki eins og `screenshot_pending`, `screenshot_file_missing` eða `screenshot_chunk_corrupted`,
varðveitir JSON-hamur reitina `reason`, `hint` og `screenshot_id` á stderr svo fulltrúar geti
reynt eldra ID eða tilkynnt nákvæma hindrun. Staðfestu gildar úttaksskrár með `file PATH`
áður en þær eru sendar áfram í sjónrænar gervigreindarskrár.

## Raunhæft dæmi: Python-fulltrúalykkja

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

## Meðhöndlun á beiðnatakmörkunum (Rate Limits)

Minningar: 120/klst. Samtöl: 25/klst. Hópgerðir: 15/klst.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Ábendingar

* Notaðu `--profile <name>` ef fulltrúinn þinn stýrir mörgum Omi-reikningum. Hver
  prófíll hefur sín eigin auðkenni og API-grunn.
* Notaðu `--api-base http://localhost:8080` fyrir staðbundnar bakendaprófanir.
* Notaðu umhverfisbreyturnar `OMI_LOCAL_API_URL` og `OMI_LOCAL_TOKEN` til að hnekkja
  staðbundnum Desktop API stillingum prófíls fyrir eina keyrslu.
* Notaðu `--verbose` við villuleit — skráir `METHOD path → status (Ns)` á stderr
  án þess að hafa áhrif á stdout, þannig að JSON-hamurinn haldist gildur.
* Til að beina efni inn í samtöl skaltu nota `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
