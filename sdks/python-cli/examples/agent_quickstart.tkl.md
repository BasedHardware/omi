# omi-cli mo nā ʻekene

> Ta'iala galulue mo nā harness e ta'ita'i e LLM (Claude Code, Cursor, kōu poki).

## He aha te CLI e lelei mo nā ʻekene

* **Konekalate JSON mautu.** `--json` e tu'u mai ha pepa JSON tonu ki te stdout ma
  *na'o* ha pepa JSON — 'ai leai ha fe'au fa'asolo, 'ai leai ha spinner. Nā hala e
  alu ki te stderr e pei `{"error": "...", "detail": "..."}`.
* **Nā numela pulea mautu.** `0` lelei / `1` fa'aoga / `2` auth / `3` server /
  `4` fakatau vave / `5` 'ai leai kitea. E mafai e nā ʻekene ke filifili i ia e
  aunoa ma te su'esu'e i hala i te gagana fa'anatula.
* **'Ai leai ha prompt fakatau i context headless.** Tu'u `--yes` (pe `-y`) ki nā
  tu'utu'uga fa'aleaga; tu'u `--api-key` pe seti `OMI_API_KEY` ke solopulea te
  login fakatau.
* **Fakafua fakaleleia retry.** `429` ma `5xx` e toe taumafai ma te backoff a'o
  le'i alia'i.

## Auth (tahi taimi, e te tagata)

E kitea e te tagata fa'aoga se ki dev API mai te app web Omi
(`https://app.omi.me` → Developer → API Keys) ma pe:

```bash
omi auth login                          # fakapipii fakatau; 'ai leai ki i te tala'atukuga shell
# pe
export OMI_API_KEY=omi_dev_...          # neongo, lelei mo nā ipu
```

## Nā mea e lima e fai tele e nā ʻekene

### 1. Faitau nā manatu

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Fakatupu se manatu

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Faitau nā talatalanoa

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Faitau nā mea galulue e tatala

```bash
omi action-item list --json --open
```

### 5. Fakailoga se mea galulue kua mavae

```bash
omi action-item complete --json a1b2c3d4
```

## API fakaloto o Desktop

A fa'aalia e Omi Desktop tōna API fakaloto, e mafai e nā ʻekene ke fesili i te
tala'atukuga o te lau o te masini, nā recap, SQL, ma nā galuega e aunoa ma te
fa'aoga o te API dev i te ao:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# pe, mo nā taimi neongo:
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

Faka'osi pe tape pe nā galuega i te taimi e fakamālo'ohia e te tagata fa'aoga:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` e tusi te screenshot ki te
disk ma e lolomi pea te JSON ki te stdout mo nā tohi. Ko te ID screenshot e masani
ona hau mai `local search-screen` pe SQL i luga o te laulau `screenshots`. Kapau
e toe tu'u mai e Desktop se hala fakatekinolōsia e pei `screenshot_pending`,
`screenshot_file_missing`, pe `screenshot_chunk_corrupted`, ko te mode JSON e
tauhi nā vaega `reason`, `hint`, ma `screenshot_id` i te stderr ke mafai e nā
ʻekene ke toe taumafai ki se ID tuai pe lipoti te palaka tonu. Fakamālo'ohia nā
ola lelei ma `file PATH` a'o le'i 'ave ki nā mea'anga va'aiga.

## Fa'ata'ita'iga kua fai: poro 'ēgenta Python

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

## Pulea nā fakatau vave

Manatu: 120/h. Talatalanoa: 25/h. Fakatupu fu'u: 15/h.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Nā fautuaga

* Fa'aoga `--profile <name>` kapau e pulea e kōu 'ēgenta ha teugatupe Omi lahi.
  Ko e pūlumi taki taha e 'iai 'ana 'a e credential ma te API base 'a ia.
* Fa'aoga `--api-base http://localhost:8080` mo nā su'ega backend fakaloto.
* Fa'aoga `OMI_LOCAL_API_URL` ma `OMI_LOCAL_TOKEN` ke fehuhu nā seti o te API
  fakaloto o Desktop o te pūlumi mo tahi tamoʻe.
* Fa'aoga `--verbose` mo te fakamālo'ohi — e tusi `METHOD path → status (Ns)` ki
  te stderr ta'e he afaina te stdout, ko te mode JSON e 'i ai pea.
* Ke pipe te 'ike ki se talatalanoa, fa'aoga `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
