# omi-cli mō ngā māngai

> Aratohu mahi mō ngā taputapu e ārahina ana e LLM (Claude Code, Cursor, āu ake rōpū).

## He aha te CLI nei i ngāwari ai mō ngā māngai

* **Kirimana JSON pūmau.** Ka whakaputa `--json` i tētahi tuhinga JSON tūturu ki
  stdout — *ko te tuhinga JSON anake* — kāore he karere kauneke, kāore he
  porowhita. Ka tuku ngā hapa ki stderr kia pēnei `{"error": "...", "detail": "..."}`.
* **Ngā waehere puta pūmau.** `0` pai / `1` whakamahinga / `2` motuhēhēnga / `3`
  tūmau / `4` kua herea te tere / `5` kāore i kitea. Ka taea e ngā māngai te
  peka mā ēnei me te kore e tātari i ngā hapa reo māori.
* **Kāore he pātai pāhekoheko i ngā horopaki kore-ā-ringa.** Tukua `--yes`
  (ranei `-y`) ki ngā whakahau whakangaro; tukua `--api-key`, whakaritea rānei
  `OMI_API_KEY` hei peka i te takiuru pāhekoheko.
* **Whanonga whakamātau-anō hangawari.** Ka whakamātauria anōtia `429` me `5xx`
  me te hokinga whakamuri i mua i te whakaatu.

## Motuhēhēnga (kotahi anake, mā te tangata)

Ka whiwhi te kaiwhakamahi i tētahi kī API dev mai i te taupānga tukutuku Omi
(`https://app.omi.me` → Developer → API Keys) ā, ka kōwhiri pēnei:

```bash
omi auth login                          # tāpiri ā-ringa; kāore te kī i roto i te hītori shell
# ranei
export OMI_API_KEY=omi_dev_...          # rangitahi, pai mō te ipu
```

## Ngā mahi e rima e mahi nuitia ana e ngā māngai

### 1. Pānui i ngā pūmahara

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Waihanga pūmahara

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Pānui i ngā kōrerorero

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Pānui i ngā mahi e tuwhera ana

```bash
omi action-item list --json --open
```

### 5. Whakaoti i tētahi mahi

```bash
omi action-item complete --json a1b2c3d4
```

## API Papamahi ā-rohe

Ina whakaatu a Omi Desktop i tana API ā-rohe, ka taea e ngā māngai te uiui i te
hītori mata i runga i te pūrere, ngā whakarāpopototanga, SQL, me ngā mahi, me te
kore whakamahi i te API dev o te kapua:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# ranei, mō ngā wātū rangitahi:
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

Whakaotia, mukurua rānei ngā mahi ina uiui māramatia mai te kaiwhakamahi:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

Ka tuhia e `omi local screenshot SCREENSHOT_ID --output PATH` te whakaahua mata
ki te kōpae, ā, ka whakaputa tonu i te JSON ki stdout mō ngā tuhinga. Ko te ID o
te whakaahua mata ka puta mai i `local search-screen`, i te SQL rānei i runga i
te ripanga `screenshots`. Mēnā ka whakahokia mai e Desktop tētahi hapa hanganga
pēnei i `screenshot_pending`, `screenshot_file_missing`, `screenshot_chunk_corrupted`
ranei, ka tiakina e te aratau JSON ngā āpure `reason`, `hint`, me `screenshot_id`
i stderr kia taea ai e ngā māngai te whakamātau anō me tētahi ID tawhito, te
pūrongo rānei i te arai tūturu. Whakamanahia ngā putanga angitu me `file PATH` i
mua i te tuku ki ngā taputapu tirohanga.

## Tauira mahi: te koropiko māngai Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Whakamahia te CLI omi i roto i te aratau JSON, whakaarahia he hapa mēnā kāore te waehere puta i angitu."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # Ka whakaputa te CLI i ngā hapa hanganga ki stderr i te aratau JSON:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Pānuitia ngā mahi tuwhera katoa, ka tohu i ngā mea neke atu i te 30 rā kua oti.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Te whakahaere i ngā heretere

Pūmahara: 120/hāora. Kōrerorero: 25/hāora. Waihanga ā-rōpū: 15/hāora.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # kua herea te tere
    err = json.loads(result.stderr)
    # Ko te āhua o err["detail"]: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Tohutohu

* Whakamahia `--profile <name>` mēnā kei te whakahaere tō māngai i ngā pūkete
  Omi maha. Kei ia kōtaha tana ake taipitopito me tana API base.
* Whakamahia `--api-base http://localhost:8080` mō te whakamātau i te tuarā ā-rohe.
* Whakamahia `OMI_LOCAL_API_URL` me `OMI_LOCAL_TOKEN` hei whakakapi i ngā
  tautuhinga API Desktop o te kōtaha mō tētahi oma kotahi.
* Whakamahia `--verbose` mō te patuiro — ka tuhia e ia `METHOD path → status (Ns)` ki stderr
  me te kore whakararu i stdout, nō reira ka noho tūturu tonu te aratau JSON.
* Hei tuku ihirangi ki tētahi kōrerorero mā te paipa, whakamahia `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
