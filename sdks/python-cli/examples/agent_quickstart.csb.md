# omi-cli dlô agentów

> Prakticzny gida dlô harnessów sterowónych przez LLM (Claude Code, Cursor, twòj włosne boty).

## Dlaczô CLI je kamrat dlô agentów

* **Stabilny JSON-kontrakt.** `--json` wydôwô wôlëżny JSON-dokumënt na stdout i
  *leno* JSON-dokumënt — żôdnych wiadła ò postãpie, żôdnych spinnerów.
  Felerë idą na stderr jak `{"error": "...", "detail": "..."}`.
* **Stabilne kòdë wëjscô.** `0` dobrze / `1` brëk / `2` auth / `3` serwer /
  `4` limit szëbkòscë / `5` nié znojdne. Agencë mògą rozgalãzacë sã na nich bez
  analizowaniô felera w nâturalny jãzëk.
* **Żôdnych interaktywnych promptów w headless-kontekstach.** Podôj `--yes` (abò `-y`)
  destruktywnym kòmandãm; podôj `--api-key` abò nôstôwi `OMI_API_KEY`, żebë
  pominąc interaktywné logowanié.
* **Przëbaczowające pònôwianié.** `429` i `5xx` są pònôwioné z backoffãm zanim
  wëjdną.

## Auth (rôz, òd człowiéka)

Brëkôcz bierze dev API-klucz z Omi web-aplikacëji
(`https://app.omi.me` → Developer → API Keys) i abò:

```bash
omi auth login                          # interaktywné wklejanié; klucz nié òstôwô w historëji szela
# abò
export OMI_API_KEY=omi_dev_...          # efemericzné, idéalny dlô kòntënerów
```

## Piãc rzeczë, co agencë robë nôbarżi

### 1. Czëtanie pamiãcy

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Twòrzenié pamiãcy

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Czëtanie rozmòwów

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Czëtanie òtkrëtych punktów akcëje

```bash
omi action-item list --json --open
```

### 5. Ôznôczanié punktu akcëje jak zrëchtowôny

```bash
omi action-item complete --json a1b2c3d4
```

## Lokalné Desktop-API

Czedë Omi Desktop wëstôwiô swòj lokalny API, agencë mògą pytac ò historëji
ekrana maszëny, rekapitulacëjach, SQL i robotach bez brëkòwaniô chmùrowégò
dev-API:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# abò, dlô efemericznëch sesëjów:
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

Dokôñcz abò wëmaż robotë leno czedë brëkôcz jasno prósë:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` pisze screenshot na dësk i
dali drëkùje JSON na stdout dlô skryptów. ID screenshota zwikle chòdzi z
`local search-screen` abò SQL nad tabelą `screenshots`. Jak Desktop wroco
strukturowany feler jak `screenshot_pending`, `screenshot_file_missing` abò
`screenshot_chunk_corrupted`, trëb JSON zachowùje pòla `reason`, `hint` i
`screenshot_id` na stderr, żebë agencë mògli pròbòwac ze starszim ID abò
rapòrtowac akluratny blokadôr. Waliduj dobré wëjscô z `file PATH` przed
przekazanim do wizyjnych nôczënków.

## Przerobiony przikłôd: agëntowô pãtla w Pythonie

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

## Zarzãdzanié limitama szëbkòscë

Pamiãcë: 120/h. Rozmòwë: 25/h. Twòrzenié w batchach: 15/h.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Radë

* Brëkùj `--profile <name>`, jak twòj agënt zarzãdzô wicy Omi-kònt. Kòżdy
  profil mô swòje kredencëje i bazã API.
* Brëkùj `--api-base http://localhost:8080` dlô lokalnëch backend-testów.
* Brëkùj `OMI_LOCAL_API_URL` i `OMI_LOCAL_TOKEN`, żebë nadpisac lokalné
  Desktop-API-ùstawiéńa profila dlô jednegò wëkònaniô.
* Brëkùj `--verbose` dlô debugòwaniô — zapisùje `METHOD path → status (Ns)` na
  stderr bez wpłiwù na stdout, skãdë trëb JSON òstôwô wôlëżny.
* Żebë pipeòwac zawartość do rozmòwë, brëkùj `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
