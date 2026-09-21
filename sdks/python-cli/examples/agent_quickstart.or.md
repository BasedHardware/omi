# ଏଜେଣ୍ଟମାନଙ୍କ ପାଇଁ omi-cli

> LLM-ଚାଳିତ ଏଜେଣ୍ଟ ପରିବେଶ ପାଇଁ (Claude Code, Cursor, ଆପଣଙ୍କ ନିଜ ବଟ୍) ବ୍ୟବହାରିକ ଗାଇଡ୍।

## CLI କାହିଁକି ଏଜେଣ୍ଟ-ଅନୁକୂଳ

* **ସ୍ଥିର JSON ଚୁକ୍ତି।** `--json` stdout କୁ ଏକ ବୈଧ JSON ଡକ୍ୟୁମେଣ୍ଟ ପଠାଏ ଏବଂ
  *କେବଳ* ଏକ JSON ଡକ୍ୟୁମେଣ୍ଟ — କୌଣସି ପ୍ରଗତି ବାର୍ତ୍ତା ନାହିଁ, କୌଣସି ସ୍ପିନର ନାହିଁ।
  ତ୍ରୁଟିଗୁଡ଼ିକ stderr କୁ `{"error": "...", "detail": "..."}` ଆକାରରେ ଯାଏ।
* **ସ୍ଥିର ଏକ୍ଜିଟ୍ କୋଡ୍।** `0` ସଫଳ / `1` ଭୁଲ ବ୍ୟବହାର / `2` ପ୍ରମାଣୀକରଣ /
  `3` ସର୍ଭର / `4` ହାର ସୀମିତ / `5` ମିଳିଲା ନାହିଁ। ଏଜେଣ୍ଟମାନେ ପ୍ରାକୃତିକ-ଭାଷା
  ତ୍ରୁଟିଗୁଡ଼ିକୁ ପାର୍ସ ନକରି ଏହି କୋଡ୍ ଉପରେ ଶାଖା କରିପାରିବେ।
* **ହେଡଲେସ୍ ପରିସ୍ଥିତିରେ କୌଣସି ଇଣ୍ଟରାକ୍ଟିଭ୍ ପ୍ରମ୍ପ୍ଟ ନାହିଁ।** ବିନାଶକାରୀ କମାଣ୍ଡ ପାଇଁ
  `--yes` (କିମ୍ବା `-y`) ଦିଅନ୍ତୁ; ଇଣ୍ଟରାକ୍ଟିଭ୍ ଲଗଇନ୍ ଏଡ଼ାଇବା ପାଇଁ `--api-key`
  ଦିଅନ୍ତୁ କିମ୍ବା `OMI_API_KEY` ସେଟ୍ କରନ୍ତୁ।
* **କ୍ଷମାଶୀଳ ପୁନଃପ୍ରୟାସ ଆଚରଣ।** `429` ଏବଂ `5xx` ଦେଖାଯିବା ପୂର୍ବରୁ ବ୍ୟାକଅଫ୍ ସହିତ
  ପୁଣି ଚେଷ୍ଟା କରାଯାଏ।

## ପ୍ରମାଣୀକରଣ (ଥରେ, ମନୁଷ୍ୟ ଦ୍ୱାରା)

ଉପଭୋକ୍ତା Omi ୱେବ୍ ଆପ୍ (`https://app.omi.me` → Developer → API Keys) ରୁ ଏକ ଡେଭ୍ API
କୀ ନେଇ ଏଥିମଧ୍ୟରୁ ଗୋଟିଏ ବାଛନ୍ତି:

```bash
omi auth login                          # ଇଣ୍ଟରାକ୍ଟିଭ୍ ପେଷ୍ଟ; କୀ shell ଇତିହାସରେ ରହେ ନାହିଁ
# କିମ୍ବା
export OMI_API_KEY=omi_dev_...          # କ୍ଷଣସ୍ଥାୟୀ, କଣ୍ଟେନର-ଅନୁକୂଳ
```

## ଏଜେଣ୍ଟମାନେ ସର୍ବାଧିକ କରୁଥିବା ପାଞ୍ଚଟି କାମ

### 1. ସ୍ମୃତିଗୁଡ଼ିକ ପଢ଼ନ୍ତୁ

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. ଏକ ସ୍ମୃତି ସୃଷ୍ଟି କରନ୍ତୁ

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. କଥାବାର୍ତ୍ତାଗୁଡ଼ିକ ପଢ଼ନ୍ତୁ

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. ଖୋଲା ଆକ୍ସନ୍ ଆଇଟମଗୁଡ଼ିକ ପଢ଼ନ୍ତୁ

```bash
omi action-item list --json --open
```

### 5. ଏକ ଆକ୍ସନ୍ ଆଇଟମ୍ ସମ୍ପୂର୍ଣ୍ଣ କରନ୍ତୁ

```bash
omi action-item complete --json a1b2c3d4
```

## ଲୋକାଲ୍ ଡେସ୍କଟପ୍ API

ଯେତେବେଳେ Omi Desktop ତାର ଲୋକାଲ୍ API ପ୍ରକାଶ କରେ, ଏଜେଣ୍ଟମାନେ କ୍ଲାଉଡ୍ ଡେଭ୍ API
ବ୍ୟବହାର ନକରି ଡିଭାଇସର ସ୍କ୍ରିନ୍ ଇତିହାସ, ସାରାଂଶ, SQL ଏବଂ କାର୍ଯ୍ୟ କ୍ୱେରୀ କରିପାରିବେ:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# କିମ୍ବା, କ୍ଷଣସ୍ଥାୟୀ ସେସନ୍ ପାଇଁ:
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

