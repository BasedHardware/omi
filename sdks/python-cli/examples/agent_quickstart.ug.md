# omi-cli ۋەكىللەر ئۈچۈن

> LLM باشقۇرىدىغان harnesslar ئۈچۈن ئەمەلىي قوللانما (Claude Code, Cursor, ئۆزۈڭلارنىڭ botلىرى).

## CLI نېمىشقا ۋەكىللەرگە ماس كېلىدۇ

* **تۇراقلىق JSON كېلىشىمى.** `--json` stdout غا ئىناۋەتلىك JSON ھۆججىتىنى چىقىرىدۇ ۋە
  *پەقەت* JSON ھۆججىتى — ئىلگىرىلەش ئۇچۇرلىرى يوق، spinnerلار يوق. خاتالىقلار stderr غا
  `{"error": "...", "detail": "..."}` شەكلىدە كېتىدۇ.
* **تۇراقلىق چىقىش كودلىرى.** `0` ياخشى / `1` ئىشلىتىش / `2` auth / `3` مۇلازىمېتىر /
  `4` سۈرئەت چېكى / `5` تېپىلمىدى. ۋەكىللەر تەبىئىي تىل خاتالىقلارنى تەھلىل قىلماي
  بۇلارغا بۆلۈنەلەيدۇ.
* **headless مۇھىتتا ئۆزئارا تەسىرلىك promptلار يوق.** بۇزغۇنچىلىق بۇيرۇقلىرىغا `--yes`
  (يا `-y`) نى يەتكۈزۈڭ; `--api-key` نى يەتكۈزۈڭ ياكى `OMI_API_KEY` نى تەڭشىڭ —
  ئۆزئارا تەسىرلىك كىرىشنى ئاتلاش ئۈچۈن.
* **كەچۈرۈملۈك قايتا سىناق قىلمىسى.** `429` ۋە `5xx` پەيدا بولۇشتىن بۇرۇن backoff
  بىلەن قايتا سىنىلىدۇ.

## Auth (بىر قېتىم، ئادەم تەرىپىدىن)

ئىشلەتكۈچى Omi تور ئەپىدىن dev API كۈنچىكىنى ئالىدۇ
(`https://app.omi.me` → Developer → API Keys) ۋە يا:

```bash
omi auth login                          # ئۆزئارا تەسىرلىك چاپلاش; كۈنچىك shell تارىخىدا قالمايدۇ
# يا
export OMI_API_KEY=omi_dev_...          # ۋاقىتلىق، كونتېينېرلارغا ئەڭ ماس
```

## ۋەكىللەر ئەڭ كۆپ قىلىدىغان بەش ئىش

### 1. ئەستە ساقلاشلارنى ئوقۇش

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. ئەستە ساقلاش يارىتىش

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. سۆھبەتلەرنى ئوقۇش

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. ئوچۇق ھەرىكەت تۈرلىرىنى ئوقۇش

```bash
omi action-item list --json --open
```

### 5. ھەرىكەت تۈرىنى تاماملاندى دەپ بەلگىلەش

```bash
omi action-item complete --json a1b2c3d4
```

## يەرلىك Desktop API

Omi Desktop يەرلىك APIسىنى ئاشكارىلىغاندا، ۋەكىللەر ئۈسكۈنىنىڭ ئېكران تارىخى،
قىسقارتىلمىلىرى، SQL ۋە ۋەزىپىلەرنى بۇلۇت dev APIسىنى ئىشلەتمەي سورىيالايدۇ:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# يا، ۋاقىتلىق ئولتۇرۇشلار ئۈچۈن:
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

ۋەزىپىلەرنى پەقەت ئىشلەتكۈچى ئېنىق تەلەپ قىلغاندا تاماملاڭ ياكى ئۆچۈرۈڭ:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` ئېكران رەسىمنى دىسكىغا يازىدۇ
ۋە يەنە JSONنى stdout غا سكرىپتلار ئۈچۈن بېسىدۇ. ئېكران رەسىم IDسى ئادەتتە
`local search-screen` ياكى `screenshots` جەدۋىلىدىكى SQLدىن كېلىدۇ. ئەگەر Desktop
`screenshot_pending`، `screenshot_file_missing` ياكى `screenshot_chunk_corrupted`
كەبى قۇرۇلمىلىق خاتالىق قايتۇرسا، JSON ھالىتى `reason`، `hint` ۋە `screenshot_id`
ئېغىزلىرىنى stderr دا ساقلايدۇ — ۋەكىللەر كونا ID نى قايتا سىناپ ياكى دەل توسۇقنى
دوكلات قىلالايدۇ. مۇۋەپپەقىيەتلىك چىقىرىقلارنى `file PATH` بىلەن كۆرۈش قوراللىرىغا
يەتكۈزۈشتىن بۇرۇن تەكشۈرۈڭ.

## ئىشلەنگەن مىسال: Python ۋەكىل ئايلانمىسى

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

## سۈرئەت چەكلىمىلىرىنى باشقۇرۇش

ئەستە ساقلاشلار: 120/سائەت. سۆھبەتلەر: 25/سائەت. توپلۇق يارىتىشلار: 15/سائەت.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## مەسلىھەتلەر

* `--profile <name>` نى ئىشلىتىڭ ئەگەر ۋەكىلىڭىز بىر نەچچە Omi ھېساباتىنى باشقۇرىدۇ.
  ھەر بىر پروفىل ئۆزىنىڭ سالاھىيەت ۋە API ئاساسىغا ئىگە.
* `--api-base http://localhost:8080` نى يەرلىك backend سىناقلىرى ئۈچۈن ئىشلىتىڭ.
* `OMI_LOCAL_API_URL` ۋە `OMI_LOCAL_TOKEN` نى پروفىلنىڭ يەرلىك Desktop API
  تەڭشىكىنى بىر ئىجرا ئۈچۈن ئالماشتۇرۇش ئۈچۈن ئىشلىتىڭ.
* `--verbose` نى خاتالىق تازىلاش ئۈچۈن ئىشلىتىڭ — `METHOD path → status (Ns)` نى
  stderr غا stdout غا تەسىر كۆرسەتمەي خاتىرىلەيدۇ، شۇڭا JSON ھالىتى ئىناۋەتلىك قالىدۇ.
* مەزمۇننى بىر سۆھبەتكە pipe قىلىش ئۈچۈن `--text -` نى ئىشلىتىڭ:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
