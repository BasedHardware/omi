# omi-cli pa agentenan

> Guia pr\u00e1tico pa sistemanan dirigi pa LLM (Claude Code, Cursor, bo propio botnan).

## Dikonan e CLI ta amigu di agentenan

* **Contrato JSON stabiel.** `--json` ta emiti un documento JSON balido na stdout i
  *solo* un documento JSON — sin mensahenan di progreso, sin spinner. Eror ta bai na
  stderr komo `{"error": "...", "detail": "..."}`.
* **K\u00f3digo di salida stabiel.** `0` ok / `1` uso / `2` autentikashon /
  `3` server / `4` limitashon di ritmo / `5` no ha\u00f1a. Agentenan por brinca riba esaki
  sin parse\u00e1 eror den idioma natural.
* **No tin prompt interaktivo den contextonan headless.** Pasa `--yes` (\u00f2f `-y`) na
  komandonan destruktivo; pasa `--api-key` \u00f2f pone `OMI_API_KEY` pa salta login
  interaktivo.
* **Komportashon di reintento tolerante.** `429` i `5xx` ta w\u00f2rdu intent\u00e1 di nobo
  ku backoff prom\u00e9 ku nan sali.

## Autentikashon (un biaha, dor di e hende)

E usuario ta ha\u00f1a un yabi di API di desaroyo for di e app web di Omi
(`https://app.omi.me` \u2192 Developer \u2192 API Keys) i despues:

```bash
omi auth login                          # pega interaktivo; e yabi no ta den e historia di shell
# \u00f2f
export OMI_API_KEY=omi_dev_...          # ef\u00edmero, bon pa container
```

## E sinku kos ku agentenan ta hasi mas

### 1. Lesa memorianan

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Krea un memoria

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Lesa konversashonnan

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Lesa akshonnan habri

```bash
omi action-item list --json --open
```

### 5. Marca un akshon komo termin\u00e1

```bash
omi action-item complete --json a1b2c3d4
```

## Local Desktop API

Ora e Omi Desktop ta ekspon\u00e9 su API lokal, agentenan por investig\u00e1 e historia di
pantaya riba e aparato, res\u00famen, SQL i tareanan sin usa e cloud dev API:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# \u00f2f, pa sesionnan ef\u00edmero:
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

Termin\u00e1 of bisa tareanan solamente ora e usuario pidi esei claramente:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` ta skirbi e screenshot riba e
disko i ainda ta imprimi JSON na stdout pa scripts. E ID di screenshot normalmente ta
bini di `local search-screen` of di un SQL riba e tabla `screenshots`. Si Desktop ta
debolbe un fayo struktura komo `screenshot_pending`, `screenshot_file_missing` of
`screenshot_chunk_corrupted`, e modo JSON ta manten\u00e9 e camnanan `reason`, `hint` i
`screenshot_id` na stderr pa agentenan por purba di nobo ku un ID mas bieu of inform\u00e1
e obstakulo eksakto. Valid\u00e1 resultadonan eksitoso ku `file PATH` prom\u00e9 di pas\u00e1 nan
na hermentnan di vishon.

## Ehempel trah\u00e1: loop di agente na Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Invoc\u00e1 e CLI di omi na modo JSON, tirando un excepcion riba k\u00f3digo di salida no eksitoso."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # E CLI ta imprimi erornan struktura na stderr na modo JSON:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Lesa tur akshonnan habri i marca tur esunnan ku ta mas bieu ku 30 dia komo termin\u00e1.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Maneho di limitashon di ritmo

Memorianan: 120/ora. Konversashonnan: 25/ora. Krea na lote: 15/ora.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # limitashon di ritmo
    err = json.loads(result.stderr)
    # err["detail"] ta parse\u00e1 manera: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Tips

* Usa `--profile <name>` si bo agente ta maneha varios account di Omi. Cada profile
  tin su mesun credencial i base di API.
* Usa `--api-base http://localhost:8080` pa prob\u00e1 e backend lokal.
* Usa `OMI_LOCAL_API_URL` i `OMI_LOCAL_TOKEN` pa overrul\u00e9 e konfiguracionnan di
  Desktop API di e profile pa un solo ehekushon.
* Usa `--verbose` pa debug — e ta registr\u00e9 `METHOD path \u2192 status (Ns)` na stderr
  sin afect\u00e1 stdout, asina e modo JSON keda balido.
* Pa p\u00e1s kontenido aden un konversashon, usa `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```