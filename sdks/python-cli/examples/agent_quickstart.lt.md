# omi-cli agentams

> Praktinis vadovas LLM valdomiems harnessams (Claude Code, Cursor, jūsų paties botams).

## Kodėl CLI yra agentams draugiškas

* **Stabilus JSON kontraktas.** `--json` į stdout išmeta galiojantį JSON dokumentą ir
  *tik* JSON dokumentą — jokių progreso pranešimų, jokių spinnerių. Klaidos eina
  į stderr kaip `{"error": "...", "detail": "..."}`.
* **Stabilūs išėjimo kodai.** `0` gerai / `1` naudojimas / `2` auth / `3` serveris /
  `4` greičio limitas / `5` nerastas. Agentai gali šakotis ties jais be natūralios
  kalbos klaidų analizavimo.
* **Jokių interaktyvių raginimų headless kontekstuose.** Perduokite `--yes` (arba `-y`)
  destruktyvioms komandoms; perduokite `--api-key` arba nustatykite `OMI_API_KEY`,
  kad praleistumėte interaktyvų prisijungimą.
* **Atlaidus pakartojimo elgsena.** `429` ir `5xx` kartojami su backoff prieš
  iškylant.

## Auth (vieną kartą, žmogaus)

Vartotojas gauna dev API raktą iš Omi žiniatinklio programos
(`https://app.omi.me` → Developer → API Keys) ir arba:

```bash
omi auth login                          # interaktyvus įklijavimas; raktas nelieka shell istorijoje
# arba
export OMI_API_KEY=omi_dev_...          # trumpalaikis, tinkamas konteineriams
```

## Penki dalykai, kuriuos agentai daro dažniausiai

### 1. Skaityti atmintis

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Sukurti atmintį

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Skaityti pokalbius

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Skaityti atvirus veiksmo punktus

```bash
omi action-item list --json --open
```

### 5. Pažymėti veiksmo punktą kaip atliktą

```bash
omi action-item complete --json a1b2c3d4
```

## Vietinė Desktop API

Kai Omi Desktop atveria savo vietinę API, agentai gali teirautis įrenginio
ekrano istorijos, santraukų, SQL ir užduočių nenaudodami debesijos dev API:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# arba, trumpalaikėms sesijoms:
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

Baigti arba ištrinti užduotis tik kai vartotojas aiškiai prašo:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` įrašo ekrano kopiją į diską
ir vis dar spausdina JSON į stdout scenarijams. Ekrano kopijos ID paprastai
ateina iš `local search-screen` arba SQL iš `screenshots` lentelės. Jei Desktop
grąžina struktūrinę klaidą, pvz., `screenshot_pending`, `screenshot_file_missing`
arba `screenshot_chunk_corrupted`, JSON režimas išsaugo `reason`, `hint` ir
`screenshot_id` laukus stderr, kad agentai galėtų pakartoti su senesniu ID arba
pranešti tikslią kliūtį. Patikrinkite sėkmingus išvestis su `file PATH` prieš
perduodami vizijos įrankiams.

## Išdirbtas pavyzdys: Python agento ciklas

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

## Greičio limitų valdymas

Atmintys: 120/val. Pokalbiai: 25/val. Paketiniai kūrimai: 15/val.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Patarimai

* Naudokite `--profile <name>`, jei jūsų agentas valdo kelias Omi paskyras. Kiekvienas
  profilis turi savo kredencialus ir API bazę.
* Naudokite `--api-base http://localhost:8080` vietiniams backend testams.
* Naudokite `OMI_LOCAL_API_URL` ir `OMI_LOCAL_TOKEN`, kad pakeistumėte profilio
  vietinės Desktop API nustatymus vienam vykdymui.
* Naudokite `--verbose` derinimui — jis registruoja `METHOD path → status (Ns)`
  į stderr nepaveikdamas stdout, todėl JSON režimas lieka galiojantis.
* Norėdami nukreipti turinį į pokalbį, naudokite `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
