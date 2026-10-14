# omi-cli no nā 'ēgenta

> Palapala ho'okele no nā harness e ho'okele 'ia e LLM (Claude Code, Cursor, kāu pono'ī bots).

## No ke aha ka CLI e pono ai i nā 'ēgenta

* **'Ōlelo aeloa JSON pa'a.** `--json` e ho'opuka i kahi palapala JSON pono i ka stdout a me
  *wale nō* ho'okahi palapala JSON — 'a'ohe memo ho'omaka, 'a'ohe spinner. Nā hewa e
  hele i ka stderr ma ke ʻano `{"error": "...", "detail": "..."}`.
* **Nā pāku'i puka pa'a.** `0` maika'i / `1' ho'ohana / `2` auth / `3` server /
  `4` kaupalena wikiwiki / `5` 'a'ole i loa'a. Hiki i nā 'ēgenta ke ho'oka'awale i
  kēia me ka 'ole o ka ho'oma'ama'a i nā hewa 'ōlelo maoli.
* **'A'ohe prompt interactive i nā context headless.** Ha'awi `--yes` (a i 'ole `-y`)
  i nā kauoha luku; ha'awi `--api-key` a ho'onohonoho 'ia `OMI_API_KEY` e holo i
  ka login interactive.
* **Hana ho'omālamalama ʻae.** `429` a me `5xx` e retry me ka backoff ma mua o ka puka 'ana.

## Auth (ho'okahi manawa, na ke kanaka)

Loa'a i ka mea ho'ohana ke kī dev API mai ka polokalamu web Omi
(`https://app.omi.me` → Developer → API Keys) a i 'ole:

```bash
omi auth login                          # paste interactive; 'a'ole kī i ka mō'aukala shell
# a i 'ole
export OMI_API_KEY=omi_dev_...          # pōnehu, maika'i no nā ipu
```

## Nā mea 'elima e hana nui ai nā 'ēgenta

### 1. Heluhelu i nā mea ho'omana'o

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Hana i ka ho'okahi mea ho'omana'o

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Heluhelu i nā kama'ilio

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Heluhelu i nā 'āpana hana e wehe ana

```bash
omi action-item list --json --open
```

### 5. Kuhikuhi i ka 'āpana hana i pau

```bash
omi action-item complete --json a1b2c3d4
```

## API kūloko o Desktop

I ka wā e hō'ike ai Omi Desktop i kona API kūloko, hiki i nā 'ēgenta ke nīnau i
ka mō'aukala pale o ke aupuni, nā recaps, SQL, a me nā hana me ka 'ole o ka
ho'ohana i ka API dev i ka ao:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# a i 'ole, no nā pōnehu pōnehu:
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

Hoʻopau a holoi rānei i nā hana i ka wā e koi ana ka mea ho'ohana i ka 'ike le'a:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` e kākau i ka screenshot i ka
disk a e pūlumi i ka JSON i ka stdout no nā script. Ke ID screenshot e hiki mai
mai `local search-screen` a i 'ole SQL ma luna o ka papa 'aina `screenshots`. Inā
ho'ihoʻi 'ia e Desktop kahi hewa 'ōlelo aeloa like `screenshot_pending`,
`screenshot_file_missing`, a i 'ole `screenshot_chunk_corrupted`, ka mode JSON e
mālama i nā kahua `reason`, `hint`, a me `screenshot_id` i ka stderr i hiki i nā
'ēgenta ke retry i kahi ID kahiko a i 'ole e ha'i i ka palena kiko'ī. Ho'ona'u i
nā hopena maika'i me `file PATH` ma mua o ka ha'awi 'ana i nā mea hana 'ike.

## La'ana i hana 'ia: poro 'ēgenta Python

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

## Ho'omalu i nā kaupalena wikiwiki

Mea ho'omana'o: 120/h. Kama'ilio: 25/h. Hana pū: 15/h.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Nā 'ōlelo a'oa'o

* Ho'ohana `--profile <name>` inā kāu 'ēgenta e mālama i nā mo'okāleka Omi he nui.
  Kēlā me kēia pūlumi he credential a me ka base API pono'ī.
* Ho'ohana `--api-base http://localhost:8080` no nā ho'ā'o backend kūloko.
* Ho'ohana `OMI_LOCAL_API_URL` a me `OMI_LOCAL_TOKEN` e ho'okā i nā ho'onohonoho
  API kūloko o Desktop o ka pūlumi no ho'okahi holo.
* Ho'ohana `--verbose` no ka ho'oponopono — e kākau `METHOD path → status (Ns)` i
  ka stderr me ka 'ole o ka ho'okā i ka stdout, no laila ke mode JSON e mau ana.
* E pipe i ka ʻike i ke kama'ilio, ho'ohana `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
