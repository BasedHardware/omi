# omi-cli loogu talagalay agents

> Hagaha wax ku ool ah oo loogu talagalay harness-yada LLM (Claude Code, Cursor, bot-yadaada).

## Sababta CLI uu u yahay mid saaxiib la ah agents-ka

* **Heshiis JSON oo deggan.** `--json` wuxuu stdout u soo saaraa dukumeenti JSON oo
  ansax ah oo keliya — *dukumeenti JSON oo keliya* — ma jiraan fariimo horumar, ma jiraan
  spinners. Khaladaadku waxay tagaan stderr sida `{"error": "...", "detail": "..."}`.
* **Koodhka bixitaanka oo deggan.** `0` wanaagsan / `1` isticmaalid / `2` xaqiijin /
  `3` server / `4` xaddidan xawaaraha / `5` lama helin. Agents-yadu waxay ku kala bixi
  karaan koodhkan iyaga oo aan falanqayn khaladaadka luqadda dabiiciga ah.
* **Ma jiraan prompts is-dhexgal ah oo ku jira xaaladaha headless.** U gudbi `--yes`
  (ama `-y`) amarrada wax burburiya; u gudbi `--api-key` ama deji `OMI_API_KEY` si aad
  uga booddo gelitaanka is-dhexgalka.
* **Hab-dhaqan dib-u-dayasho oo cafis leh.** `429` iyo `5xx` dib ayaa loo dayaa iyada
  oo la raacayo backoff ka hor inta aysan soo muuqan.

## Xaqiijinta (hal mar, qofka)

Isticmaaluhu wuxuu dev API fure ka helaa Omi web app
(`https://app.omi.me` → Developer → API Keys) wuxuuna sameeyaa mid ka mid ah:

```bash
omi auth login                          # dhejis is-dhexgal; furaha kuma jiro taariikhda shell
# ama
export OMI_API_KEY=omi_dev_...          # ku meel gaar, container-ku habboon
```

## Shanta waxyaabood ee agents-ku ugu badan sameeyaan

### 1. Akhri xusuusta

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Samee xusuus

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Akhri wada-hadallada

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Akhri shayada ficilka ee furan

```bash
omi action-item list --json --open
```

### 5. Calaamadee shay ficil inuu dhammaaday

```bash
omi action-item complete --json a1b2c3d4
```

## API-ga Desktop-ka Maxalliga ah

Marka Omi Desktop soo bandhigo API-ga maxalliga ah, agents-yadu waxay waydiin karaan
taariikhda shaashadda qalabka, soo-koobitaannada, SQL, iyo hawlo iyaga oo aan
isticmaalayn cloud dev API:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# ama, fadhiyada ku meel gaarka ah:
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

Kaliya dhammee ama tirtir hawlo marka isticmaaluhu si cad u weydiisto:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` waxay sawirka shaashadda ku qortaa
disk-ka oo weli JSON u daabacdaa stdout-ka scripts-ka. ID-ga sawirka shaashadda inta
badan wuxuu ka yimaadaa `local search-screen` ama SQL ku yaal shaxda `screenshots`.
Haddii Desktop soo celiyo guul-darro qaabaysan sida `screenshot_pending`,
`screenshot_file_missing`, ama `screenshot_chunk_corrupted`, qaabka JSON wuxuu stderr
ku ilaaliyaa `reason`, `hint`, iyo `screenshot_id` si agents-yadu dib ugu dayan karaan
ID hore ama u soo sheegaan xannibaadda saxda ah. Xaqiiji soo-saarka guulaysta
`file PATH` ka hor inta aanad u gudbin qalabka aragtida.

## Tusaale la shaqeeyay: Python agent loop

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """U wac omi CLI qaabka JSON, oo kici khalad marka koodhka bixitaanku guulaysan waayo."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI waxay stderr ku daabacdaa khaladaad qaabaysan qaabka JSON:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Akhri dhammaan shayada ficilka ee furan oo calaamadee wax kasta oo ka weyn 30 maalmood mid dhammaaday.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Maareynta xaddidaadka xawaaraha

Xusuusta: 120/hr. Wada-hadallada: 25/hr. Abuurista koox: 15/hr.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # xaddidan xawaaraha
    err = json.loads(result.stderr)
    # err["detail"] wuxuu u eg yahay: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Talooyin

* Isticmaal `--profile <name>` haddii agent-kaagu maareeyo xisaabo badan oo Omi ah.
  Profile kastaa wuxuu leeyahay aqoonsi u gaar ah iyo API base.
* Isticmaal `--api-base http://localhost:8080` tijaabinta backend-ka maxalliga ah.
* Isticmaal `OMI_LOCAL_API_URL` iyo `OMI_LOCAL_TOKEN` si aad uga gudubto dejinta
  Desktop API ee profile-ka hal mar.
* Isticmaal `--verbose` debugging — wuxuu stderr ku diiwaangeliyaa
  `METHOD path → status (Ns)` isaga oo aan saameyn stdout, markaa qaabka JSON wuu
  ansaxnaadaa.
* Si aad ugu shubto content wada-hadal iyada oo loo marayo pipe, isticmaal `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
