# omi-cli no te mau hoʻā

> Tārere ara'a no te mau harness i fa'aho'ia e te mau LLM (Claude Code, Cursor, to outou mau bot ōna ē).

## Aha ara'a te CLI ē ha'apu i te mau hoʻā

* **JSON contract matara.** `--json` e tā i te taura JSON e monel te stdout *ʻoiaʻoʻe* te taura JSON — ʻaʻole e tā no te tere no te tahi atu, ʻaʻole e tā e te spinner. Te mau disu e tā i te stderr me`{"error": "...", "detail": "..."}`.
* **Exit code matara.** `0` monel / `1` am ui / `2` auth / `3` server / `4` rate limited / `5` ʻaita. E hinaaro ai te mau hoʻā i te hohono i tēia mau code ʻaʻole i te tautai i te mau disu i te reo ta'atamai.
* **ʻAʻole e ui i te mau hoʻā i te vā i teie matagi headless.** E tā `--yes` (na `-y`) i te mau ui māʻāneʻe; e tā `--api-key` na'e `OMI_API_KEY` i te mahana i te ui i te auth interactif.
* **Oro mārama i te tārua'i.** E tārua'i te mau `429` a `5xx` me te backoff mua ai te mai.

## Auth (tahi mahana, i te tao'e)

E mau te mea e fatu ai te API key no te dev i te vaha'a Omi web
(`https://app.omi.me` → Developer → API Keys) a:

```bash
omi auth login                          # am ui interactif; ʻaʻole e mau te key i te shell history
# na'e
export OMI_API_KEY=omi_dev_...          # ephemeral, metua te container
```

## Te mau ta'otorā na'o te mau hoʻā ē fa'ahitihia matara

### 1. Te mau ā'amu

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. E fa'ahiti tahi ā'amu

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Te mau tōhā'ono

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Te mau āha'aga no te mahana i fa'aiti

```bash
omi action-item list --json --open
```

### 5. Fa'aoti tahi āha'aga no te mahana i fa'aiti

```bash
omi action-item complete --json a1b2c3d4
```

## API ē tō mai i tēia pāpēho

I te fa'ahitihia te API ē tō mai i te Omi Desktop, e anga'ahia ai te mau hoʻā i te ī noiho i te tāma'ara'a ē tō mai i te mata'ī'ī, te recaps, te SQL a te mau āha'aga ʻaʻole i te anga'ahia te cloud dev API:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# na'e, no te mau session ephemeral:
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

Fā'aiti no'e tao'e te mau āha'aga na te mea i hinaaro 'ia matara:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` e sivi i te screenshot i te diski
a e tā no'e te JSON i te stdout no te mau script. Te screenshot ID e tā mai
`local search-screen` na'e te SQL i te tabele `screenshots`. I te fa'a'ao te Desktop
tahi disu matara me `screenshot_pending`, `screenshot_file_missing`,
na'e `screenshot_chunk_corrupted`, i te JSON mode e mau no'e te
`reason`, `hint`, a te `screenshot_id` i te stderr i te mārama
i te mau hoʻā i te tārua'i tahi ID tō mua'au e faapea i te matagi matara.
Fa'aharo te mau output monel me `file PATH` ma mua'i te hinaaro'ia
i te mau ī matagi vision.

## Tārere ara'a: te hoʻā Python loop

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

## Te mau āha'aga no te rate limit

Ā'amu: 120/i te hā'ā. Tōhā'ono: 25/i te hā'ā. Fa'ahiti batch: 15/i te hā'ā.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Te mau lē'ē

* Fa'aa'oa `--profile <name>` i te fa'ahitihia te hoʻā i te mau account Omi tino no'e tahi. E mau no'e tahi credential a API base i tē profile.
* Fa'aa'oa `--api-base http://localhost:8080` no te ā'amu backend ē tō mai.
* Fa'aa'oa `OMI_LOCAL_API_URL` a `OMI_LOCAL_TOKEN` i te hohono i te Desktop API ē tō mai no tahi tārua'i.
* Fa'aa'oa `--verbose` no te ā'amu — e tā `METHOD path → status (Ns)` i te stderr ʻaʻole e tā i te stdout, i te monel no'e te JSON mode.
* No te tā i te taura ē tō mai i tahi tōhā'ono, fa'aa'oa `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
