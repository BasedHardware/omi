# omi-cli para sa mga agent

> Praktikal na gabay para sa mga harness na pinapagana ng LLM (Claude Code, Cursor, sarili mong mga bot).

## Bakit angkop ang CLI para sa mga agent

* **Matatag na kontrata ng JSON.** Naglalabas ang `--json` ng wastong JSON na dokumento sa stdout at
  *tanging* JSON na dokumento lamang — walang mga mensahe sa pag-usad o mga spinner. Pumupunta ang mga error sa
  stderr bilang `{"error": "...", "detail": "..."}`.
* **Matatag na mga exit code.** `0` ok / `1` maling paggamit / `2` pagpapatunay / `3` error sa server / `4` nalimitahan ang rate / `5` hindi nahanap. Maaaring mag-branch ang mga agent batay dito nang hindi kailangang mag-parse ng mga error sa natural na wika.
* **Walang mga interactive na prompt sa headless na konteksto.** Ipasa ang `--yes` (o `-y`) para sa
  mga mapanirang command; ipasa ang `--api-key` o itakda ang `OMI_API_KEY` upang laktawan ang interactive na pag-login.
* **Mapagparayang gawi sa muling pagsubok.** Muling sinusubukan ang `429` at `5xx` nang may backoff
  bago ilabas ang error.

## Pagpapatunay (isang beses, ng tao)

Kinukuha ng user ang dev API key mula sa Omi web app
(`https://app.omi.me` → Developer → API Keys) at alinman sa:

```bash
omi auth login                          # interactive na pag-paste; hindi naitatala ang key sa history ng shell
# o
export OMI_API_KEY=omi_dev_...          # pansamantala, angkop para sa container
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

Kapag inilantad ng Omi Desktop ang lokal na API nito, maaaring i-query ng mga agent ang history ng screen sa device,
mga recap, SQL, at mga gawain nang hindi ginagamit ang cloud dev API:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# o, para sa mga pansamantalang session:
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

Kumpletuhin o tanggalin lamang ang mga gawain kapag malinaw na hiniling ng user:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

Isinusulat ng `omi local screenshot SCREENSHOT_ID --output PATH` ang screenshot sa
disk at nagpi-print pa rin ng JSON sa stdout para sa mga script. Karaniwang nagmumula
ang ID ng screenshot sa `local search-screen` o SQL sa talahanayan ng `screenshots`. Kung magbalik
ang Desktop ng nakabalangkas na pagkabigo tulad ng `screenshot_pending`, `screenshot_file_missing`,
o `screenshot_chunk_corrupted`, pinapanatili ng JSON mode ang mga field na `reason`, `hint`, at
`screenshot_id` sa stderr upang makapagsimula muli ang mga agent gamit ang mas lumang ID o maiulat
ang eksaktong dahilan. I-validate ang mga matagumpay na output gamit ang `file PATH` bago ipasa ang mga ito
sa mga vision tool.

## Halimbawa: Loop ng Python agent

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Tawagin ang omi CLI sa JSON mode, nagpapakita ng exception sa mga error code."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # Nagpi-print ang CLI ng mga nakabalangkas na error sa stderr sa JSON mode:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Basahin ang lahat ng bukas na action item at markahan ang anumang mas luma sa 30 araw bilang tapos na.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Pangangasiwa sa mga limitasyon sa rate (rate limits)

Mga Alaala: 120/oras. Mga Pag-uusap: 25/oras. Maramihang paggawa: 15/oras.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # nalimitahan ang rate
    err = json.loads(result.stderr)
    # ganito ang hitsura ng err["detail"]: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Mga Tip

* Gamitin ang `--profile <pangalan>` kung humahawak ang iyong agent ng maramihang Omi account. Bawat
  profile ay may sariling kredensyal at API base.
* Gamitin ang `--api-base http://localhost:8080` para sa lokal na pagsusuri sa backend.
* Gamitin ang `OMI_LOCAL_API_URL` at `OMI_LOCAL_TOKEN` upang i-override ang mga lokal na setting
  ng Desktop API para sa isang pagpapatakbo.
* Gamitin ang `--verbose` para sa pag-debug — nagla-log ito ng `METHOD path → status (Ns)` sa stderr
  nang hindi naaapektuhan ang stdout, kaya nananatiling wasto ang JSON mode.
* Para sa pag-pipe ng nilalaman sa isang pag-uusap, gamitin ang `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
