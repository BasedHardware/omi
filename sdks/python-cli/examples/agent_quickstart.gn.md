# omi-cli umi agénte g̃uarã

> Tembiporu ñe'ẽ LLM ogueraháva harness rehegua (Claude Code, Cursor, nde botete'.

## Mba'éicha pe CLI oĩ porã umi agénte g̃uarã

* **JSON ñe'ẽjuajúre oĩ porãva.** `--json` omoherakuã peteĩ JSON kuatiaite oĩ porãva stdout-pe ha
  *ñañónte* JSON kuatiaite — ndaipóri ñe'ẽmondo oĩporãvévo, ndaipóri spinner. Umi jejavy
  oho stderr-pe `{"error": "...", "detail": "..."}` ramo.
* **Ñesẽ código oĩ porãva.** `0` porã / `1` jeporu / `2` auth / `3` servidor /
  `4` jekuaa jeykeko / `5` ndojejuhúi. Umi agénte ikatu ojepohýi ko'ãme'ẽ ndojejuhúiva'ekue
  ñe'ẽtee jejavy.
* **Ndaipóri prompt interactivo headless rehegua.** Eme'ẽ `--yes` (térã `-y`) umi
  ñe'ẽmondo ombohasáva; eme'ẽ `--api-key` térã embohekóe `OMI_API_KEY` ani eike
  ñe'ẽmondo interactivo.
* **Retry oguenohẽvéva.** `429` ha `5xx` oñeháũjey backoff ndive oje'ẽ mboyve.

## Auth (peteĩ jave, ava rupive)

Puruhára ojuhu dev API key Omi web app-pe
(`https://app.omi.me` → Developer → API Keys) ha térã:

```bash
omi auth login                          # pegar interactivo; key ndopái shell historial-pe
# térã
export OMI_API_KEY=omi_dev_...          # ñañónte, iporãvéva contenedor g̃uarã
```

## Po po'õ umi agénte ojapo hetavéva

### 1. Emoñe'ẽ umi mandu'a

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Ejapo peteĩ mandu'a

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Emoñe'ẽ umi ñe'ẽjuaju

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Emoñe'ẽ umi ñe'ẽmondo ijurujáva

```bash
omi action-item list --json --open
```

### 5. Emoĩ paho peteĩ ñe'ẽmondo oĩporãmóvaramo

```bash
omi action-item complete --json a1b2c3d4
```

## API local Desktop pegua

Omi Desktop ohechauka i API local jave, umi agénte ikatu oporandu pe dispositivo
pantalla historial, recap, SQL, ha tembi'apo oiporu'ỹre pe API dev nube pegua:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# térã, sesiones ñañóntevépe:
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

Emoĩ paho térã embogue umi tembi'apo puruhára ojejerure añetegua:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` ohai pe screenshot disco-pe ha
ojeimprime JSON stdout-pe script g̃uarã. Pe screenshot ID ou `local search-screen`
térã SQL `screenshots` tabla rehegua. Desktop ombojevýrõ jejavy estructurado
`screenshot_pending`, `screenshot_file_missing`, térã `screenshot_chunk_corrupted`
ramo, pe modo JSON oñongatu pe `reason`, `hint`, ha `screenshot_id` campo stderr-pe
ani umi agénte ojeháũjey peteĩ ID tuichavéva térã oinformar bloqueo ha'etéva.
Ehecha emoĩporã resultado `file PATH` ndive ombouva'erã vision herramienta g̃uarã.

## Ejemplo ojejapóva: loop de agente Python-pe

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

## Eñangareko límite jeykeko rehegua

Mandu'a: 120/h. Ñe'ẽjuaju: 25/h. Creación lote-pe: 15/h.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Consejo

* Eiporu `--profile <name>` nde agénte oñangareko heta cuenta Omi rehegua.
  Peteĩteĩ perfil oguereko i credencial ha i API base.
* Eiporu `--api-base http://localhost:8080` test backend local g̃uarã.
* Eiporu `OMI_LOCAL_API_URL` ha `OMI_LOCAL_TOKEN` ani emoambue perfil local
  Desktop API ñemboheko peteĩ ejecución g̃uarã.
* Eiporu `--verbose` debug g̃uarã — ohai `METHOD path → status (Ns)` stderr-pe
  stdout-pe oafectar'ỹre, péro modo JSON oikóvo.
* Eiporu `--text -` ani epipe contenido peteĩ ñe'ẽjuaju-pe:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
