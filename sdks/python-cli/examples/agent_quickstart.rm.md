# omi-cli per agens

> Guida pratica per sistems dirigids dad LLM (Claude Code, Cursor, tes agens atgns).

## Pertge ch'il CLI è favuraivel per agens

* **Contract JSON stabil.** `--json` emetta in document JSON valid a stdout e
  *mo* in document JSON — nagin messadi da progress, nagins spinners. Errors van a
  stderr sco `{"error": "...", "detail": "..."}`.
* **Codes da sortida stabels.** `0` ok / `1` diever / `2` autenticaziun /
  `3` server / `4` limitaziun da rata / `5` bet chattà. Agens pon sa decider tenor
  quests codes senza stushar errors en linguatg natiral.
* **Nagins prompts interactivs en contextus headless.** Passa `--yes` (u `-y`) per
  cumonds destructivs; passa `--api-key` u metta `OMI_API_KEY` per evitar il login
  interactiv.
* **Cumportament da retry perdonant.** `429` e `5xx` vegnan retentads cun backoff
  avant che els vegnian a la glisch.

## Autenticaziun (ina giada, da l'uman)

L'utilisader retschaiva ina clav API da developers da l'app web Omi
(`https://app.omi.me` → Developer → API Keys) e lu:

```bash
omi auth login                          # encollar interactiv; clav bet en l'istorgia da la shell
# u
export OMI_API_KEY=omi_dev_...          # efemera, adattada per containers
```

## Las tschintg chaussas che agens fan il pli savens

### 1. Leger memorias

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Crear ina memoria

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Leger conversaziuns

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Leger puncts d'actiun averts

```bash
omi action-item list --json --open
```

### 5. Marcar in punct d'actiun sco fatg

```bash
omi action-item complete --json a1b2c3d4
```

## Local Desktop API

Sche Omi Desktop metta a disposiziun ses API local, pon agens intercurir l'istorgia da
la visur da l'ordinatur, resumés, SQL e tasks senza duvrar il cloud dev API:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# u, per sesiuns efemeras:
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

Completescha u stizza tasks mo sche l'utilisader dumonda explicitamain:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` scriva la foto da la visur sin il
disc ed emetta anc adina JSON a stdout per scripts. L'ID da la foto deriva per ordinari
da `local search-screen` u dad in SQL sur la tabella `screenshots`. Sche Desktop
returna in'errur structurada sco `screenshot_pending`, `screenshot_file_missing` u
`screenshot_chunk_corrupted`, alura il modus JSON mantegna ils champs `reason`, `hint` e
`screenshot_id` sin stderr, uschia che agens pon empruvar ina veglia ID u rapportar
l'impediment exact. Verifitgescha resultats reussids cun `file PATH` avant da als
talar ad utensils da visiun.

## Exempel lavurà: loop d'agens en Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Invochar il CLI omi en modus JSON, lantschar in'exceptiun sin codes da sortida nunreussids."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # Il CLI emetta errors structuradas a stderr en modus JSON:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Leger tut ils puncts d'actiun averts e marcar tut quels pli vegls che 30 dis sco fatgs.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Tractar limitaziuns da rata

Memorias: 120/ura. Conversaziuns: 25/ura. Creaziuns en massa: 15/ura.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # limitaziun da rata
    err = json.loads(result.stderr)
    # err["detail"] para sco: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Tips

* Dovra `--profile <name>` sche tes agens mova plirs contos Omi. Mintga profil ha
  sias atgnas infurmaziuns d'access e sia basa API.
* Dovra `--api-base http://localhost:8080` per testar il backend local.
* Dovra `OMI_LOCAL_API_URL` ed `OMI_LOCAL_TOKEN` per surscriver per ina suletta
  execuziun las configuraziuns da l'API da Desktop dal profil.
* Dovra `--verbose` per il debugging — el protocola `METHOD path → status (Ns)` a stderr
  senza influenzar stdout, uschia che il modus JSON resta valid.
* Per pipar cuntegn en ina conversaziun, dovra `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```