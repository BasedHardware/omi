# omi-cli no te mau agent

> Parau fa'aao no te mau harness LLM (Claude Code, Cursor, te mau bot na outou).

## Nō te aha te CLI e mea maitai no te mau agent

* **Contract JSON tūpatō.** `--json` e tu'u i te document JSON mau i te stdout e
  *ho'e document JSON anae* — 'aita message ha'apa'ora'a, 'aita spinner. Te mau
  hape e haere i te stderr ma'ti `{"error": "...", "detail": "..."}`.
* **Code ha'ama'a tūpatō.** `0` maitai / `1` ha'apa'ora'a / `2` auth / `3` server /
  `4` fare rate / `5` 'aita i ite. Te mau agent e nehenehe e fana'o i nā iho
  'aita te hape i te reo iti.
* **'Aita prompt interactive i roto i te context headless.** Fa'aere `--yes` (a'ore `-y`)
  i te mau command fa'ahoro; fa'aere `--api-key` a'ore `OMI_API_KEY` no te ha'ama'a
  i te login interactive.
* **Fa'aiti ha'apa'ora'a ha'ama'a.** `429` e `5xx` e fa'aiti i te mata'ita'i ma te
  backoff i mua i te ha'ama'a.

## Auth (ho'e taime, na te ta'ata)

Te ta'ata e hi'o i te dev API key mai te web app Omi
(`https://app.omi.me` → Developer → API Keys) e a'ore:

```bash
omi auth login                          # paste interactive; te key 'aita i roto i te histoire shell
# a'ore
export OMI_API_KEY=omi_dev_...          # ephemeral, maitai no te container
```

## Te mau mea e'ha te mau agent e rave mā'ore

### 1. Tai'o i te mau memory

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Fa'atia i te ho'e memory

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Tai'o i te mau parau

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Tai'o i te mau action-item i hu'ero

```bash
omi action-item list --json --open
```

### 5. Fai i te ho'e action-item i roto i te huru fa'atia

```bash
omi action-item complete --json a1b2c3d4
```

## API local no te Desktop

I te taime Omi Desktop e fa'aite i tōna API local, te mau agent e nehenehe e
uiui i te histoire écran i nō iho i te device, te mau recap, te SQL, e te mau
tâche 'aita te API dev i te cloud:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# a'ore, no te mau session ephemeral:
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

Fa'atia a'ore tape'e te mau tâche i te taime te ta'ata e ui ma'iti:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` e papā i te screenshot i te
disque e e fa'atia i te JSON i te stdout no te mau script. Te ID screenshot e
hi'o mai `local search-screen` a'ore SQL i nō iho i te table `screenshots`.
Tongana Desktop e hō'ē i te hape structured ma'ti `screenshot_pending`,
`screenshot_file_missing`, a'ore `screenshot_chunk_corrupted`, te mode JSON e
hi'o i te mau champ `reason`, `hint`, e `screenshot_id` i te stderr no te agent
e nehenehe e fa'aiti i te ID tāmu'a a'ore e fa'aite i te blocage precis.
Vérifie te mau résultat maitai na `file PATH` i mua i te fa'aere i te mau outil
vision.

## Exemple fa'aao: boucle agent i roto i te Python

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

## Gère i te mau limite rate

Memory: 120/h. Parau: 25/h. Fa'atia batch: 15/h.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Te mau hint

* Ha'apa'ora'a `--profile <name>` tongana te agent e gère i te mau account Omi
  e'ē. Ho'e profile e 'i tōna credential e tōna base API.
* Ha'apa'ora'a `--api-base http://localhost:8080` no te test backend local.
* Ha'apa'ora'a `OMI_LOCAL_API_URL` e `OMI_LOCAL_TOKEN` no te passé i te mau
  setting API local no te run ho'e.
* Ha'apa'ora'a `--verbose` no te debug — e log i te `METHOD path → status (Ns)`
  i te stderr 'aita te affecter stdout, ma'ti te mode JSON e mau i te valid.
* No te pipe i te contenu i roto i te parau, ha'apa'ora'a `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
