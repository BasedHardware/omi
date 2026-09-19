# omi-cli para sa mga AI Agent

> Praktikal na gabay para sa mga harness na pinapagana ng LLM (Claude Code, Cursor, sarili mong mga bot).

## Bakit angkop ang CLI para sa mga agent

* **Matatag na kontrata ng JSON.** Ang `--json` ay naglalabas ng wastong dokumentong JSON sa stdout
  at *tanging* dokumentong JSON lamang — walang mga mensahe ng progreso, walang mga loading spinner.
  Ang mga error ay ipinapadala sa stderr bilang `{"error": "...", "detail": "..."}`.
* **Matatag na mga exit code.** `0` ayos / `1` maling paggamit / `2` pagpapatotoo / `3` server /
  `4` nalampasan ang rate limit / `5` hindi nahanap. Maaaring magsangay ang mga agent batay sa mga
  ito nang hindi kinakailangang mag-parse ng natural na wika.
* **Walang mga interactive prompt sa mga headless context.** Ipasa ang `--yes` (o `-y`) para sa mga
  mapanirang command; ipasa ang `--api-key` o itakda ang `OMI_API_KEY` upang laktawan ang
  interactive login.
* **Mapanuring gawi sa muling pagsubok.** Ang mga error na `429` at `5xx` ay awtomatikong muling
  sinusubukan na may exponential backoff bago iulat.

## Pagpapatotoo (isang beses lamang, ng tao)

Kukunin ng user ang dev API key mula sa web app ng Omi
(`https://app.omi.me` → Developer → API Keys) at gagawin ang isa sa mga sumusunod:

```bash
omi auth login                          # interactive na pag-paste; hindi naka-save ang key sa kasaysayan ng shell
# o kaya
export OMI_API_KEY=omi_dev_...          # panandalian, angkop para sa mga container
```

## Ang limang bagay na pinakamadalas gawin ng mga agent

### 1. Magbasa ng mga alaala

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Gumawa ng alaala

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Magbasa ng mga pag-uusap

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Magbasa ng mga bukas na action item

```bash
omi action-item list --json --open
```

### 5. Markahan ang action item bilang tapos na

```bash
omi action-item complete --json a1b2c3d4
```

## Lokal na Desktop API

Kapag pinapagana ng Omi Desktop ang lokal nitong API, maaaring mag-query ang mga agent sa kasaysayan
ng screen ng device, mga recap, SQL, at mga gawain nang hindi ginagamit ang cloud dev API:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# o para sa mga pansamantalang session:
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

Kumpletuhin o tanggalin lamang ang mga gawain kapag malinaw itong hiniling ng user:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

Ang command na `omi local screenshot SCREENSHOT_ID --output PATH` ay nagsusulat ng screenshot sa disk
at patuloy na nagpi-print ng JSON sa stdout para sa mga script. Ang screenshot ID ay karaniwang nagmumula
sa `local search-screen` o SQL query sa talahanayan ng `screenshots`. Kung magbalik ang Desktop ng
nakabalangkas na pagkabigo tulad ng `screenshot_pending`, `screenshot_file_missing`, o
`screenshot_chunk_corrupted`, pinapanatili ng JSON mode ang mga field na `reason`, `hint`, at `screenshot_id`
sa stderr upang makasubok ang mga agent ng mas lumang ID o mag-ulat ng eksaktong sagabal.
Patotohanan ang mga matagumpay na output gamit ang `file PATH` bago ipasa ang mga ito sa mga vision tool.

## Detalyadong halimbawa: Python agent loop

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

## Pamamahala sa mga limitasyon sa dalas (Rate Limits)

Mga Alaala: 120/oras. Mga Pag-uusap: 25/oras. Maramihang Paglikha: 15/oras.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Mga Tip

* Gamitin ang `--profile <name>` kung ang iyong agent ay namamahala ng maramihang Omi account. Bawat
  profile ay may sariling kredensyal at base ng API.
* Gamitin ang `--api-base http://localhost:8080` para sa lokal na backend testing.
* Gamitin ang `OMI_LOCAL_API_URL` at `OMI_LOCAL_TOKEN` upang i-override ang profile-local na mga
  setting ng Desktop API para sa isang takbo.
* Gamitin ang `--verbose` para sa pag-debug — nagtatala ito ng `METHOD path → status (Ns)` sa stderr
  nang hindi naaapektuhan ang stdout, kaya nananatiling wasto ang JSON mode.
* Para sa pag-pipe ng nilalaman sa isang pag-uusap, gamitin ang `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
