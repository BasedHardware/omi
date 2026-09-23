# omi-cli fyri agentar

> Hagnýt leiðarvísir fyri LLM-drivnar telduheildir (Claude Code, Cursor, tínar egnu bottar).

## Hví CLI'ið er agentvænligt

* **Støðugur JSON-sáttmáli.** `--json` sendir eitt gild JSON-skjal til stdout —
  *bert* eitt JSON-skjal — eingi framstigsboð, eingir spinnerar. Feilir fara til
  stderr sum `{"error": "...", "detail": "..."}`.
* **Støðugir útgongdskotur.** `0` ok / `1` nýtsla / `2` innritan / `3` servari /
  `4` ferðmark / `5` ikki funnið. Agentar kunnu greina á hesum uttan at tulka
  náttúrligar feilmeiningar.
* **Eingi samvirkin spurningar í headless-samanhengi.** Gev `--yes` (ella `-y`)
  til oyðileggjandi boð; gev `--api-key` ella set `OMI_API_KEY` at sleppa
  samvirkinni innritan.
* **Tillátin endurroyndarferð.** `429` og `5xx` verða roynd aftur við backoff
  áðrenn tey koma fram.

## Innritan (eina ferð, av menniskjanum)

Nýtarin fær ein dev API-lykil frá Omi-vevappini
(`https://app.omi.me` → Developer → API Keys) og velur annarhvørt:

```bash
omi auth login                          # samvirkin innliming; lykilin kemur ikki í shell-søgu
# ella
export OMI_API_KEY=omi_dev_...          # fyribils, høgligur fyri container
```

## Tey fimm lutir sum agentar gera oftast

### 1. Les minni

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Ger eitt minni

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Les samrøður

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Les opin arbeiðslið

```bash
omi action-item list --json --open
```

### 5. Merk eitt arbeiðslið sum liðugt

```bash
omi action-item complete --json a1b2c3d4
```

## Lokalt Desktop-API

Tá Omi Desktop vísir sítt lokala API, kunnu agentar spyrja um skjásøgu á
tólinum, samandráttir, SQL og uppgávur uttan at nýta skýggja-dev-API'ið:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# ella, fyri fyribils setur:
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

Fullfør ella strika uppgávur bert tá nýtarin biður greitt um tað:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` skrivar skjámyndina til
diskin og prentar framvegis JSON til stdout fyri skriftir. Skjámynd-ID'ið kemur
vanliga frá `local search-screen` ella SQL yvir `screenshots`-tøvluni. Um
Desktop sendir eina struktureraraða feil sum `screenshot_pending`,
`screenshot_file_missing`, ella `screenshot_chunk_corrupted`, varðveitir
JSON-støðan `reason`, `hint` og `screenshot_id`-økini á stderr so agentar kunnu
roynda eitt eldri ID aftur ella melda nágreiniliga forðingina. Vátta eydnukendar
útskriftir við `file PATH` áðrenn tær verða sendar til sjónartól.

## Dømi: Python-agentlykka

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Kallar omi-CLI'ið í JSON-støðu, reisir feil tá útgongdskotan er ikki eydnukend."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI'ið prentar struktureraraðar feilir til stderr í JSON-støðu:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Les øll opin arbeiðslið og merk alt eldri enn 30 dagar sum liðugt.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## At handfara ferðmark

Minni: 120/tíma. Samrøður: 25/tíma. Lotuppskot: 15/tíma.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # ferðmark nátt
    err = json.loads(result.stderr)
    # err["detail"] sær soleiðis út: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Góð ráð

* Nýt `--profile <name>` um agenturin tín hevur fleiri Omi-kontur. Hvør profil
  hevur egna innritan og egna API-grund.
* Nýt `--api-base http://localhost:8080` fyri lokala backend-roynd.
* Nýt `OMI_LOCAL_API_URL` og `OMI_LOCAL_TOKEN` at yvirkoyra
  Desktop-API-stillingarnar hjá profilinum fyri eina koyru.
* Nýt `--verbose` til debugging — tað skrásetur `METHOD path → status (Ns)` til stderr
  uttan at ávirka stdout, so JSON-støðan verður verandi gild.
* Fyri at senda innihald inn í eina samrøðu gjøgnum rør, nýt `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
