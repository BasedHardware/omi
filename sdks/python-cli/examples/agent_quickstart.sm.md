# omi-cli mo sui

> Taʻiala faʻatinoga mo masini e taʻitaʻia e LLM (Claude Code, Cursor, au lava robots).

## Aisea e fetaui ai le CLI mo sui

* **Konekarate JSON mautu.** E tuʻuina atu e `--json` se pepa JSON aoga i
  stdout — *naʻo se pepa JSON* — leai ni feʻau alualu i luma, leai ni milo.
  E alu mea sese i stderr e pei o `{"error": "...", "detail": "..."}`.
* **Koseti ulufale mautu.** `0` lelei / `1` faʻaaogaina / `2` faʻamaoniga / `3`
  auʻaunaga / `4` faʻatapulaʻaina le saosaoa / `5` leʻi maua. E mafai e sui ona
  filifili i nei koseti e aunoa ma le suʻeina o mea sese i le gagana masani.
* **Leai ni fesili fesoʻotaʻi i siosiomaga headless.** Tuʻuina atu `--yes` (poʻo
  `-y`) i poloaiga faʻaleagaina; tuʻuina atu `--api-key` pe seti `OMI_API_KEY` e
  faʻaseʻe ai le ulufale fesoʻotaʻi.
* **Amio toe taumafai faʻamagalo.** E toe taumafai `429` ma `5xx` ma le solo i
  tua aʻo leʻi faʻaalia.

## Faʻamaoniga (tasi, e le tagata)

E maua e le tagata faʻaoga se ki API dev mai le polokalame uepi Omi
(`https://app.omi.me` → Developer → API Keys) ona filifili lea:

```bash
omi auth login                          # faapipii lima; e le i totonu o le tala faasolopito o le shell le ki
# poʻo
export OMI_API_KEY=omi_dev_...          # le tumau, fetaui mo pusa
```

## Mea e lima e fai soo ai sui

### 1. Faitau manatuaga

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Fausia se manatuaga

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Faitau talanoaga

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Faitau galuega tatala

```bash
omi action-item list --json --open
```

### 5. Faʻaiʻu se galuega

```bash
omi action-item complete --json a1b2c3d4
```

## API Desktop Lotoifale

Pe a faʻaalia e Omi Desktop lana API lotoifale, e mafai e sui ona fesili i le
tala faasolopito o le lau i luga o le masini, faʻamatalaga, SQL, ma galuega e
aunoa ma le faʻaaogaina o le API dev o le ao:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# poʻo, mo sauniga le tumau:
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

Faʻaiʻu pe tape galuega pea pe a fai manino le tagata faʻaoga:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

E tusia e `omi local screenshot SCREENSHOT_ID --output PATH` le ata o le lau i
le tisiki ma lolomi pea le JSON i stdout mo tusitusiga. E masani ona sau le ID
o le ata mai `local search-screen` poʻo SQL i luga o le laulau `screenshots`.
Afai e toe faafoi mai e Desktop se faaletonu faʻatulagaina e pei o
`screenshot_pending`, `screenshot_file_missing`, poʻo `screenshot_chunk_corrupted`,
e tausia e le faiga JSON ia fanua `reason`, `hint`, ma `screenshot_id` i stderr
ina ia mafai ai e sui ona toe taumafai i se ID tuai pe lipoti le faʻalavelave
tonu. Faʻamaonia galuega manuia i `file PATH` ae leʻi tuʻuina atu i meafaigaluega
vaai.

## Faʻataʻitaʻiga hana: taamilosaga sui Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Faʻaoga le CLI omi i le faiga JSON, sii i luga se faaletonu pe a le manuia le koseti ulufale."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # E lolomi e le CLI mea sese faʻatulagaina i stderr i le faiga JSON:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Faitau galuega tatala uma ma faʻailoga soʻo se mea ua silia i le 30 aso ua maeʻa.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Taulimaina o tapulaa saosaoa

Manatuaga: 120/itula. Talanoaga: 25/itula. Fausiaga faʻaputu: 15/itula.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # faʻatapulaʻaina le saosaoa
    err = json.loads(result.stderr)
    # err["detail"] e pei o: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Fautuaga

* Faʻaaoga `--profile <name>` pe a pulea e lau sui ni tala Omi se tele. E tofu
  le tala ma ona lava faʻamaoniga ma lona API base.
* Faʻaaoga `--api-base http://localhost:8080` mo suʻega o le backend lotoifale.
* Faʻaaoga `OMI_LOCAL_API_URL` ma `OMI_LOCAL_TOKEN` e sui ai faatulagaga API
  Desktop o le tala mo se taamilosaga e tasi.
* Faʻaaoga `--verbose` mo le faʻamamā — e tusia `METHOD path → status (Ns)` i stderr
  e aunoa ma le afaina o stdout, ina ia tumau le aoga o le faiga JSON.
* Mo le tuʻuina atu o anotusi i se talanoaga, faʻaaoga `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
