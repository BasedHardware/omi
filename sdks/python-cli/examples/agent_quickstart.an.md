# omi-cli ta agents

> Guía practica ta sistemas empentaus por LLM (Claude Code, Cursor, os tuyos propios bots).

## Per qué o CLI ye amigo d'os agents

* **Contrato JSON estable.** `--json` mincha un documento JSON valido a stdout y
  *nomás* un documento JSON — sin mensaches de progreso, sin spinners. Os errors van
  ta stderr como `{"error": "...", "detail": "..."}`.
* **Codigos de salida estables.** `0` ok / `1` uso / `2` autenticación /
  `3` servidor / `4` limitación de ritmo / `5` no trobau. Os agents pueden fer una
  rama con ellos sin analisar errors en luengache natural.
* **No bi ha prompts interactivos en contextos headless.** Pasa `--yes` (u `-y`) ta
  comandos destructivos; pasa `--api-key` u define `OMI_API_KEY` ta saltar-se o login
  interactivo.
* **Comportamiento de reintento tolerant.** `429` y `5xx` se tornan a intentar con
  backoff antis de surtir.

## Autenticación (una vegada, per lo humán)

L'usuario recibe una clau API de desembolique de l'aplicación web d'Omi
(`https://app.omi.me` → Developer → API Keys) y dimpués:

```bash
omi auth login                          # endicar interactivo; la clau no ye en l'historial d'a shell
# u
export OMI_API_KEY=omi_dev_...          # efimera, bien ta contenedors
```

## As cinco cosas que os agents fan más a cutío

### 1. Leyer memorias

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Crear una memoria

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Leyer conversas

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Leyer os items d'acción ubiertos

```bash
omi action-item list --json --open
```

### 5. Marcar un item d'acción como rematau

```bash
omi action-item complete --json a1b2c3d4
```

## Local Desktop API

Quan Omi Desktop exposa lo suyo API local, os agents pueden consultar l'historial de
pantalla en o dispositivo, resúmens, SQL y treballos sin usar lo cloud dev API:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# u, ta sessions efimeras:
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

Remata u esborra treballos nomás quan l'usuario lo demande explicitament:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` escribe a captura de pantalla en o
disco y contina minchando JSON a stdout ta scripts. L'ID d'a captura gosa venir de
`local search-screen` u d'un SQL sobre la tabla `screenshots`. Si Desktop torna una
falla estructurada como `screenshot_pending`, `screenshot_file_missing` u
`screenshot_chunk_corrupted`, lo modo JSON conserva os campos `reason`, `hint` y
`screenshot_id` en stderr ta que os agents puedan tornar a intentar con un ID más
viello u informar d'o bloqueo exacto. Valida as salidas exitosas con `file PATH` antis
de pasar-las a ferramientas de visión.

## Eixemplo treballau: bucle d'agent en Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Invoca lo CLI omi en modo JSON, lanzando una excepción en codigos de salida no exitosos."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # Lo CLI mincha errors estructurados a stderr en modo JSON:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Leye toz os items d'acción ubiertos y marca como remataus los que tiengan més de 30 días.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Manechar limitacions de ritmo

Memorias: 120/h. Conversas: 25/h. Creacions por lot: 15/h.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # limitación de ritmo
    err = json.loads(result.stderr)
    # err["detail"] se pareixe a: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Consellos

* Fai servir `--profile <name>` si lo tuyo agent chestiona varios cuentas d'Omi. Cada
  perfil tien as suyas propias credencials y base d'API.
* Fai servir `--api-base http://localhost:8080` ta probar lo backend local.
* Fai servir `OMI_LOCAL_API_URL` y `OMI_LOCAL_TOKEN` ta sobreescribir as configuracions
  d'o Desktop API por perfil en una sola execución.
* Fai servir `--verbose` ta depurar — rechistra `METHOD path → status (Ns)` en stderr
  sin afeutar a stdout, asinas lo modo JSON continúa siendo valido.
* Ta encadenar conteniu enta una conversa, fai servir `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```