# omi-cli pa ba agents

> Mukanda wa buleji pa ba harnesses baleleke na LLM (Claude Code, Cursor, ne ba bots bobe).

## Mukwaito CLI ikala ya kind pa ba agents

* **Aqendur ya JSON ya kind.** `--json` ituma JSON document ya valid pa stdout ne
  *bua* JSON document — kakudi ba messages ba progress, kakudi ba spinners. Ba
  erreurs baluka pa stderr bu `{"error": "...", "detail": "..."}`.
* **Ba codes ba kufuma ya kind.** `0` ok / `1` usage / `2` auth / `3` server / `4` rate
  limited / `5` not found. Ba agents balongesha kusala njila pa ibo ne
  kakubalangulula ba messages ba erreurs ba lolowe lwadi.
* **Kakudi ba prompts ba interactive pa ba contextes ba headless.** Tuma `--yes`
  (toba `-y`) pa ba commandes ba kusumbula; tuma `--api-key` toba teleka
  `OMI_API_KEY` pa kufunda interactive login.
* **Retry ya buleleme.** `429` ne `5xx` bika-retrieshwa ne backoff
  kumpala kwa kubileja.

## Auth (kabedi kamue, ne muntu)

Muntu udi musumba dev API key pa Omi web app
(`https://app.omi.me` → Developer → API Keys) ne udi muyikela kimue kia ibi:

```bash
omi auth login                          # tapila interactive; clé kayi mu historique ya shell
# toba
export OMI_API_KEY=omi_dev_...          # ephemeral, bimpe pa ba conteneurs
```

## Bintu bitanu iba agents bakela bingi

### 1. Kutangila ba memories

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Kusumba memory

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Kutangila ba conversations

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Kutangila ba action items ba open

```bash
omi action-item list --json --open
```

### 5. Kuyidika action item bua complete

```bash
omi action-item complete --json a1b2c3d4
```

## API locale ya Desktop

Pambadilu Omi Desktop ileja API yandi ya locale, ba agents balongesha
kukongolease historique ya ecran ya pa machine, ba recaps, SQL, ne ba tasks
kabiituma API ya cloud dev:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# toba, pa ba sessions ba ephemeral:
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

Komesha toba fumisha ba tasks bua pambadilu muntu ulombela bimpe:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` ikafundisha screenshot pa
disque ne ikatuma JSON pa stdout pa ba scripts. ID ya screenshot ikabala
mwingi pa `local search-screen` toba pa SQL pa tableau ya `screenshots`.
Pambadilu Desktop ilamba failure ya structure bu `screenshot_pending`,
`screenshot_file_missing`, toba `screenshot_chunk_corrupted`, mode ya JSON
ikasungisha ba champs `reason`, `hint`, ne `screenshot_id` pa stderr bu ne
agents balongesha kulonga kabidi ID ya kale toba kulombela blockage ya luhisha.
Verifie ba outputs ba succes ne `file PATH` kumpala kwa kubituma pa ba outils
ba vision.

## Exemple ya kela: boucle ya agent mu Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Tuma omi CLI mu mode ya JSON, ukangula error pa ba codes ba kufuma babiisatelama."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI ituma ba erreurs ba structure pa stderr mu mode ya JSON:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Tangila ba action items ba open bonso, ukomesha bionso bipite matuku 30.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Kutangana ne ba rate limits

Memories: 120/hr. Conversations: 25/hr. Batch creates: 15/hr.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limit ifikile
    err = json.loads(result.stderr)
    # err["detail"] ikaleja bu: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Malongeselo

* Tuma `--profile <name>` pambadilu agent yobe ukwata ba comptes ba bungi ba
  Omi. Profile yonso ikwatsha credential yandi ne API base yandi.
* Tuma `--api-base http://localhost:8080` pa kupinga backend ya locale.
* Tuma `OMI_LOCAL_API_URL` ne `OMI_LOCAL_TOKEN` pa kufunda ba paramètres ba
  API ya Desktop ya profile pa run umue.
* Tuma `--verbose` pa debugging — ikafundisha `METHOD path → status (Ns)` pa
  stderr ne kayiikwatsha stdout, buo mode ya JSON ikala valid.
* Pa kutuma contenu mu conversation, tuma `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
