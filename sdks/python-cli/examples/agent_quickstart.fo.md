# omi-cli til umboðsmenn

> Praktiskur vegleiðari fyri LLM-stýrd harness (Claude Code, Cursor, tíns egnu bøtur).

## Hví er CLI vinarligur umboðsmönnum

* **Stabilt JSON-samning.** `--json` gefur út gildan JSON-skjal til stdout og
  *bert* JSON-skjal — ongar framdriftarboð, ongar snúrar. Feilur fer til stderr
  sum `{"error": "...", "detail": "..."}`.
* **Stabilir útgangskóðar.** `0` gott / `1` brúk / `2` auth / `3` servari /
  `4` ferðamark / `5` funnið ikki. Umboðsmenn kunnu forgreina á teimum án at
  tulka náttúruliga málfeilur.
* **Ongar samskiftandi promptar í headless-samhengi.** Send `--yes` (ella `-y`)
  til eyðileggjandi skipanir; send `--api-key` ella sett `OMI_API_KEY` fyri at
  sleppa samskiftandi innskráning.
* **Fyrikennandi endurreynsi.** `429` og `5xx` endurreynast við backoff áðrenn
  tey koma út.

## Auth (einaferð, av menniskju)

Brúkarin fær dev API-lykil frá Omi vebuforriti
(`https://app.omi.me` → Developer → API Keys) og ella:

```bash
omi auth login                          # samskiftandi líming; lykilin verður ikki í skel-historienum
# ella
export OMI_API_KEY=omi_dev_...          # skammlívt, gott til geyma
```

## Tey fimm ting, umboðsmenn gera mest

### 1. Lesa minni

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Gera minni

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Lesa samrøður

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Lesa opnar gerðarpunktir

```bash
omi action-item list --json --open
```

### 5. Markera gerðarpunkt sum liðan

```bash
omi action-item complete --json a1b2c3d4
```

## Staðbundið Desktop API

Tá Omi Desktop víðir sín staðbunda API, kunnu umboðsmenn fyrispurna um skjá
søgu tólka, samandráttir, SQL og verk án at brúka skýdev-API:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# ella, fyri skammlívar samlinger:
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

Fullfør ella strik verk bert tá brúkarin biður greitt:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` skrivar skjámyndina á disk og
prentar enn JSON til stdout fyri skriptir. Skjámyndar-ID kemur vanliga frá
`local search-screen` ella SQL um `screenshots`-töfluna. Vísir Desktop
struktureraða feil sum `screenshot_pending`, `screenshot_file_missing` ella
`screenshot_chunk_corrupted`, varðveitir JSON-hátturin `reason`, `hint` og
`screenshot_id` reitarnar á stderr, so umboðsmenn kunnu roynda við eldra ID ella
boða frá nákvæmum hindringum. Staðfest útkomur við `file PATH` áðrenn tú sender
teimum til sjón-tólir.

## Útferðað dømi: Python-umboðssíglið

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

## Stýring av ferðamörkum

Minni: 120/t. Samrøður: 25/t. Pøttinger: 15/t.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Ráð

* Brúka `--profile <name>` um tíni umboðsmaður stýrir fleiri Omi-kontum. Hvør
  profilur hevur sína egnu innskráning og API-grunn.
* Brúka `--api-base http://localhost:8080` til staðbundnar backend-próvingar.
* Brúka `OMI_LOCAL_API_URL` og `OMI_LOCAL_TOKEN` til at seta um staðbundnar
  Desktop API-innstillingar profil fyri eina keyrslu.
* Brúka `--verbose` til feilleiting — tað skrivar `METHOD path → status (Ns)`
  til stderr án at ávirka stdout, so JSON-hátturin heldur við at vera gildan.
* Til at pipea innihald í samrøðu, brúka `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
