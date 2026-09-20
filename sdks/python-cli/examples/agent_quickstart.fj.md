# omi-cli ni na agents

> Veivakasauraraki vakavuna ni LLM (Claude Code, Cursor, se na nomu bola vakataki iko).

## Na cava e gadrevi kina na CLI vei ira na agents

* **Na iyauyaloyalo ni JSON e tu vakaudolu.** Na `--json` e cavuta e dua na itukutuku
  dodonu ni JSON ki na stdout ka *gauna walega* e dua na itukutuku ni JSON — sega ni
  tiko na itukutuku ni toso, sega ni spinner. Na cala e lako ki na stderr me vaka
  `{"error": "...", "detail": "..."}`.
* **Na ka e lako mai e tu vakaudolu.** `0` vinaka / `1` vakayagataki / `2` itokotoko
  ni curuvaka / `3` server / `4` vakatabatabataka na vakatakece / `5` sega ni kunea.
  Era na rawa ni digitaka na agents e na veika oqo ena sega ni raica na cala ni vosa
  vakavuravura.
* **Sega ni tiko na kerekere ena veigauna headless.** Solia na `--yes` (se `-y`) ki na
  veivakavunau vakacacani; solia na `--api-key` se biuta na `OMI_API_KEY` me vakairawai
  na curuvaka.
* **Na kena tovolei tale e tu vakavinaka.** Na `429` kei na `5xx` e tovolei tale ena
  backoff ni bera ni rairavi.

## Na curuvaka (e dua na gauna, vei ira na tamata)

Ena kunea na tamata e dua na kī ni API ni ivakarau mai na app ni web ni Omi
(`https://app.omi.me` → Developer → API Keys) ka qai:

```bash
omi auth login                          # curuvaka vakataki iko; na kī e sega ni tiko ena itukutuku ni shell
# se
export OMI_API_KEY=omi_dev_...          # vakaoti-vakalailai, vinaka vei ira na container
```

## Na lima na ka era dau cakava na agents

### 1. Wilika na memorī

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Cakava e dua na memorī

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Wilika na veitaratara

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Wilika na itavi e sa dolava

```bash
omi action-item list --json --open
```

### 5. Vakatakila e dua na itavi me sa oti

```bash
omi action-item complete --json a1b2c3d4
```

## Local Desktop API

Ni dau yalataka na Omi Desktop na nona API ena vanua, era na rawa ni kerea na agents
na itukutuku ni screen e na tavi, na itukutuku lala, SQL, kei na itavi ena sega ni
vakayagataka na cloud dev API:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# se, me baleta na gauna vakaoti-vakalailai:
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

Me oti se vakarusai na itavi ga ni sa kerea vakamatata na tamata:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` e vola na screenshot ki na disiki ka
se tu tikoga na kena cavuti ni JSON ki na stdout me baleta na scripts. Na ID ni
screenshot e dau lako mai na `local search-screen` se na SQL ena teveli ni `screenshots`.
Kevaka e kidavaka na Desktop e dua na cala vakavakarau me vaka `screenshot_pending`,
`screenshot_file_missing`, se `screenshot_chunk_corrupted`, na mode ni JSON e taura
tu na iwasewase `reason`, `hint`, kei na `screenshot_id` ena stderr me rawa ni tovolei
tale na agents ena ID makawa se raica na ka e vakarerevaki. Vakatotolo na itukutuku
vinaka o kunea ena `file PATH` ni bera ni solia ki na veika ni rai.

## Ivakaraitaki ni cakacaka: na loop ni agent ena Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Kaciva na CLI ni omi ena mode ni JSON, vakavodoka e dua na exception ena kena sega ni vinaka na lako mai."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # Na CLI e vakarautaka na cala ki na stderr ena mode ni JSON:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Wilika na itavi kece e sa dolava ka vakatakila na kena sa makawa mai na 30 siga oti.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Na kena veikauyaki na vakatabatabataki ni vakatakece

Memorī: 120/e dua na auwa. Veitaratara: 25/e dua na auwa. Cakava e lewe vuqa: 15/e dua na auwa.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # vakatabatabataka na vakatakece
    err = json.loads(result.stderr)
    # err["detail"] e vaka: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Vosa vakatagi

* Vakayagataka na `--profile <name>` kevaka na nomu agent e vakayagataka e levu na
  account ni Omi. Na profile kece e tu vua na nona veivuke kei na kena vanua ni API.
* Vakayagataka na `--api-base http://localhost:8080` me baleta na veiwainimatekivu ni
  backend ena vanua.
* Vakayagataka na `OMI_LOCAL_API_URL` kei na `OMI_LOCAL_TOKEN` mo veisau na ituvatuva
  ni Desktop API ni profile ena dua na gauna walega.
* Vakayagataka na `--verbose` mei keba — e volai `METHOD path → status (Ns)` ki na
  stderr ena sega ni veisau na stdout, o koya na mode ni JSON e tu dodonu tikoga.
* Mo vakatali na ka ena e dua na veitaratara, vakayagataka na `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```