# omi-cli ke he tau 'ēkeni

> Tohi fakahinohino ke he tau harness 'oku fakafuofuaki 'e LLM (Claude Code, Cursor, ho'o tau poki).

## 'Oku fefe 'a e CLI mo e tau 'ēkeni

* **Fuakavenga JSON tu'umālie.** `--json` 'oku 'omi ha pepa JSON tonu ki he stdout mo
  *pe 'okosi* ha pepa JSON — 'ikai ha fekau fakahoko, 'ikai ha spinner. Ko e tau hala
  'oku 'alu ki he stderr 'o hange `{"error": "...", "detail": "..."}`.
* **Tau fika 'ulungaanga tu'umālie.** `0` lelei / `1` faka'uu / `2` auth / `3` seave /
  `4` fakangatangata vave / `5` 'ikai kitea. 'E malava 'e he tau 'ēkeni ke filifili
  ki ai ta'e he fika'i ha hala 'i he lea fakafonua.
* **'Ikai ha prompt faka'ulungaanga 'i he context headless.** 'Atake `--yes` (pe `-y`)
  ki he tau tu'utu'uni fakamamahi; 'atake `--api-key` pe seti `OMI_API_KEY` ke 'ikai
  ha login faka'ulungaanga.
* **Fakafua fakavalevale retry.** `429` mo `5xx` 'e toe fakatō mo e backoff 'i mu'a
  'i ha'ofua.

## Auth (taha 'a e taimi, 'e he tagata)

'E 'ilo 'e he tagata faka'uu ha ki dev API mei he 'api web Omi
(`https://app.omi.me` → Developer → API Keys) mo pe:

```bash
omi auth login                          # tapaki faka'ulungaanga; 'ikai ke toe 'i he tala'atukuga shell
# pe
export OMI_API_KEY=omi_dev_...          # neongo, lelei ke he tau konitaina
```

## Ko e tau me'a 'e nima 'oku fakahoko lahi 'e he tau 'ēkeni

### 1. Lau 'a e tau manatu

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Fakatupu ha manatu

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Lau 'a e tau talatalanoa

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Lau 'a e tau me'a galue 'oku to'e

```bash
omi action-item list --json --open
```

### 5. Fakahā 'a e me'a galue 'oku mavae

```bash
omi action-item complete --json a1b2c3d4
```

## API fakaloto 'o Desktop

'Oku 'omi 'e Omi Desktop 'ene API fakaloto, 'e malava 'e he tau 'ēkeni ke faka'eke'eke
'i he tala'atukuga 'o e lau 'o e masini, 'a e tau recap, SQL, mo e tau galue 'o 'ikai
faka'uu 'a e API dev 'i he 'ao:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# pe, ki he tau taimi neongo:
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

Faka'osi pe tamate'i pe 'a e tau galue 'i he taimi 'oku fakamālo'ohia 'e he tagata faka'uu:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` 'oku tohi 'a e screenshot ki he
disk mo 'oku 'omi kei 'i he JSON ki he stdout ki he tau tohi. Ko e ID screenshot
'oku fa'a mai mei `local search-screen` pe SQL 'i he tepile `screenshots`. Kapau
'oku 'omai 'e Desktop ha hala fakatekinolōsia hange `screenshot_pending`,
`screenshot_file_missing`, pe `screenshot_chunk_corrupted`, ko e mode JSON 'oku
tauhi 'a e tau konga `reason`, `hint`, mo `screenshot_id` 'i he stderr ke malava
'e he tau 'ēkeni ke toe fakatō ki ha ID tu'oloa pe lipooti 'a e palaka tonu.
Fakamālo'ohia 'a e tau ola lelei 'aki `file PATH` 'i mu'a 'i 'ave ki he tau me'angaue
va'aiga.

## 'Āsite 'oku fakahoko: 'ēkeni loop 'i he Python

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

## Pule'i 'a e tau fakangatangata vave

Manatu: 120/h. Talatalanoa: 25/h. Fakatupu fu'u: 15/h.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Tau fakakaukau

* Faka'uu `--profile <name>` kapau 'oku pule'i 'e ho'o 'ēkeni ha tau 'akauni Omi
  lahi. Ko e profil ta'e 'e 'iai 'ana 'a e credential mo e API base 'a ia.
* Faka'uu `--api-base http://localhost:8080` ki he tau fakamālo'ohi backend fakaloto.
* Faka'uu `OMI_LOCAL_API_URL` mo `OMI_LOCAL_TOKEN` ke fehuhu 'a e seti 'o e API
  fakaloto 'o Desktop 'o e profil ki he taha fakahoko.
* Faka'uu `--verbose` ki he fakamālo'ohi — 'oku tohi `METHOD path → status (Ns)`
  ki he stderr ta'e he fakafuofua ki he stdout, ko e mode JSON 'e 'i ai pe.
* Ke pipe 'a e 'ike ki ha talatalanoa, faka'uu `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
