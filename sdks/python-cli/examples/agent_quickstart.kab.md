# omi-cli i yis-agents

> Amnir ameskan i yis-agents yesselqes s LLM (Claude Code, Cursor, neɣ bots inek).

## Acɣer CLI yelha i yis-agents

* **Aqendur JSON ur ibeddilen.** `--json` yesuffeɣ afaylu JSON ameɣtu ɣer
  stdout, *kan* afaylu JSON — ulac iznan n usfari, ulac spinners. Tuccḍiwin
  tteffɣent ɣer stderr am `{"error": "...", "detail": "..."}`.
* **Tingalin n tuffɣa ur ttbeddilen.** `0` ok / `1` usage / `2` auth / `3`
  server / `4` rate limited / `5` not found. Is-agents zemren ad fṛen ɣef
  wid-a war ad ɣeṛṛen tuccḍiwin s tutlayt tamezdayant.
* **Ulac isuterayen interactive deg unagrawen headless.** Efk `--yes` (neɣ
  `-y`) i tnezmiwin yettmettaten; efk `--api-key` neɣ seddu `OMI_API_KEY`
  akken ad tsegleḍ tuqqna interactive.
* **Aselmed n walsekkar.** `429` d `5xx` ttalsekkaren s backoff qbel ad banen.

## Tuqqna (yiwet tikelt, s ufus n umdan)

Aseqdac yettagen tsarit API n uneflay seg usmel n Omi
(`https://app.omi.me` → Developer → API Keys) syen yettexṣer yiwen seg wigi:

```bash
omi auth login                          # amsali interactive; tsarit ur telli deg umazray n shell
# neɣ
export OMI_API_KEY=omi_dev_...          # ephemeral, yelha i yikontenṛen
```

## Tɣawsiwin semmus i xeddmen is-agents aṭas

### 1. Taɣuri n ismiren

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Snulfu-d asmire

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Taɣuri n idiwenniyen

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Taɣuri n tmahilin n uxeddim yeldin

```bash
omi action-item list --json --open
```

### 5. Err temhilt n uxeddim am temmed

```bash
omi action-item complete --json a1b2c3d4
```

## API tanarazt n Desktop

Mi ara yessken Omi Desktop API-is tanarazt, is-agents zemren ad seqsen amazray
n ugdil ɣef tmacint, iselmaden (recaps), SQL, d tmahilin war aseqdec n API n
uneflay deg ubiger:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# neɣ, i tɣuṛiwin (sessions) isefɣiren:
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

Immed neɣ kkes tmahilin kan mi ara yesteqsa aseqdac s wudem ibanen:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` yessers aselmed ɣef udebber
syen yettmeslay daɣen JSON ɣer stdout i yiskripten. ID n uselmed yettuɣal aṭas
seg `local search-screen` neɣ seg SQL ɣef tfelwit `screenshots`. Ma yella
Desktop yerra tuccḍa yettwabnun am `screenshot_pending`,
`screenshot_file_missing`, neɣ `screenshot_chunk_corrupted`, asker JSON
iḥerrez urtan `reason`, `hint`, d `screenshot_id` ɣer stderr akken is-agents
zemren ad ěǧren ID aqbuṛ neɣ ad mmalen awɣi n ubeyṛu. Senqed tuffɣa yeddan s
`file PATH` qbel ad tt-yefkeḍ i yifecka n timmuɣli.

## Amedya yexdem: ticcelt n us-agent s Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Semsed omi CLI deg usker JSON, sers tuccḍa ɣef tingalin n tuffɣa ur nelli meɣtu."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI yesuffeɣ tuccḍiwin yettwabnun ɣer stderr deg usker JSON:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Ɣeṛ akk tmahilin yeldin, immed-ten ma yezdeɣ 30 n wussan.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Tigdatin n tuzzya

Memories: 120/hr. Conversations: 25/hr. Batch creates: 15/hr.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # tagdalt n tuzzya
    err = json.loads(result.stderr)
    # err["detail"] yettban am: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Tiktiwin

* Semsed `--profile <isem>` ma yella agent-inek yettawi ddeqs n umiḍan Omi.
  Yal profile yesɛa asenkan-is d API base-is.
* Semsed `--api-base http://localhost:8080` i usekyed n backend tanarazt.
* Semsed `OMI_LOCAL_API_URL` d `OMI_LOCAL_TOKEN` akken ad tsebɛeḍ iɣewwaren n
  API n Desktop n profile i yiwet tikkelt.
* Semsed `--verbose` i tɣuṛi — yettaru `METHOD path → status (Ns)` ɣer stderr
  war ad yennɣeṣ stdout, ihi asker JSON yeqqim ameɣtu.
* I uǧǧal n ugbur deg udiwenni, semsed `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
