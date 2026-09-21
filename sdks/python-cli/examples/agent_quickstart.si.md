# නියෝජිතයන් (Agents) සඳහා omi-cli

> LLM මඟින් මෙහෙයවන පද්ධති (Claude Code, Cursor, ඔබේම බොට්ස්) සඳහා ප්‍රායෝගික මාර්ගෝපදේශය.

## CLI නියෝජිතයන් සඳහා හිතකර වීමට හේතු

* **ස්ථාවර JSON ගිවිසුම.** `--json` මඟින් stdout වෙත වලංගු JSON ලේඛනයක් සහ JSON ලේඛනයක්
  *පමණක්* ප්‍රතිදානය කරයි — කිසිදු ප්‍රගති පණිවිඩයක් හෝ කැරකෙන සජීවිකරණයක් නැත. දෝෂ
  `{"error": "...", "detail": "..."}` ලෙස stderr වෙත යවනු ලැබේ.
* **ස්ථාවර පිටවීමේ කේත (exit codes).** `0` සාර්ථකයි / `1` භාවිත දෝෂය / `2` සත්‍යාපන දෝෂය /
  `3` සේවාදායක දෝෂය / `4` සීමාව ඉක්මවීම (rate limited) / `5` හමු නොවීය. ස්වභාවික භාෂා දෝෂ
  විශ්ලේෂණය නොකර නියෝජිතයින්ට මෙම කේත මත කෙලින්ම තීරණ ගත හැකිය.
* **headless සන්දර්භවලදී අන්තර්ක්‍රියාකාරී විමසුම් නොමැත.** වෙනස්කම් සිදු කරන විධානයන්ට
  `--yes` (හෝ `-y`) ලබා දෙන්න; අන්තර්ක්‍රියාකාරී පිවිසුම මඟ හැරීමට `--api-key` ලබා දෙන්න හෝ
  `OMI_API_KEY` පරිසර විචල්‍යය සකසන්න.
* **නම්‍යශීලී නැවත උත්සාහ කිරීමේ හැසිරීම.** `429` සහ `5xx` දෝෂ මතු වීමට පෙර ක්‍රමික ප්‍රමාදයකින්
  (backoff) ස්වයංක්‍රීයව නැවත උත්සාහ කරනු ලැබේ.

## සත්‍යාපනය (මිනිසෙකු විසින් එක් වරක් පමණක් සිදු කරයි)

පරිශීලකයා Omi වෙබ් යෙදුමෙන් සංවර්ධක API යතුර ලබා ගනී
(`https://app.omi.me` → Developer → API Keys) සහ පහත දැක්වෙන එකක් තෝරා ගනී:

```bash
omi auth login                          # අන්තර්ක්‍රියාකාරී ඇලවීම; යතුර ෂෙල් ඉතිහාසයේ නොපවතී
# හෝ
export OMI_API_KEY=omi_dev_...          # තාවකාලික, කන්ටේනර් සඳහා හිතකර
```

## නියෝජිතයන් වැඩිපුරම කරන කරුණු පහ

### 1. මතකයන් කියවීම

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. මතකයක් සෑදීම

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. සංවාද කියවීම

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. විවෘත ක්‍රියාකාරී අයිතම කියවීම

```bash
omi action-item list --json --open
```

### 5. ක්‍රියාකාරී අයිතමයක් අවසන් කළ බව සලකුණු කිරීම

```bash
omi action-item complete --json a1b2c3d4
```

## දේශීය ඩෙස්ක්ටොප් API (Local Desktop API)

Omi Desktop එහි දේශීය API සක්‍රීය කළ විට, ක්ලවුඩ් සංවර්ධක API භාවිතා නොකර උපාංගය තුළ ඇති
තිර ඉතිහාසය, සාරාංශ, SQL දත්ත සහ කාර්යයන් විමසීමට නියෝජිතයින්ට හැකිය:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# හෝ තාවකාලික සැසි සඳහා:
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

පරිශීලකයා පැහැදිලිව ඉල්ලා සිටින විට පමණක් කාර්යයන් සම්පූර්ණ කරන්න හෝ මකන්න:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` මඟින් තිර රුව ඩිස්ක් එකට ලියන අතර
ස්ක්‍රිප්ට් සඳහා stdout වෙත JSON මුද්‍රණය කිරීම දිගටම කරගෙන යයි. තිර රූ හැඳුනුම්පත සාමාන්‍යයෙන්
`local search-screen` හෝ `screenshots` වගුව මත SQL විමසුමකින් ලබා ගනී. Desktop විසින්
`screenshot_pending`, `screenshot_file_missing` හෝ `screenshot_chunk_corrupted` වැනි
ව්‍යුහාත්මක දෝෂයක් ආපසු ලබා දෙන්නේ නම්, JSON මාදිලිය මඟින් stderr හි `reason`, `hint` සහ
`screenshot_id` ක්ෂේත්‍ර රඳවා තබා ගන්නා බැවින් නියෝජිතයින්ට පැරණි ID එකක් සමඟ නැවත උත්සාහ කිරීමට
හෝ නිශ්චිත බාධාව වාර්තා කිරීමට හැකිය. දෘශ්‍ය මෙවලම් වෙත යැවීමට පෙර සාර්ථක ප්‍රතිදානයන් `file PATH` මඟින් වලංගු කරන්න.

## ප්‍රායෝගික උදාහරණය: Python නියෝජිත චක්‍රය

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """සාර්ථක නොවන පිටවීමේ කේතයන්හි දෝෂ මතු කරමින්, JSON ප්‍රකාරයෙන් omi CLI අමතයි."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI JSON ප්‍රකාරයේදී stderr වෙත ව්‍යුහාත්මක දෝෂ නිකුත් කරයි:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# සියලුම විවෘත ක්‍රියාකාරී අයිතම කියවා දින 30කට වඩා පැරණි ඕනෑම දෙයක් සම්පූර්ණ කළ බව සලකුණු කරන්න.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## සීමාවන් කළමනාකරණය (Rate Limits)

මතකයන්: 120/පැයට. සංවාද: 25/පැයට. කාණ්ඩ සෑදීම්: 15/පැයට.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # සීමාව ඉක්මවා ඇත
    err = json.loads(result.stderr)
    # err["detail"] මෙසේ පෙනේ: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## උපදෙස්

* ඔබේ නියෝජිතයා Omi ගිණුම් කිහිපයක් හසුරුවන්නේ නම් `--profile <name>` භාවිතා කරන්න.
  සෑම පැතිකඩකටම තමන්ගේම අක්තපත්‍ර සහ API පදනමක් ඇත.
* දේශීය පසුබිම් පරීක්ෂාව සඳහා `--api-base http://localhost:8080` භාවිතා කරන්න.
* එක් ධාවනයක් සඳහා පැතිකඩෙහි දේශීය ඩෙස්ක්ටොප් API සැකසීම් අභිබවා යාමට `OMI_LOCAL_API_URL`
  සහ `OMI_LOCAL_TOKEN` භාවිතා කරන්න.
* දෝෂහරණය සඳහා `--verbose` භාවිතා කරන්න — එය stdout වලට බලපෑමක් නොකර stderr වෙත
  `METHOD path → status (Ns)` සටහන් කරයි, එබැවින් JSON ප්‍රකාරය වලංගුව පවතී.
* සංවාදයකට අන්තර්ගතය යොමු කිරීම සඳහා `--text -` භාවිතා කරන්න:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
