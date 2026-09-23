# omi-cli fyrir vinnufugla

> Hagnýt leiðbeining fyrir LLM-ækka (Claude Code, Cursor, þínir eigin botar).

## Af hvervi CLI er vinnufuglavænt

* **Stöðugt JSON samning.** `--json` sendir gilt JSON skjal á stdout og
  *einungis* JSON skjal — engin skilaboð um framvindu, engir spinners. Villur fara á
  stderr sem `{"error": "...", "detail": "..."}`.
* **Stöðugar útgangskóðar.** `0` ok / `1` notkun / `2` auth / `3` þjónn / `4`
  tíðni takmörk / `5` fannst ekki. Vinnufuglar geta greint á þessum án þess að greina
  villur á náttúrulegu máli.
* **Engir gagnvirkir spurningar í headless umhverfi.** Sendu `--yes` (eða `-a`) til
  eyðileggjandi skipana; sendu `--api-key` eða stilltu `OMI_API_KEY` til að sleppa
  gagnvirkri innskráningu.
* **Gefandi tilraunir.** `429` og `5xx` eru reind aftur með backoff
  áður en þau birtast.

## Auth (eina sinni, af manneskju)

Notandanum fæst þróunar API lykill úr Omi vefforritinu
(`https://app.omi.me` → Developer → API Keys) og annaðhvort:

```bash
omi auth login                          # interactive paste; key not in shell history
# or
export OMI_API_KEY=omi_dev_...          # ephemeral, container-friendly
```

## Fimm hlutirnir sem vinnufuglar gera oftast

### 1. Lesa minningar

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Búa til minningu

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Lesa samræður

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Lesa opnar aðgerðir

```bash
omi action-item list --json --open
```

### 5. Merkja aðgerð sem kláraða

```bash
omi action-item complete --json a1b2c3d4
```

## Staðbundin Desktop API

Þegar Omi Desktop opnar staðbundna API sína geta vinnufuglar flett í skjáferil
tækis, yfirlit, SQL og verkefni án þess að nota skýjar API:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# or, for ephemeral sessions:
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

Kláraðu eða eyddu verkefnum aðeins þegar notandinn biður skýrt:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` skrifar skjámynd á disk og
prentar enn JSON á stdout fyrir skriftir. Skjámyndar-ID kemur venjulega úr
`local search-screen` eða SQL yfir `screenshots` töfluna. Ef Desktop skilar
uppbyggðri villu eins og `screenshot_pending`, `screenshot_file_missing`
eða `screenshot_chunk_corrupted` varðveitir JSON hamsvið `reason`, `hint` og
`screenshot_id` á stderr svo vinnufuglar geti reint eldri ID eða tilkynnt nákvæman
hindrun. Staðfestu heppnar úttöki með `file PATH` áður en þú sendir þau til
sjónverkfæra.

## Praksis dæmi: Python vinnufuglslykkja

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

## Meðhöndlun tíðn takmarka

Minningar: 120/klst. Samræður: 25/klst. Magnbúnaður: 15/klst.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Ábendingar

* Notaðu `--profile <nafn>` ef vinnufugl þinn meðhöndlar marga Omi reikninga. Hvert
  prófíll hefur eigin auðkenni og API base.
* Notaðu `--api-base http://localhost:8080` fyrir staðbundna bakenda prófun.
* Notaðu `OMI_LOCAL_API_URL` og `OMI_LOCAL_TOKEN` til að segja skila stillingum
  Desktop API fyrir prófíl fyrir eina keyrslu.
* Notaðu `--verbose` til að fletta upp villum — skrár `METHOD path → status (Ns)` á stderr
  án þess að hafa áhrif á stdout, svo JSON hamur haldist gildur.
* Til að flytja efni í samræðu, notaðu `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
