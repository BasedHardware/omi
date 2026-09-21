# ఏజెంట్‌ల కోసం omi-cli

> LLM-నడిచే ఏజెంట్ వాతావరణాల కోసం (Claude Code, Cursor, మీ స్వంత బాట్‌లు) ఆచరణాత్మక మార్గదర్శిని.

## CLI ఏజెంట్-అనుకూలం ఎందుకు

* **స్థిరమైన JSON ఒప్పందం.** `--json` stdout కు చెల్లుబాటు అయ్యే JSON పత్రాన్ని పంపుతుంది
  మరియు *JSON పత్రాన్ని మాత్రమే* — ప్రగతి సందేశాలు లేవు, స్పిన్నర్‌లు లేవు. లోపాలు
  stderr కు `{"error": "...", "detail": "..."}` రూపంలో వెళ్తాయి.
* **స్థిరమైన నిష్క్రమణ కోడ్‌లు.** `0` విజయం / `1` తప్పు వినియోగం / `2` ప్రామాణీకరణ /
  `3` సర్వర్ / `4` రేటు పరిమితి / `5` కనుగొనబడలేదు. సహజ-భాషా లోపాలను
  విశ్లేషించకుండానే ఏజెంట్‌లు ఈ కోడ్‌లపై శాఖలు చేయగలరు.
* **హెడ్‌లెస్ సందర్భాల్లో ఇంటరాక్టివ్ ప్రాంప్ట్‌లు లేవు.** విధ్వంసక ఆదేశాలకు
  `--yes` (లేదా `-y`) ఇవ్వండి; ఇంటరాక్టివ్ లాగిన్‌ను దాటవేయడానికి `--api-key`
  ఇవ్వండి లేదా `OMI_API_KEY` సెట్ చేయండి.
* **క్షమాగుణం కలిగిన రీట్రై ప్రవర్తన.** `429` మరియు `5xx` బయటపడే ముందు బ్యాకాఫ్‌తో
  మళ్లీ ప్రయత్నించబడతాయి.

## ప్రామాణీకరణ (ఒకసారి, మనిషి ద్వారా)

వినియోగదారు Omi వెబ్ యాప్ (`https://app.omi.me` → Developer → API Keys) నుండి డెవ్ API
కీని పొంది, వీటిలో ఒకటి చేస్తారు:

```bash
omi auth login                          # ఇంటరాక్టివ్ పేస్ట్; కీ shell చరిత్రలో ఉండదు
# లేదా
export OMI_API_KEY=omi_dev_...          # తాత్కాలికం, కంటైనర్-అనుకూలం
```

## ఏజెంట్‌లు ఎక్కువగా చేసే ఐదు పనులు

### 1. జ్ఞాపకాలు చదవండి

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. జ్ఞాపకాన్ని సృష్టించండి

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. సంభాషణలు చదవండి

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. తెరిచిన యాక్షన్ ఐటమ్‌లు చదవండి

```bash
omi action-item list --json --open
```

### 5. యాక్షన్ ఐటమ్‌ను పూర్తి చేయండి

```bash
omi action-item complete --json a1b2c3d4
```

## లోకల్ డెస్క్‌టాప్ API

Omi Desktop తన లోకల్ API ను అందుబాటులో ఉంచినప్పుడు, క్లౌడ్ డెవ్ API ఉపయోగించకుండా
ఏజెంట్‌లు పరికరంలోని స్క్రీన్ చరిత్ర, సారాంశాలు, SQL మరియు టాస్క్‌లను క్వెరీ చేయగలరు:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# లేదా, తాత్కాలిక సెషన్‌ల కోసం:
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

వినియోగదారు స్పష్టంగా అడిగినప్పుడే టాస్క్‌లను పూర్తి చేయండి లేదా తొలగించండి:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` స్క్రీన్‌షాట్‌ను డిస్క్‌కు రాస్తుంది
మరియు స్క్రిప్ట్‌ల కోసం stdout కు JSON ను ప్రింట్ చేస్తుంది. స్క్రీన్‌షాట్ ఐడీ సాధారణంగా
`local search-screen` నుండి లేదా `screenshots` టేబుల్‌పై SQL నుండి వస్తుంది. Desktop
`screenshot_pending`, `screenshot_file_missing` లేదా `screenshot_chunk_corrupted`
వంటి నిర్మిత వైఫల్యాన్ని తిరిగి ఇచ్చినట్లయితే, JSON మోడ్ stderr పై `reason`, `hint`
మరియు `screenshot_id` ఫీల్డ్‌లను భద్రపరుస్తుంది, తద్వారా ఏజెంట్‌లు పాత ఐడీతో
మళ్లీ ప్రయత్నించవచ్చు లేదా ఖచ్చితమైన అడ్డంకిని నివేదించవచ్చు. విజన్ టూల్స్‌కు
పంపే ముందు విజయవంతమైన అవుట్‌పుట్‌లను `file PATH` తో ధృవీకరించండి.

## పనితీరు ఉదాహరణ: Python ఏజెంట్ లూప్

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """omi CLI ను JSON మోడ్‌లో నడిపిస్తుంది, విఫల నిష్క్రమణ కోడ్‌లపై మినహాయింపు విసురుతుంది."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI JSON మోడ్‌లో stderr కు నిర్మిత లోపాలను ప్రింట్ చేస్తుంది:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# తెరిచిన యాక్షన్ ఐటమ్‌లన్నీ చదివి, 30 రోజుల కంటే పాతవి పూర్తి చేయండి.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## రేటు పరిమితులను నిర్వహించడం

జ్ఞాపకాలు: 120/గం. సంభాషణలు: 25/గం. బ్యాచ్ సృష్టులు: 15/గం.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # రేటు పరిమితి
    err = json.loads(result.stderr)
    # err["detail"] ఇలా ఉంటుంది: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## చిట్కాలు

* మీ ఏజెంట్ అనేక Omi ఖాతాలను నిర్వహిస్తే `--profile <name>` ఉపయోగించండి. ప్రతి
  ప్రొఫైల్‌కు దాని స్వంత ఆధారాలు మరియు API బేస్ ఉంటాయి.
* లోకల్ బ్యాకెండ్ పరీక్ష కోసం `--api-base http://localhost:8080` ఉపయోగించండి.
* ఒక రన్ కోసం ప్రొఫైల్-లోకల్ Desktop API సెట్టింగ్‌లను ఓవర్‌రైడ్ చేయడానికి
  `OMI_LOCAL_API_URL` మరియు `OMI_LOCAL_TOKEN` ఉపయోగించండి.
* డీబగ్గింగ్ కోసం `--verbose` ఉపయోగించండి — ఇది stderr కు `METHOD path → status (Ns)`
  లాగ్ చేస్తుంది, stdout ను ప్రభావితం చేయదు, కాబట్టి JSON మోడ్ చెల్లుబాటులో ఉంటుంది.
* పైప్ ద్వారా సంభాషణలోకి కంటెంట్ పంపడానికి `--text -` ఉపయోగించండి:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
