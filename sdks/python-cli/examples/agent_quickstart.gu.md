# એજન્ટો માટે omi-cli

> LLM-સંચાલિત એજન્ટ વાતાવરણ માટે (Claude Code, Cursor, તમારા પોતાના બોટ) વ્યવહારુ માર્ગદર્શિકા.

## CLI એજન્ટ-અનુકૂળ કેમ છે

* **સ્થિર JSON કરાર.** `--json` stdout પર માન્ય JSON દસ્તાવેજ મોકલે છે અને
  *ફક્ત* એક JSON દસ્તાવેજ — કોઈ પ્રગતિ સંદેશા નહીં, કોઈ સ્પિનર નહીં. ભૂલો
  stderr પર `{"error": "...", "detail": "..."}` સ્વરૂપે જાય છે.
* **સ્થિર એક્ઝિટ કોડ.** `0` સફળ / `1` ખોટો વપરાશ / `2` પ્રમાણીકરણ /
  `3` સર્વર / `4` દર-મર્યાદિત / `5` મળ્યું નથી. એજન્ટો કુદરતી-ભાષાની ભૂલો
  પાર્સ કર્યા વિના આ કોડ પર શાખા બનાવી શકે છે.
* **હેડલેસ સંદર્ભોમાં કોઈ ઇન્ટરેક્ટિવ પ્રોમ્પ્ટ નથી.** વિનાશક આદેશો માટે
  `--yes` (અથવા `-y`) આપો; ઇન્ટરેક્ટિવ લોગિન ટાળવા `--api-key` આપો
  અથવા `OMI_API_KEY` સેટ કરો.
* **સહનશીલ ફરી-પ્રયાસ વર્તન.** `429` અને `5xx` સામે આવે તે પહેલાં બેકઓફ સાથે
  ફરી પ્રયાસ કરવામાં આવે છે.

## પ્રમાણીકરણ (એક વાર, માણસ દ્વારા)

વપરાશકર્તા Omi વેબ એપ (`https://app.omi.me` → Developer → API Keys) પરથી ડેવ API
કી મેળવે છે અને આમાંથી એક પસંદ કરે છે:

```bash
omi auth login                          # ઇન્ટરેક્ટિવ પેસ્ટ; કી shell ઇતિહાસમાં રહેતી નથી
# અથવા
export OMI_API_KEY=omi_dev_...          # ક્ષણિક, કન્ટેનર-અનુકૂળ
```

## એજન્ટો સૌથી વધુ કરે છે તે પાંચ વસ્તુઓ

### 1. યાદો વાંચો

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. યાદ બનાવો

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. વાતચીતો વાંચો

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. ખુલ્લા એક્શન આઇટમ્સ વાંચો

```bash
omi action-item list --json --open
```

### 5. એક્શન આઇટમ પૂર્ણ કરો

```bash
omi action-item complete --json a1b2c3d4
```

## લોકલ ડેસ્કટોપ API

જ્યારે Omi Desktop તેનું લોકલ API ખુલ્લું કરે છે, ત્યારે એજન્ટો ક્લાઉડ ડેવ API
વાપર્યા વિના ઉપકરણની સ્ક્રીન ઇતિહાસ, સારાંશ, SQL અને કાર્યોની ક્વેરી કરી શકે છે:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# અથવા, ક્ષણિક સત્રો માટે:
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

વપરાશકર્તા સ્પષ્ટ રીતે કહે તો જ કાર્યો પૂર્ણ કરો કે ડિલીટ કરો:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` સ્ક્રીનશોટ ડિસ્ક પર લખે છે
અને સ્ક્રિપ્ટો માટે stdout પર JSON પ્રિન્ટ કરે છે. સ્ક્રીનશોટ આઇડી સામાન્ય રીતે
`local search-screen` અથવા `screenshots` ટેબલ પરની SQL પરથી આવે છે. જો Desktop
`screenshot_pending`, `screenshot_file_missing` કે `screenshot_chunk_corrupted` જેવી
સંરચિત નિષ્ફળતા પરત આપે, તો JSON મોડ stderr પર `reason`, `hint` અને
`screenshot_id` ફીલ્ડ સાચવે છે જેથી એજન્ટો જૂની આઇડી સાથે ફરી પ્રયાસ કરી શકે
અથવા ચોક્કસ અવરોધ જણાવી શકે. સફળ આઉટપુટ વિઝન ટૂલ્સને મોકલતા પહેલાં
`file PATH` થી ચકાસો.

## કાર્યપ્રવાહ ઉદાહરણ: Python એજન્ટ લૂપ

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """omi CLI ને JSON મોડમાં ચલાવે છે, નિષ્ફળ એક્ઝિટ કોડ પર અપવાદ ઉઠાવે છે."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI JSON મોડમાં stderr પર સંરચિત ભૂલો પ્રિન્ટ કરે છે:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# બધા ખુલ્લા એક્શન આઇટમ્સ વાંચો અને 30 દિવસથી જૂનાં પૂર્ણ કરો.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## દર મર્યાદા સંભાળવી

યાદો: 120/કલાક. વાતચીતો: 25/કલાક. બેચ બનાવટ: 15/કલાક.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # દર-મર્યાદિત
    err = json.loads(result.stderr)
    # err["detail"] આવું દેખાય છે: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## ટિપ્સ

* જો તમારો એજન્ટ અનેક Omi એકાઉન્ટ સંભાળે તો `--profile <name>` વાપરો. દરેક
  પ્રોફાઇલની પોતાની ક્રેડેન્શિયલ્સ અને API બેઝ હોય છે.
* લોકલ બેકએન્ડ પરીક્ષણ માટે `--api-base http://localhost:8080` વાપરો.
* એક રન માટે પ્રોફાઇલ-લોકલ Desktop API સેટિંગ્સ ઓવરરાઇડ કરવા
  `OMI_LOCAL_API_URL` અને `OMI_LOCAL_TOKEN` વાપરો.
* ડિબગિંગ માટે `--verbose` વાપરો — તે stderr પર `METHOD path → status (Ns)`
  લોગ કરે છે, stdout ને અસર કરતું નથી, તેથી JSON મોડ માન્ય રહે છે.
* પાઇપ દ્વારા વાતચીતમાં સામગ્રી મોકલવા `--text -` વાપરો:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
