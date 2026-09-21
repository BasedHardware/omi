# omi-cli pro agentibus

> Enchiridion practicum pro structuris ab exemplaribus linguae grandibus (LLM) actis (Claude Code, Cursor, automata propria).

## Cur CLI sit agentibus idoneum

* **Foedus JSON stabile.** `--json` documentum JSON validum ad stdout emittit atque
  *solum* documentum JSON — sine nuntiis de progressu, sine volubilibus. Errores ad
  stderr mittuntur ut `{"error": "...", "detail": "..."}`.
* **Codices exitus stabiles.** `0` recte / `1` usus / `2` authenticatio / `3` servitor / `4` limes
  frequentiae / `5` non inventum. Agentes secundum hos codices discedere possunt sine
  interpretatione errorum linguae naturalis.
* **Nulla indicia interactiva in contextibus acephalis.** Adde `--yes` (vel `-y`) ad
  mandata deletoria; adde `--api-key` vel constitue `OMI_API_KEY` ad transitum
  coniunctionis interactivae.
* **Mitis iterandi modus.** `429` et `5xx` cum relaxatione temporis iterantur
  antequam emergant.

## Authenticatio (semel, ab homine)

Usor clavem API evolutionis a programmate telaris Omi accipit
(`https://app.omi.me` → Developer → API Keys) et vel:

```bash
omi auth login                          # agglutinatio interactiva; clavis non in historia testae
# vel
export OMI_API_KEY=omi_dev_...          # ephemerum, aptum receptaculis
```

## Quinque actiones quas agentes saepissime perficiunt

### 1. Legere memorias

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Creare memoriam

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Legere colloquia

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Legere pensa aperta

```bash
omi action-item list --json --open
```

### 5. Indicare pensum confectum

```bash
omi action-item complete --json a1b2c3d4
```

## API Tabulae Localis

Cum Omi Desktop suum API locale patefacit, agentes historiam scrinii in ipso
instrumento, compendia, SQL, et pensa interrogare possunt sine usu API nubis:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# vel, pro sessionibus ephemeris:
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

Tantum perfice vel dele pensa cum usor id clare poscit:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` imaginem scrinii in discum
scribit et tamen JSON ad stdout pro scriptis imprimit. ID imaginis plerumque
venit de `local search-screen` vel de interrogatione SQL tabulae `screenshots`. Si Desktop
defectum structuratum reddit qualis est `screenshot_pending`, `screenshot_file_missing`,
vel `screenshot_chunk_corrupted`, modus JSON campos `reason`, `hint`, et
`screenshot_id` in stderr servat ut agentes antiquius ID iterare vel certum
impedimentum nuntiare possint. Valida exitus prosperos per `file PATH` antequam ad
instrumenta visionis transmittas.

## Exemplum practicum: gyrus agentis Pythonis

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Invoca omi CLI in modo JSON, errorem tollens in codicibus non prosperis."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI errores structuratos ad stderr in modo JSON imprimit:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Lege omnia pensa aperta et nota confectum quidquid 30 diebus antiquius est.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Tractatio limitum frequentiae

Memoriae: 120/hora. Colloquia: 25/hora. Creationes aggregatae: 15/hora.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # limes frequentiae perventum est
    err = json.loads(result.stderr)
    # err["detail"] simile est: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Consilia

* Utere `--profile <nomen>` si agens tuus plures rationes Omi administrat. Quodque
  profilum suam tesseram et basim API propriam habet.
* Utere `--api-base http://localhost:8080` pro probatione postica locali.
* Utere `OMI_LOCAL_API_URL` et `OMI_LOCAL_TOKEN` ad superandas configurationes locales
  Desktop API pro uno cursu.
* Utere `--verbose` ad emendandum — annotat `METHOD path → status (Ns)` ad stderr
  sine effectu in stdout, ut modus JSON validus maneat.
* Ad contentum in colloquium canalizandum, utere `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
