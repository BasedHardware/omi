# omi-cli agenteentzat

> LLMek gidatutako harnessentzako gida praktikoa (Claude Code, Cursor, zure bot propioak).

## Zergatik da CLIa agenteentzako egokia

* **JSON kontratu egonkorra.** `--json`-ek JSON dokumentu balioduna inprimatzen du stdout-ra eta *bakarrik* JSON — aurrerapen-mezurik edo spinnerik gabe. Akatsak stderr-ra doaz `{"error": "...", "detail": "..."}` moduan.
* **Irteera-kode egonkorrak.** `0` ok / `1` erabilera / `2` auth / `3` zerbitzaria / `4` rate limited / `5` ez aurkituta. Agenteei hauetan adar egin diezaiekete hizkuntza naturala parseatu gabe.
* **Ez dago gonbidapen interaktiborik headless testuinguruetan.** `--yes` (edo `-y`) eman suntsitzaile komandoetara; `--api-key` eman edo `OMI_API_KEY` ezarri saio interaktiboa saltzeko.
* **Errore-bereizketa barkatzailea.** `429` eta `5xx` backoff-arekin berriz saiatzen dira azaleratu aurretik.

## Autentifikazioa (behin, gizakiak)

Erabiltzaileak dev API gakoa lortzen du Omi web aplikaziotik
(`https://app.omi.me` → Developer → API Keys) eta ondoren:

```bash
omi auth login                          # itsatsi interaktiboa; gakoa ez dago shell historian
# # edo
export OMI_API_KEY=omi_dev_...          # behin-behinekoa, edukiontzi-adaptatua
```

## Agenteei gehien egiten dieten bost gauza

### 1. Memories irakurtzea

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Memory bat sortzea

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Conversations irakurtzea

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Irekitako action items irakurtzea

```bash
omi action-item list --json --open
```

### 5. Action item bat eginda markatzea

```bash
omi action-item complete --json a1b2c3d4
```

## Desktop API lokala

Omi Desktop-k bere API lokala erakusten duenean, agenteek on-device
pantaila-historia, recaps, SQL eta atazak galdegin ditzakete cloud dev API erabili gabe:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# # edo, behin-behineko saioentzat:
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

Atazak bakarrik osatu edo ezabatu erabiltzaileak argi eskatzen duenean:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH`-k pantaila-argazkia
idazten du diskora eta JSON-a stdout-ra inprimatzen du scriptetarako. Screenshot
ID orokorrean `local search-screen` edo `screenshots` taularen SQL-etik dator.
Desktop-ek egituratutako hutsegitea itzultzen badu, adibidez `screenshot_pending`,
`screenshot_file_missing` edo `screenshot_chunk_corrupted`, JSON moduak `reason`,
`hint` eta `screenshot_id` eremuak stderr-n mantentzen ditu, agenteak ID zaharragoa
saiatzeko edo blokeatzaile zehatza jakinarazteko. Irteera onak `file PATH`-ekin
balioztatu vision-tresnetara bidali aurretik.

## Adibide landua: Python agente begizta

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

# Irekitako action item guztiak irakurri eta 30 egun baino zaharragoak osatu bezala markatu.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Rate-limiten kudeaketa

Memories: 120/ordu. Conversations: 25/ordu. Batch sortzeak: 15/ordu.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] horrela dago: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Aholkuak

* Erabili `--profile <name>` zure agenteak hainbat Omi kontu kudeatzen baditu.
  Profil bakoitzak bere kredentzialak eta API-basea ditu.
* Erabili `--api-base http://localhost:8080` backend lokala probatzeko.
* Erabili `OMI_LOCAL_API_URL` eta `OMI_LOCAL_TOKEN` profil-lokal Desktop API
  ezarpenak gainidazteko exekuzio batzuetarako.
* Erabili `--verbose` debugatzeko — `METHOD path → status (Ns)` stderr-ra
  erregistratzen du stdout-ari kalterik egin gabe, beraz JSON modua baliozkoa da.
* Conversation-era edukia pipe egiteko, erabili `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
