# omi-cli evit an agentoù

> Ur sturlevr pleustrek evit an harnessoù kaset gant LLM (Claude Code, Cursor, ho botadoù deoc'h).

## Perak eo CLI unan aet gant an agentoù

* **Emglev JSON stabil.** `--json` a bro ur teul JSON talvoudek war stdout ha
  *nemet* ur teul JSON — hep kemennadennoù araokaat, hep spinneroù. Ar fazioù a
  ya da stderr evel `{"error": "...", "detail": "..."}`.
* **Kodoù mont er-maez stabil.** `0` mat / `1` implij / `2` auth / `3` servijer /
  `4` bevenn tizh / `5` n'eo ket kavet. An agentoù a c'hall rannañ warno hep
  dielfennañ ar fazioù e yezh naturel.
* **Pret ebet e promptoù etrewezhius e kendestennoù headless.** Tremenit `--yes` (pe `-y`)
  d'an urzhiadoù distrujus; tremenit `--api-key` pe kegit `OMI_API_KEY` evit tremen
  dreist ar gevreadenn etrewezhius.
* **Emzalc'h adsaoliñ digarus.** `429` ha `5xx` a adsaoler gant backoff a-raok
  dont a-gleiz.

## Auth (ur wech, gant an den)

An implijer a gaot ur alc'hwez dev API diouzh arload web Omi
(`https://app.omi.me` → Developer → API Keys) ha pe:

```bash
omi auth login                          # pegañ etrewezhius; an alc'hwez ne chom ket e istor ar shell
# pe
export OMI_API_KEY=omi_dev_...          # amzerel, gwellañ evit ar c'honteinerioù
```

## Ar pemp tra a ra an agentoù ar muiañ

### 1. Lenn ar soñjoù

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Krouiñ ur soñj

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Lenn an divizoù

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Lenn ar poentoù ober digor

```bash
omi action-item list --json --open
```

### 5. Merkañ ur poent ober evel graet

```bash
omi action-item complete --json a1b2c3d4
```

## API lec'hel Desktop

Pa ziskouez Omi Desktop e API lec'hel, e c'hall an agentoù goulenn istor skramm
an trevnad, ar c'hlotañ, SQL, hag an trevelloù hep implijout API dev ar goumoul:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# pe, evit an dalc'hoù amzerel:
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

Klokaat pe dilemel an trevelloù nemet pa c'houlenn an implijer sklaer:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` a skriv ar skrammadenn war an
disk hag a voull c'hoazh JSON war stdout evit ar skriptoù. An ID skrammadenn a
zeu eus `local search-screen` pe SQL war an daolenn `screenshots` alies. Ma
roer gantañ ur fazi frammek evel `screenshot_pending`, `screenshot_file_missing`
pe `screenshot_chunk_corrupted`, ar mod JSON a zerc'hel ar maeziennoù `reason`,
`hint` ha `screenshot_id` war stderr evit ma c'hall an agentoù adesevil un ID
koshoc'h pe diskleriañ ar bloc'hadennoù resis. Gwiriit an disoc'hoù mat gant
`file PATH` a-raok kas anezho d'an ostilhoù gweledigezh.

## Skouer labouret: loop ejen Python

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

## Merañ bevennoù tizh

Soñjoù: 120/e. Divizoù: 25/e. Krouidigezhioù voutailh: 15/e.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Erbedadennoù

* Implijit `--profile <name>` m'emañ hoc'h ejen o verañ meur a gont Omi. Pep profil
  en deus e daveennoù hag e ziazez API.
* Implijit `--api-base http://localhost:8080` evit arnodiñ ar backend lec'hel.
* Implijit `OMI_LOCAL_API_URL` hag `OMI_LOCAL_TOKEN` evit erlec'hiañ arventennoù
  API lec'hel Desktop ar profil evit un exekuzion.
* Implijit `--verbose` evit disloc'hañ — e skriv `METHOD path → status (Ns)` war
  stderr hep ledañ stdout, setu ar mod JSON a chom talvoudek.
* Evit pipeañ endalc'had en ur diviz, implijit `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
