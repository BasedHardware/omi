# omi-cli פֿאַר אַגענטן

> פּראַקטישער וועגווײַזער פֿאַר LLM-געפֿירטע סוויוועס (Claude Code, Cursor, אייערע אייגענע באָטן).

## פֿאַרוואָס די CLI איז פֿרײַנדלעך צו אַגענטן

* **סטאַבילער JSON קאָנטראַקט.** `--json` שיקט אַ גילטיקן JSON דאָקומענט צו stdout און
  *נאָר* אַ JSON דאָקומענט — קיין פּראָגרעס־אָנזאָגן, קיין ספּינערס. ערלערסן גייען צו
  stderr ווי `{"error": "...", "detail": "..."}`.
* **סטאַבילע אַרויסגאַנג־קאָדן.** `0` גוט / `1` באַניץ / `2` אויטאָריזאַציע / `3`
  סערווירער / `4` ראַטע־לימיט / `5` נישט געפֿונען. אַגענטן קענען צווייגן לויט די
  קאָדן אָן צו פּאַרסן ערלערסן אין נאַטירלעכער שפּראַך.
* **קיין אינטעראַקטיווע פּראָמפּטן אין headless קאָנטעקסטן.** גיט `--yes` (אָדער `-y`)
  צו דעסטרוקטיווע קאָמאַנדן; גיט `--api-key` אָדער שטעלט `OMI_API_KEY` צו איבערהיפּן
  אינטעראַקטיוון לאָגין.
* **פֿאַרגעבנדיקן ריטריי־פֿאַרהאַלטן.** `429` און `5xx` ווערן ריטריעט מיט backoff
  איידער זיי דערשיינען.

## אויטאָריזאַציע (איין מאָל, דורך דעם מענטש)

דער באַניצער באַקומט אַ dev API שליסל פֿון דער Omi וועב־אַפּ
(`https://app.omi.me` → Developer → API Keys) און איינע פֿון די פֿאָלגנדיקע:

```bash
omi auth login                          # אינטעראַקטיוו אַריינפֿאַסן; שליסל נישט אין shell היסטאָריע
# אָדער
export OMI_API_KEY=omi_dev_...          # פֿאַרבייגענדיק, פּאַסיק פֿאַר קאָנטיינערס
```

## די פֿינף זאַכן וואָס אַגענטן טוען אַ סאַך

### 1. לייענען זכרונות

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. שאַפֿן אַ זכרון

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. לייענען שמועסן

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. לייענען אָפֿענע אויפֿגאַבן

```bash
omi action-item list --json --open
```

### 5. פֿאַרמאַרקן אַן אויפֿגאַבע ווי דערפֿילט

```bash
omi action-item complete --json a1b2c3d4
```

## לאָקאַלע Desktop API

ווען Omi Desktop שטעלט צו זיין לאָקאַלע API, קענען אַגענטן פֿרעגן די
אויף־דער־אַפּאַראַט בילדשירם־היסטאָריע, רעקאַפּס, SQL און אויפֿגאַבן אָן צו ניצן
דעם וואָלקן dev API:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# אָדער, פֿאַר פֿאַרבייגענדיקע סעסיעס:
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

פֿאַרענדיקט אָדער אויסמעקט אויפֿגאַבן נאָר ווען דער באַניצער בעט קלאָר:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` שרײַבט דעם בילדשירם צו דיסק
און גיט נאָך אַלץ אַרויס JSON צו stdout פֿאַר סקריפּטן. דער בילדשירם־ID קומט
געוויינטלעך פֿון `local search-screen` אָדער SQL איבער דער טאַבעלע
`screenshots`. אויב Desktop גיט אַ סטרוקטורירטן דורכפֿאַל ווי `screenshot_pending`,
`screenshot_file_missing` אָדער `screenshot_chunk_corrupted`, האַלט JSON־מאָדוס ביי
די פֿעלדער `reason`, `hint` און `screenshot_id` אויף stderr, אַזוי אַז אַגענטן קענען
פּרובירן נאָך אַן עלטערן ID אָדער באַריכטן דעם פּינקטלעכן בלאקירער. באַשטעטיקט
דערפֿאָלגרייכע אַרויסגאַבן מיט `file PATH` איידער איר זיי שיקט צו vision־געצייג.

## אַ דורכגעפֿירט ביישפּיל: Python אַגענט־שלייף

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """רופֿט אָן די omi CLI אין JSON־מאָדוס און וואַרפֿט אַרויס בײַ נישט־דערפֿאָלגרייכע אַרויסגאַנג־קאָדן."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # די CLI שיקט סטרוקטורירטע ערלערסן צו stderr אין JSON־מאָדוס:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# לייענט אַלע אָפֿענע אויפֿגאַבן און פֿאַרמאַרקט וואָס עלטער ווי 30 טעג ווי דערפֿילט.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## באַהאַנדלונג פֿון ראַטע־לימיטן

זכרונות: 120/שעה. שמועסן: 25/שעה. באַטש־שאַפֿונגען: 15/שעה.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # ראַטע־לימיט דערגרייכט
    err = json.loads(result.stderr)
    # err["detail"] זעט אויס ווי: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## עצות

* ניצט `--profile <name>` אויב אייער אַגענט פֿירט מערערע Omi־קאנטעס. יעדער
  פּראָפֿיל האָט זײַן אייגענעם באַשטעטיקונג און API base.
* ניצט `--api-base http://localhost:8080` פֿאַר לאָקאַלע backend־פּרואוון.
* ניצט `OMI_LOCAL_API_URL` און `OMI_LOCAL_TOKEN` צו איבערשרייַבן די פּראָפֿיל־לאָקאַלע
  Desktop API־איינשטעלונגען פֿאַר איין לויף.
* ניצט `--verbose` פֿאַר דיבאַגינג — עס פֿירט זשורנאַל פֿון `METHOD path → status (Ns)` צו
  stderr אָן צו באַאיינפֿלוסן stdout, אַזוי JSON־מאָדוס בלײַבט גילטיק.
* צו אַריינשיקן אינהאַלט אין אַ שמועס דורך אַ pipe, ניצט `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