ଉପଭୋକ୍ତା ସ୍ପଷ୍ଟ ଭାବରେ ନକହିଲେ କାର୍ଯ୍ୟଗୁଡ଼ିକ ସମ୍ପୂର୍ଣ୍ଣ କରନ୍ତୁ ନାହିଁ କିମ୍ବା ବିଲୋପ କରନ୍ତୁ ନାହିଁ:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` ସ୍କ୍ରିନସଟ୍ କୁ ଡିସ୍କରେ ଲେଖେ ଏବଂ
ସ୍କ୍ରିପ୍ଟ ପାଇଁ stdout କୁ JSON ପ୍ରିଣ୍ଟ କରେ। ସ୍କ୍ରିନସଟ୍ ଆଇଡି ସାଧାରଣତଃ
`local search-screen` ରୁ କିମ୍ବା `screenshots` ଟେବୁଲ ଉପରେ SQL ରୁ ଆସେ। Desktop ଯଦି
`screenshot_pending`, `screenshot_file_missing` କିମ୍ବା `screenshot_chunk_corrupted`
ଭଳି ସଂରଚିତ ବିଫଳତା ଫେରାଏ, JSON ମୋଡ୍ stderr ରେ `reason`, `hint` ଏବଂ
`screenshot_id` ଫିଲ୍ଡ ସଂରକ୍ଷଣ କରେ, ଯାହାଫଳରେ ଏଜେଣ୍ଟମାନେ ପୁରୁଣା ଆଇଡି ସହିତ ପୁଣି
ଚେଷ୍ଟା କରିପାରିବେ କିମ୍ବା ସଠିକ୍ ପ୍ରତିବନ୍ଧକ ରିପୋର୍ଟ କରିପାରିବେ। ସଫଳ ଆଉଟପୁଟଗୁଡ଼ିକୁ
ଭିଜନ୍ ଟୁଲକୁ ପଠାଇବା ପୂର୍ବରୁ `file PATH` ସହିତ ଯାଞ୍ଚ କରନ୍ତୁ।

## କାର୍ଯ୍ୟପ୍ରବାହ ଉଦାହରଣ: Python ଏଜେଣ୍ଟ ଲୁପ୍

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """omi CLI କୁ JSON ମୋଡରେ ଚଲାଏ, ବିଫଳ ଏକ୍ଜିଟ୍ କୋଡରେ ଏକ୍ସେପ୍ସନ ଉଠାଏ।"""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI JSON ମୋଡରେ stderr କୁ ସଂରଚିତ ତ୍ରୁଟି ପ୍ରିଣ୍ଟ କରେ:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# ସମସ୍ତ ଖୋଲା ଆକ୍ସନ୍ ଆଇଟମ ପଢ଼ନ୍ତୁ ଏବଂ 30 ଦିନରୁ ପୁରୁଣା ସମ୍ପୂର୍ଣ୍ଣ କରନ୍ତୁ।
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## ହାର ସୀମା ପରିଚାଳନା

ସ୍ମୃତି: 120/ଘଣ୍ଟା। କଥାବାର୍ତ୍ତା: 25/ଘଣ୍ଟା। ବ୍ୟାଚ୍ ସୃଷ୍ଟି: 15/ଘଣ୍ଟା।

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # ହାର ସୀମିତ
    err = json.loads(result.stderr)
    # err["detail"] ଏପରି ଦେଖାଯାଏ: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## ଟିପ୍ସ

* ଆପଣଙ୍କ ଏଜେଣ୍ଟ ଏକାଧିକ Omi ଖାତା ସମ୍ଭାଳୁଥିଲେ `--profile <name>` ବ୍ୟବହାର କରନ୍ତୁ।
  ପ୍ରତ୍ୟେକ ପ୍ରୋଫାଇଲର ନିଜସ୍ୱ କ୍ରେଡେନସିଆଲ୍ ଏବଂ API ବେସ୍ ଥାଏ।
* ଲୋକାଲ୍ ବ୍ୟାକଏଣ୍ଡ ପରୀକ୍ଷା ପାଇଁ `--api-base http://localhost:8080` ବ୍ୟବହାର କରନ୍ତୁ।
* ଗୋଟିଏ ରନ୍ ପାଇଁ ପ୍ରୋଫାଇଲ୍-ଲୋକାଲ୍ Desktop API ସେଟିଂସ୍ ଓଭରରାଇଡ୍ କରିବାକୁ
  `OMI_LOCAL_API_URL` ଏବଂ `OMI_LOCAL_TOKEN` ବ୍ୟବହାର କରନ୍ତୁ।
* ଡିବଗିଂ ପାଇଁ `--verbose` ବ୍ୟବହାର କରନ୍ତୁ — ଏହା stderr କୁ `METHOD path → status (Ns)`
  ଲଗ୍ କରେ, stdout କୁ ପ୍ରଭାବିତ କରେ ନାହିଁ, ତେଣୁ JSON ମୋଡ୍ ବୈଧ ରହେ।
* ପାଇପ୍ ମାଧ୍ୟମରେ କଥାବାର୍ତ୍ତାରେ ବିଷୟବସ୍ତୁ ପଠାଇବାକୁ `--text -` ବ୍ୟବହାର କରନ୍ତୁ:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
