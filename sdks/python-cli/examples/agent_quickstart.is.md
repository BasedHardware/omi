# omi-cli fyrir gervigreindarforrit (agenta)

> Hagnýt handbók fyrir LLM-drifin verkfæri (Claude Code, Cursor, eigin þjarka).

## Af hverju skipanalínan er hentug fyrir gervigreind

* **Stöðugt JSON-snið.** `--json` skilar gildu JSON-skjali á stdout og
  *eingöngu* JSON-skjali — engin framvinduskilaboð eða hreyfimyndir. Villur fara á
  stderr sem `{"error": "...", "detail": "..."}`.
* **Stöðugir lokakóðar.** `0` í lagi / `1` notkunarvilla / `2` auðkenningarvilla / `3` netþjónsvilla / `4` hraðatakmörkun / `5` fannst ekki. Forrit geta tekið ákvarðanir út frá þessum kóðum án þess að þurfa að þátta villuboð á náttúrulegu máli.
* **Engar gagnvirkar spurningar í sjálfvirkum keyrslum.** Notaðu `--yes` (eða `-y`) fyrir
  aðgerðir sem eyða gögnum; notaðu `--api-key` eða stilltu `OMI_API_KEY` til að sleppa
  gagnvirkri innskráningu.
* **Sveigjanleg endurtekningarhegðun.** Kóðar `429` og `5xx` eru reyndir aftur með vaxandi biðtíma
  áður en villu er kastað.

## Auðkenning (einu sinni, af notanda)

Notandinn sækir API-lykil forritara í Omi-vefforritinu
(`https://app.omi.me` → Developer → API Keys) og velur annað hvort:

```bash
omi auth login                          # gagnvirk líming; lykillinn vistar sig ekki í skipanaferli
# eða
export OMI_API_KEY=omi_dev_...          # tímabundið, hentar vel fyrir gáma
```

## Fimm hlutir sem forrit gera oftast

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

### 4. Lesa opna verkefnaliði

```bash
omi action-item list --json --open
```

### 5. Merkja verkefnalið lokið

```bash
omi action-item complete --json a1b2c3d4
```

## Staðbundið Skjáborðs-API (Desktop API)

Þegar Omi Desktop birtir staðbundið API geta forrit leitað í skjásögu tækisins,
samantektum, SQL og verkefnum án þess að nota skýja-API-ið:

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

Aðeins skal ljúka við eða eyða verkefnum þegar notandi óskar þess sérstaklega:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

Skipunin `omi local screenshot SCREENSHOT_ID --output PATH` vistar skjámynd á
disk og skilar áfram JSON á stdout fyrir forrit. Auðkenni skjámyndar kemur venjulega
úr `local search-screen` eða SQL yfir `screenshots`-töfluna. Ef Desktop
skilar skipulagðri villu á borð við `screenshot_pending`, `screenshot_file_missing`
eða `screenshot_chunk_corrupted`, heldur JSON-hamurinn reitunum `reason`, `hint` og
`screenshot_id` á stderr svo forrit geti reynt aftur með eldra auðkenni eða tilkynnt
nákvæma hindrun. Staðfestu gildar niðurstöður með `file PATH` áður en þær eru sendar
til myndgreiningartóla.

## Dæmi: Python forritslykkja

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Keyrir omi skipanalínuna í JSON-ham og kastar villu ef lokakóði er ekki 0."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # Skipanalínan skrifar skipulagðar villur á stderr í JSON-ham:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Lesa alla opna verkefnaliði og merkja allt sem er eldra en 30 daga lokið.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Meðhöndlun hraðatakmarkana (rate limits)

Minningar: 120/klst. Samtöl: 25/klst. Hópskráningar: 15/klst.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # hraðatakmörkun náð
    err = json.loads(result.stderr)
    # err["detail"] lítur svona út: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Ábendingar

* Notaðu `--profile <nafn>` ef forritið þitt stýrir mörgum Omi-reikningum. Hver
  prófíll hefur sín eigin auðkenni og API-slóð.
* Notaðu `--api-base http://localhost:8080` fyrir staðbundnar prófanir á bakenda.
* Notaðu `OMI_LOCAL_API_URL` og `OMI_LOCAL_TOKEN` til að hnekkja staðbundnum
  Desktop API stillingum fyrir eina keyrslu.
* Notaðu `--verbose` við villuleit — það skrifar `METHOD path → status (Ns)` á stderr
  án þess að hafa áhrif á stdout, svo JSON-hamur helst gildur.
* Til að beina efni inn í samtal í gegnum pípu (pipe) skal nota `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
