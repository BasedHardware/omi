# omi-cli por agentoj

> Praktika gvidilo por LLM-movitaj sistemoj (Claude Code, Cursor, viaj propraj robotoj).

## Kial la CLI estas taŭga por agentoj

* **Stabila JSON-kontrakto.** `--json` elsendas validan JSON-dokumenton al stdout kaj
  *nur* JSON-dokumenton — neniujn progresmesaĝojn, neniujn ŝpinitojn. Eraroj iras al
  stderr kiel `{"error": "...", "detail": "..."}`.
* **Stabilaj elirkodoj.** `0` bone / `1` uzado / `2` aŭtentigo / `3` servilo / `4` rapideca
  limigo / `5` ne trovita. Agentoj povas disbranĉiĝi laŭ ĉi tiuj sen analizi
  naturlingvajn erarojn.
* **Neniuj interagaj instigoj en senkapaj kuntekstoj.** Pasu `--yes` (aŭ `-y`) al
  detruaj komandoj; pasu `--api-key` aŭ agordu `OMI_API_KEY` por preterpasi
  interagan ensaluton.
* **Pardonema reatenta konduto.** `429` kaj `5xx` estas reprovitaj kun eksponenta
  retiriĝo antaŭ ol aperi.

## Aŭtentigo (unufoje, fare de la homo)

La uzanto ricevas programistan API-ŝlosilon de la TTT-aplikaĵo Omi
(`https://app.omi.me` → Developer → API Keys) kaj aŭ:

```bash
omi auth login                          # interaga algluo; ŝlosilo ne en ŝela historio
# aŭ
export OMI_API_KEY=omi_dev_...          # efemera, taŭga por ujoj
```

## La kvin aferoj, kiujn agentoj faras plej ofte

### 1. Legi memorojn

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Krei memoron

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Legi konversaciojn

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Legi malfermitajn agerojn

```bash
omi action-item list --json --open
```

### 5. Marki ageron finita

```bash
omi action-item complete --json a1b2c3d4
```

## Loka Labortabla API

Kiam Omi Desktop malkaŝas sian lokan API, agentoj povas peti suraparatan ekranan
historion, resumojn, SQL, kaj taskojn sen uzi la nuban programistan API:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# aŭ, por efemeraj sesioj:
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

Nur plenumu aŭ forigu taskojn kiam la uzanto klare petas:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` skribas la ekrankopion al
disko kaj ankoraŭ eligas JSON al stdout por skriptoj. La ekrankopia ID kutime
venas de `local search-screen` aŭ SQL super la tabelo `screenshots`. Se Desktop
redonas strukturitan fiaskon kiel ekzemple `screenshot_pending`, `screenshot_file_missing`,
aŭ `screenshot_chunk_corrupted`, JSON-reĝimo konservas la kampojn `reason`, `hint`, kaj
`screenshot_id` en stderr por ke agentoj povu reprovi pli malnovan ID aŭ raporti la
precizan blokilon. Validigu sukcesajn elirojn per `file PATH` antaŭ ol transdoni ilin
al vidilaj iloj.

## Funkcianta ekzemplo: Python-agenta ciklo

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Voki la omi CLI en JSON-reĝimo, levante eraron ĉe nesukcesaj elirkodoj."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # La CLI eligas strukturitajn erarojn al stderr en JSON-reĝimo:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Legi ĉiujn malfermitajn agerojn kaj marki ion ajn pli aĝan ol 30 tagoj finita.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Traktado de rapidecaj limigoj

Memoroj: 120/horo. Konversacioj: 25/horo. Stapla kreado: 15/horo.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rapideca limigo atingita
    err = json.loads(result.stderr)
    # err["detail"] aspektas kiel: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Konsiloj

* Uzu `--profile <nomo>` se via agento administras plurajn Omi-kontojn. Ĉiu
  profilo havas sian propran ensalutinformon kaj API-bazon.
* Uzu `--api-base http://localhost:8080` por loka fona testado.
* Uzu `OMI_LOCAL_API_URL` kaj `OMI_LOCAL_TOKEN` por anstataŭigi profil-lokajn
  agordojn de Desktop API por unu kuro.
* Uzu `--verbose` por sencimigo — ĝi registras `METHOD path → status (Ns)` al stderr
  sen influi stdout, do JSON-reĝimo restas valida.
* Por dukti enhavon en konversacion, uzu `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
