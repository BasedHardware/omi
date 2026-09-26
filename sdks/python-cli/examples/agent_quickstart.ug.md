# omi-cli ئايگېنتلار ئۈچۈن

> LLM تەرىپىدىن باشقۇرۇلىدىغان مۇھىتلار ئۈچۈن ئەمەلىي قوللانما (Claude Code, Cursor, ئۆزىڭىزنىڭ بوتلىرى).

## نېمىشقا CLI ئايگېنتلارغا قولايلىق

* **مۇقىم JSON كېلىشىمى.** `--json` stdout غا ئىشلەتكىلى بولىدىغان JSON ھۆججىتىنىلا
  چىقىرىدۇ — *پەقەت* JSON ھۆججىتى، ئىلگىرىلەش ئۇچۇرى يوق، spinner يوق. خاتالىقلار
  stderr غا `{"error": "...", "detail": "..."}` شەكلىدە چىقىرىلىدۇ.
* **مۇقىم چىقىش كودلىرى.** `0` نورمال / `1` ئىشلىتىش خاتالىقى / `2` دەلىللەش / `3`
  مۇلازىمېتەر / `4` سۈرئەت چەكلەندى / `5` تېپىلمىدى. ئايگېنتلار تەبىئىي تىلدىكى
  خاتالىقلارنى تەھلىل قىلماي، مۇشۇ كودلارغا ئاساسەن شاخلىنالايدۇ.
* **headless مۇھىتتا ئۆز-ئارا سۆھبەت يوق.** بۇزغۇچى بۇيرۇقلارغا `--yes` (ياكى `-y`)
  بېرىڭ؛ ئۆز-ئارا كىرىشنى ئاتلاپ ئۆتۈش ئۈچۈن `--api-key` بېرىڭ ياكى `OMI_API_KEY`
  نى تەڭشەڭ.
* **كەچۈرۈمچان قايتا سىناش.** `429` ۋە `5xx` خاتالىقلىرى ئاشكارىلانشتىن بۇرۇن
  backoff بىلەن قايتا سىنىلىدۇ.

## دەلىللەش (بىر قېتىملىق، ئىنسان تەرىپىدىن)

ئىشلەتكۈچى Omi تور ئەپلىكەتسىيەسىدىن dev API ئاچقۇچى ئالىدۇ
(`https://app.omi.me` → Developer → API Keys) ۋە تۆۋەندىكىلەرنىڭ بىرىنى تاللايدۇ:

```bash
omi auth login                          # ئۆز-ئارا چاپلاش؛ ئاچقۇچ shell تارىخىغا كىرمەيدۇ
# ياكى
export OMI_API_KEY=omi_dev_...          # ۋاقىتلىق، كونتىينېرغا ماس كېلىدۇ
```

## ئايگېنتلار ئەڭ كۆپ قىلىدىغان بەش ئىش

### 1. ئەسلىمىلەرنى ئوقۇش

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. ئەسلىمە قۇرۇش

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

Omi Desktop يەرلىك API سىنى ئاشكارىلىغاندا، ئايگېنتلار بۇلۇت dev API سىنى
ئىشلەتمەي تۇرۇپ ئۈسكۈنىدىكى ئېكران تارىخى، خۇلاسىلەر، SQL ۋە ۋەزىپىلەرنى
سورايدۇ:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# ياكى، ۋاقىتلىق سېسسىيەلەر ئۈچۈن:
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

ۋەزىپىلەرنى پەقەت ئىشلەتكۈچى ئېنىق تەلەپ قىلغاندىلا تاماملاڭ ياكى ئۆچۈرۈڭ:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` ئېكران كۆرۈنۈشىنى disk قا
يازىدۇ ۋە سىكرىپتلار ئۈچۈن stdout غا JSON چىقىرىشنى داۋاملاشتۇرىدۇ. ئېكران
كۆرۈنۈشى ID ئادەتتە `local search-screen` ياكى `screenshots` جەدۋىلىدىكى SQL
دىن كېلىدۇ. ئەگەر Desktop `screenshot_pending`، `screenshot_file_missing` ياكى
`screenshot_chunk_corrupted` قاتارلىق قۇرۇلمىلىق مەغلۇبىيەت قايتۇرسا، JSON
ھالىتى stderr دا `reason`، `hint` ۋە `screenshot_id` بۆلەكلىرىنى ساقلاپ
قالىدۇ، شۇنداق قىلىپ ئايگېنتلار كونا ID بىلەن قايتا سىنايدۇ ياكى توغرا
توسالغۇنى دوكلات قىلىدۇ. مۇۋەپپەقىيەتلىك چىقىرىشلارنى vision قوراللىرىغا
يەتكۈزۈشتىن بۇرۇن `file PATH` بىلەن دەلىللەڭ.

## ئەمەلىي مىسال: Python ئايگېنت ھالقىسى

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """omi CLI نى JSON ھالىتىدە چاقىرىدۇ، مۇۋەپپەقىيەتسىز چىقىش كودىدا ئىستىسنا كۆتۈرىدۇ."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI JSON ھالىتىدە قۇرۇلمىلىق خاتالىقلارنى stderr غا چىقىرىدۇ:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# بارلىق ئوچۇق ھەرىكەت تۈرلىرىنى ئوقۇپ، 30 كۈندىن ئاشقانلىرىنى تاماملاندى دەپ بەلگىلەڭ.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## سۈرئەت چەكلىمىلىرىنى بىر تەرەپ قىلىش

ئەسلىمىلەر: 120/سائەت. سۆھبەتلەر: 25/سائەت. توپلۇق قۇرۇش: 15/سائەت.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # سۈرئەت چەكلەندى
    err = json.loads(result.stderr)
    # err["detail"] مۇنداق كۆرۈنىدۇ: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## تەۋسىيەلەر

* ئەگەر ئايگېنتىڭىز بىر قانچە Omi ھېساباتىنى باشقۇرسا، `--profile <name>` نى
  ئىشلىتىڭ. ھەر بىر profil نىڭ ئۆزىنىڭ كىنىشكىسى ۋە API base ى بار.
* يەرلىك backend نى سىناش ئۈچۈن `--api-base http://localhost:8080` نى ئىشلىتىڭ.
* بىر قېتىملىق يۈرگۈزۈشتە profil نىڭ يەرلىك Desktop API تەڭشەكلىرىنى
  ئالماشتۇرۇش ئۈچۈن `OMI_LOCAL_API_URL` ۋە `OMI_LOCAL_TOKEN` نى ئىشلىتىڭ.
* ئەلالاشتۇرۇش ئۈچۈن `--verbose` نى ئىشلىتىڭ — ئۇ stderr غا
  `METHOD path → status (Ns)` نى خاتىرىلەيدۇ، stdout غا تەسىر كۆرسەتمەيدۇ،
  شۇڭا JSON ھالىتى ئىشلەتكىلى بولىدىغان بولۇپ قالىدۇ.
* مەزمۇننى pipe ئارقىلىق سۆھبەتكە كىرگۈزۈش ئۈچۈن `--text -` نى ئىشلىتىڭ:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
