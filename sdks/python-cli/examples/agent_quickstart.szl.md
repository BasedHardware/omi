# omi-cli dlŏ agyntōw

> Praktyczny guide dlŏ harnessōw sterowanych bez LLM (Claude Code, Cursor, twoje włŏsne boty).

## Dlaczego CLI je kamradzki dlŏ agyntōw

* **Stabilny JSON-kontrakt.** `--json` wydŏwŏ walidny JSON-dokumynt na stdout i
  *ino* JSON-dokumynt — żŏdnych komunikatōw ô postympie, żŏdnych spinnerōw.
  Felerŏ idōm na stderr jako `{"error": "...", "detail": "..."}`.
* **Stabilne kody wyjścio.** `0` dobrze / `1` użycie / `2` auth / `3` serwer /
  `4` limit szybkości / `5` niy znojdyne. Agynci mogōm rozgalōnzić sie na nich
  bez analizowanio felera w naturalnyj gŏdce.
* **Żŏdnych interaktywnych promptōw w headless-kontekstach.** Podŏj `--yes` (abo `-y`)
  do destruktywnych kōmand; podŏj `--api-key` abo ustŏw `OMI_API_KEY`, coby
  pominōńć interaktywne logowanie.
* **Przibocznŏwalne pōnawianie.** `429` i `5xx` sōm pōnawiane z backoffym zŏn
  nŏwiynkōm.

## Auth (rŏz, ôd człowieka)

Używŏcz bierze dev API-klucz ze Omi web-aplikacyje
(`https://app.omi.me` → Developer → API Keys) i abo:

```bash
omi auth login                          # interaktywne wklejanie; klucz niy ôstŏwŏ w historyji shella
# abo
export OMI_API_KEY=omi_dev_...          # efemeryczny, idealny dlŏ kōntynerōw
```

## Piyńć rzeczy, co agynci rŏbiōm nojczyńściyj

### 1. Czytanie pamiyńci

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Tworzynie pamiyńci

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Czytanie gŏdek

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Czytanie ôtwartych punktōw akcyje

```bash
omi action-item list --json --open
```

### 5. Ôznačanie punktu akcyje jako zrobiony

```bash
omi action-item complete --json a1b2c3d4
```

## Lokalne Desktop-API

Kiedy Omi Desktop wystawio swoje lokalne API, agynci mogōm pytŏć ô historyji
ekrana maszyny, rekapitulacyjach, SQL i robotach bez używanio chmurowego
dev-API:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# abo, dlŏ efemerycznych sesyj:
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

Dokōńcz abo wymaż roboty ino jak używŏcz jasno prōsi:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` pisze screenshot na dysk i
dŏlej drukuje JSON na stdout dlŏ skryptōw. ID screenshota zwykle chodzi ze
`local search-screen` abo SQL nad tabelōm `screenshots`. Jak Desktop wrŏco
strukturowany feler jako `screenshot_pending`, `screenshot_file_missing` abo
`screenshot_chunk_corrupted`, tryb JSON zachowuje pola `reason`, `hint` i
`screenshot_id` na stderr, coby agynci mogli prōbować ze starszym ID abo
raportować akuratny blokadōr. Waliduj dobre wyjścia z `file PATH` zŏn nŏwiynkōm
przed przekazaniym do wizyjnych nōczyń.

## Przerōbiony przikłŏd: agyntowa pyntla w Pythonie

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

## Zarzōndzanie limitami szybkości

Pamiyńci: 120/h. Gŏdki: 25/h. Tworzynie w batchach: 15/h.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Rady

* Użyj `--profile <name>`, jak twōj agynt zarzōndzo mockami Omi-kōnt. Kŏżdy
  profil mŏ swoje kredecyje i bazę API.
* Użyj `--api-base http://localhost:8080` dlŏ lokalnych backend-testōw.
* Użyj `OMI_LOCAL_API_URL` i `OMI_LOCAL_TOKEN`, coby nadpisać lokalne
  Desktop-API-ustawianiŏ profila dlŏ jednego wykołanio.
* Użyj `--verbose` dlŏ debugowanio — zapisuje `METHOD path → status (Ns)` na
  stderr bez wpływu na stdout, skiż czego tryb JSON ôstŏwŏ walidny.
* Coby pipeować zawartość do gŏdki, użyj `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
