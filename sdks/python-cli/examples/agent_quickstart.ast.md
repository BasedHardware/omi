# omi-cli pa axentes

> Guía práctica pa arneses empobinaos por LLM (Claude Code, Cursor, los tos propios bots).

## Por qué la CLI ye amigable pa los axentes

* **Contratu JSON estable.** `--json` emite un documentu JSON válidu a stdout y
  *namás* un documentu JSON — nin mensaxes de progresu, nin spinners. Los
  errores van a stderr como `{"error": "...", "detail": "..."}`.
* **Códigos de salida estables.** `0` bien / `1` usu / `2` autenticación / `3`
  sirvidor / `4` llende de tasa / `5` non atopáu. Los axentes pueden ramificar
  sobre estos códigos ensin analizar errores en llinguaxe natural.
* **Ensin entraes interactives en contestos headless.** Pasa `--yes` (o `-y`) a
  los comandos destructivos; pasa `--api-key` o configura `OMI_API_KEY` pa
  saltar el login interactivu.
* **Comportamientu de reintentu tolerante.** `429` y `5xx` se reintenten con
  retrocesu enantes de manifestase.

## Autenticación (una vegada, pel humanu)

L'usuariu consigue una clave API dev dende l'aplicación web d'Omi
(`https://app.omi.me` → Developer → API Keys) y dempués:

```bash
omi auth login                          # pegáu interactivu; la clave nun queda nel historial del shell
# o
export OMI_API_KEY=omi_dev_...          # efímeru, afayadizu pa contenedores
```

## Les cinco coses que los axentes faen más de cutiu

### 1. Lleer memories

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Crear una memoria

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Lleer conversaciones

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Lleer elementos d'aición abiertos

```bash
omi action-item list --json --open
```

### 5. Marcar un elementu d'aición como fechu

```bash
omi action-item complete --json a1b2c3d4
```

## API Local del Escritoriu

Cuando Omi Desktop espón la so API local, los axentes pueden consultar
l'historial de pantalla nel preséu, resúmenes, SQL y xeres ensin usar la API
dev de la nube:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# o, pa sesiones efímeres:
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

Solo completa o desanicia xeres cuando l'usuariu lo pida claramente:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` escribe la captura de
pantalla al discu y sigue imprentando JSON a stdout pa los scripts. El ID de la
captura suel venir de `local search-screen` o de SQL sobre la tabla
`screenshots`. Si Desktop devuelve un fallu estructuráu como
`screenshot_pending`, `screenshot_file_missing` o `screenshot_chunk_corrupted`,
el mou JSON caltién los campos `reason`, `hint` y `screenshot_id` en stderr pa
que los axentes puedan reintentar con un ID más antiguu o informar del bloquéu
exactu. Valida les salíes exitoses con `file PATH` enantes de pasales a
ferramientes de visión.

## Exemplo completu: bucle d'axente en Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Invoca la CLI omi en mou JSON, llevantando esceiciones en códigos de salida non esitosos."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # La CLI imprime errores estructuraos a stderr en mou JSON:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Llee tolos elementos d'aición abiertos y marca como completos los de más de 30 díes.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Xestión de llendes de tasa

Memories: 120/hora. Conversaciones: 25/hora. Creaciones por llotes: 15/hora.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # llende de tasa
    err = json.loads(result.stderr)
    # err["detail"] ye daqué como: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Consejos

* Usa `--profile <name>` si el to axente xestiona delles cuentes d'Omi. Cada
  perfil tien la so propia credencial y base d'API.
* Usa `--api-base http://localhost:8080` pa probar el backend local.
* Usa `OMI_LOCAL_API_URL` y `OMI_LOCAL_TOKEN` pa sobrescribir la configuración
  de l'API Local del Escritoriu d'un perfil mientres una execución.
* Usa `--verbose` pa depurar — rexistra `METHOD path → status (Ns)` a stderr
  ensin afectar a stdout, asina que'l mou JSON sigue siendo válidu.
* Pa enriar conteníu a una conversación, usa `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
