# ஏஜெண்ட்களுக்கான omi-cli

> LLM-இயக்கும் ஏஜெண்ட் சூழல்களுக்கான (Claude Code, Cursor, உங்கள் சொந்த பாட்கள்) நடைமுறை வழிகாட்டி.

## CLI ஏன் ஏஜெண்ட்-நட்பானது

* **நிலையான JSON ஒப்பந்தம்.** `--json` stdout-க்கு சரியான JSON ஆவணத்தை வெளியிடும் —
  *JSON ஆவணம் மட்டுமே* — முன்னேற்றச் செய்திகள் இல்லை, ஸ்பின்னர்கள் இல்லை. பிழைகள்
  stderr-க்கு `{"error": "...", "detail": "..."}` வடிவில் செல்லும்.
* **நிலையான நிறைவுக் குறியீடுகள்.** `0` வெற்றி / `1` தவறான பயன்பாடு / `2` அங்கீகாரம் /
  `3` சர்வர் / `4` விகித வரம்பு / `5` கண்டறியப்படவில்லை. இயற்கை-மொழிப் பிழைகளைப்
  பாகுபடுத்தாமல் ஏஜெண்ட்கள் இந்தக் குறியீடுகளின் அடிப்படையில் கிளைக்க முடியும்.
* **ஹெட்லெஸ் சூழல்களில் ஊடாடும் கேள்விகள் இல்லை.** அழிவுகரமான கட்டளைகளுக்கு
  `--yes` (அல்லது `-y`) அளிக்கவும்; ஊடாடும் உள்நுழைவைத் தவிர்க்க `--api-key`
  அளிக்கவும் அல்லது `OMI_API_KEY` அமைக்கவும்.
* **பொறுத்தருளும் மறுமுயற்சி நடத்தை.** `429` மற்றும் `5xx` வெளிப்படுவதற்கு முன்
  பின்னடைவுடன் (backoff) மீண்டும் முயற்சிக்கப்படும்.

## அங்கீகாரம் (ஒருமுறை, மனிதரால்)

பயனர் Omi வலை ஆப்பில் (`https://app.omi.me` → Developer → API Keys) இருந்து டெவ் API
விசையைப் பெற்று, பின்வற்றில் ஒன்றைச் செய்யலாம்:

```bash
omi auth login                          # ஊடாடும் ஒட்டுதல்; விசை shell வரலாற்றில் இருக்காது
# அல்லது
export OMI_API_KEY=omi_dev_...          # தற்காலிகமானது, கொள்கலனுக்கு ஏற்றது
```

## ஏஜெண்ட்கள் அதிகம் செய்யும் ஐந்து விஷயங்கள்

### 1. நினைவுகளைப் படிக்கவும்

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. ஒரு நினைவை உருவாக்கவும்

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. உரையாடல்களைப் படிக்கவும்

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. திறந்த செயல் உருப்படிகளைப் படிக்கவும்

```bash
omi action-item list --json --open
```

### 5. ஒரு செயல் உருப்படியை முடிக்கவும்

```bash
omi action-item complete --json a1b2c3d4
```

## லோக்கல் டெஸ்க்டாப் API

Omi Desktop அதன் லோக்கல் API-ஐ வெளிப்படுத்தும்போது, கிளவுட் டெவ் API-ஐப்
பயன்படுத்தாமல் ஏஜெண்ட்கள் சாதனத்தின் திரை வரலாறு, சுருக்கங்கள், SQL மற்றும்
பணிகளை வினவ முடியும்:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# அல்லது, தற்காலிக அமர்வுகளுக்கு:
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

பயனர் தெளிவாகக் கேட்டால் மட்டுமே பணிகளை முடிக்கவும் அல்லது நீக்கவும்:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` ஸ்கிரீன்ஷாட்டை வட்டில் எழுதி,
ஸ்கிரிப்ட்களுக்காக stdout-க்கு JSON-ஐ அச்சிடும். ஸ்கிரீன்ஷாட் ஐடி பொதுவாக
`local search-screen` அல்லது `screenshots` அட்டவணை மீதான SQL-இல் இருந்து வரும்.
Desktop `screenshot_pending`, `screenshot_file_missing` அல்லது
`screenshot_chunk_corrupted` போன்ற கட்டமைக்கப்பட்ட தோல்வியை வழங்கினால், JSON
பயன்முறை stderr-இல் `reason`, `hint` மற்றும் `screenshot_id` புலங்களைப்
பாதுகாக்கிறது — இதனால் ஏஜெண்ட்கள் பழைய ஐடியுடன் மீண்டும் முயற்சிக்கவோ சரியான
தடையைத் தெரிவிக்கவோ முடியும். வெற்றிகரமான வெளியீடுகளை விஷன் கருவிகளுக்கு
அனுப்பும் முன் `file PATH` மூலம் சரிபார்க்கவும்.

## செயல்வழி எடுத்துக்காட்டு: Python ஏஜெண்ட் லூப்

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """omi CLI-ஐ JSON பயன்முறையில் இயக்கி, தோல்வி நிறைவுக் குறியீடுகளில் விதிவிலக்கு எழுப்பும்."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI JSON பயன்முறையில் stderr-க்கு கட்டமைக்கப்பட்ட பிழைகளை அச்சிடும்:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# திறந்த செயல் உருப்படிகள் அனைத்தையும் படித்து, 30 நாட்களுக்கு மூத்தவற்றை முடிக்கவும்.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## விகித வரம்புகளைக் கையாளுதல்

நினைவுகள்: 120/மணி. உரையாடல்கள்: 25/மணி. தொகுதி உருவாக்கங்கள்: 15/மணி.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # விகித வரம்பு
    err = json.loads(result.stderr)
    # err["detail"] இப்படி இருக்கும்: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## குறிப்புகள்

* உங்கள் ஏஜெண்ட் பல Omi கணக்குகளைக் கையாள்வதென்றால் `--profile <name>`
  பயன்படுத்தவும். ஒவ்வொரு சுயவிவரத்துக்கும் அதன் சொந்தச் சான்றுகளும் API
  அடிப்படையும் இருக்கும்.
* லோக்கல் பின்தளச் சோதனைக்கு `--api-base http://localhost:8080` பயன்படுத்தவும்.
* ஒரு இயக்கத்திற்கு சுயவிவர-லோக்கல் Desktop API அமைப்புகளை மேலெழுத
  `OMI_LOCAL_API_URL` மற்றும் `OMI_LOCAL_TOKEN` பயன்படுத்தவும்.
* பிழைதிருத்தத்திற்கு `--verbose` பயன்படுத்தவும் — இது stderr-க்கு
  `METHOD path → status (Ns)`-ஐப் பதிவுசெய்யும், stdout-ஐப் பாதிக்காது, எனவே
  JSON பயன்முறை செல்லுபடியாகவே இருக்கும்.
* குழாய் வழியாக உரையாடலில் உள்ளடக்கத்தைச் செலுத்த `--text -` பயன்படுத்தவும்:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
