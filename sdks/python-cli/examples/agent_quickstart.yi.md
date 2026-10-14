# omi-cli פֿאַר אַגענטן

> אַ פּראַקטישער גײַד פֿאַר LLM-געפֿירטע harnesses (Claude Code, Cursor, דיין אייגענע באָטן).

## פֿאַר וואָס די CLI איז פרײַנדלעך צו אַגענטן

* **סטאַבילער JSON קאָנטראַקט.** `--json` גיט אויס אַ וואַלידן JSON דאָקומענט אויף
  stdout און *בלײַז* אַ JSON דאָקומענט — קיין פּראָגרעס-מעסאַדזשעס, קיין ספּינערס.
  טעותים גײן צו stderr ווי `{"error": "...", "detail": "..."}`.
* **סטאַבילע אַרויס-קאָדן.** `0` גוט / `1` ניצן / `2` auth / `3` סערווער /
  `4` ראַטע-לימיט / `5` נישט געפֿונען. אַגענטן קענען צווייגן אויף זיי אָן
  פּאַרסן נאַטירלעך-שפּראַך טעותים.
* **קיין אינטעראַקטיווע פּראָמפּטן אין headless קאָנטעקסטן.** גיב `--yes` (אָדער `-y`)
  צו דעסטרוקטיווע קאָמאַנדן; גיב `--api-key` אָדער שטעל `OMI_API_KEY` כדי צו
  איבערשפּרינגען אינטעראַקטיוון לאָגין.
* **פֿאַרגעבנדיקער ריטרײַ-האַנדל.** `429` און `5xx` ווערן ריטרײַד מיט באַקאָפֿ
  ביז זיי קומען אַרויס.

## Auth (איין מאָל, פֿונעט מענטש)

דער באַניצער כאָפּט אַ dev API שליסל פֿונעם Omi וועב-אַפּ
(`https://app.omi.me` → Developer → API Keys) און אָדער:

```bash
omi auth login                          # אינטעראַקטיווע פּאַסטע; שליסל בלײַבט נישט אין שעל-היסטאָריע
# אָדער
export OMI_API_KEY=omi_dev_...          # עפֿעמערלעך, אידעאַל פֿאַר קאָנטיינערס
```

## די פֿינף זאַכן וואָס אַגענטן טאָן מערסטנס

### 1. לייענען זיכרונות

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. מאַכן אַ זיכרון

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. לייענען שמועסן

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. לייענען עפֿענע אַקציע-אייטעמס

```bash
omi action-item list --json --open
```

### 5. מארקירן אַן אַקציע-אייטעם ווי געטאָן

```bash
omi action-item complete --json a1b2c3d4
```

## לאָקאַלע דעסקטאָפּ API

ווען Omi Desktop ווײַזט זײַן לאָקאַלע API, קענען אַגענטן פֿראַגן די אויפֿדעקונג
היסטאָריע, רעקאַפּס, SQL און אויפֿגאַבן אָן צו ניצן די קלאָוד דעו-API:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# אָדער, פֿאַר עפֿעמערלעכע סעסיעס:
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

פֿאַרענדיקן אָדער אויסמעקן אויפֿגאַבן נאָר ווען דער באַניצער בעט קלאר:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` שרײַבט דעם סקרינשאָט אויפֿן
דיסק און פּרינט נאָך JSON אויף stdout פֿאַר סקריפּטן. דער סקרינשאָט-איי.די. קומט
געוויינטלעך פֿון `local search-screen` אָדער SQL אויף די `screenshots` טאַבעלע.
אויב Desktop גיט צוריק אַ סטרוקטורירטער פֿעלער ווי `screenshot_pending`,
`screenshot_file_missing`, אָדער `screenshot_chunk_corrupted`, דער JSON-מוֹד
היט די `reason`, `hint` און `screenshot_id` פֿעלדער אויף stderr כּדי אַז אַגענטן
קענען פרוואַרן אַן עלטערער איי.די. אָדער מעלדן די פּינטלעכע בלאָקירונג.
וואַלידירן דערפֿאָלגעדיקע רעזולטאַטן מיט `file PATH` ביז איר גיבט זיי צו
וואַזשן-טולז.

## דורכגעארבעט בײַשפּיל: Python אַגענט-שלײַף

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

## האַנדלן מיט ראַטע-לימיטן

זיכרונות: 120/שעה. שמועסן: 25/שעה. באַטש-באַשאַפֿונגען: 15/שעה.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## טיפּן

* ניצן `--profile <name>` אויב דיין אַגענט האַנדלט עטלעכע Omi אַקאַונטס. יעדער
  פּראָפֿיל האָט זײַן אייגענע קרעדענשאַלן און API-באַזע.
* ניצן `--api-base http://localhost:8080` פֿאַר לאָקאַלע באַקענד-טעסטן.
* ניצן `OMI_LOCAL_API_URL` און `OMI_LOCAL_TOKEN` כדי צו איבערשרײַבן די
  פּראָפֿיל-לאָקאַלע דעסקטאָפּ-API אינסטאַלירונגען פֿאַר איין לויף.
* ניצן `--verbose` פֿאַר דיבאַגירן — עס לאָגט `METHOD path → status (Ns)` צו
  stderr אָן אַפֿעקטירן stdout, אַזײַ JSON-מוֹד בלײַבט וואַליד.
* צו פּײַפּן אינהאַלט אין אַ שמועס, ניצן `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
