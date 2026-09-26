# omi-cli dlô agentów

> Prakticzny przewòdnik dlô harneców kierowónych przez LLM (Claude Code, Cursor, twòje własne botë).

## Dlô czegò CLI je przëjaznô dlô agentów

* **Stabilny kontrakt JSON.** `--json` wësélô pòprôwny dokùment JSON na stdout i
  *blós* dokùment JSON — żôdnych komunikatów ò pòstãpie, żôdnych spinnerów.
  Felëri jidą na stderr jakno `{"error": "...", "detail": "..."}`.
* **Stabilne kòdë wëjscô.** `0` OK / `1` ùżëcé / `2` aùtentikacjô / `3` serwer
  / `4` limit chùtkòscë / `5` nie nalazłé. Agenty mògą na tim bazowac bez
  parsowaniô felërów w naturalny mòwie.
* **Żôdnych interaktiwnych pëtzaniów w kòntekstach headless.** Pòdôj `--yes`
  (abò `-y`) do destrukcyjnych kòmandów; pòdôj `--api-key` abò ùstaw
  `OMI_API_KEY`, bë òminąc interaktiwne logòwanié.
* **Wëbaczającé zachòwanié retry.** `429` i `5xx` są sprôwòwane znowa z
  backoffã zanim sã pòkôżą.

## Aùtentikacjô (jedón rôz, przez człowieka)

Ùżiwôcz dostôwô klucz API dev z aplikacji web Omi
(`https://app.omi.me` → Developer → API Keys) i pòtim abò:

```bash
omi auth login                          # interaktiwne wklajenié; klucz nie jidze do historëji shella
# abò
export OMI_API_KEY=omi_dev_...          # efemerny, przëjazny dlô kòntenerów
```

## Piãc rzeczi, jaczé agenty robią nôczãszczi

### 1. Czëtac pamiãcé

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Stwòrzëc pamiãc

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Czëtac kònfersacëje

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Czëtac òtemkłé pòzëcje akcjów

```bash
omi action-item list --json --open
```

### 5. Òznaczëc pòzëcjã akcji jakno skùńczoną

```bash
omi action-item complete --json a1b2c3d4
```

## Lokalné API Desktop

Kiedë Omi Desktop wëstawiô swòje lokalné API, agenty mògą pëtac ò historëjã
ekranu na ùrządzenim, pòdsumòwaniô, SQL i zadania bez ùżëcô chmùrowégò API dev:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# abò, dlô efemernych sesëjów:
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

Ùkùńcz abò wëkasëj zadania blós wtedë, ga ùżiwôcz jasno ò to pròszi:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` zapisëje zrzut ekranu na
disk i dali drukùje JSON na stdout dlô skriptów. ID zrzutu nôczãszczi pòchòdzy
z `local search-screen` abò z SQL-a pò tabeli `screenshots`. Jeżlë Desktop
wrôcô struturny felër taczi jakno `screenshot_pending`,
`screenshot_file_missing` abò `screenshot_chunk_corrupted`, trib JSON zachòwô
pòla `reason`, `hint` i `screenshot_id` na stderr, tak że agenty mògą
sprôwac starszi ID abò zgłoscëc dokładny bloker. Weryfikùjë ùdóné wënikówë z
`file PATH` zanim pòdôsz je dali do nôrzãdzów wizëjnych.

## Przëkłôd: pãtla agenta w Pythonie

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Wëwołëj CLI omi w tribie JSON, rzëcając przë kòdach wëjscô jinëch jakno sukces."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI wësélô strukturné felëri na stderr w tribie JSON:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Czëtôj wszëtczé òtemkłé pòzëcje akcjów i znaczi jakno skùńczoné te starszé jakno 30 dni.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Òbsłëga limitów chùtkòscë

Pamiãcë: 120/gòdz. Kònfersacëje: 25/gòdz. Wsadowé stwòrzenié: 15/gòdz.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # limit chùtkòscë
    err = json.loads(result.stderr)
    # err["detail"] wëzdrzi tak: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Radë

* Ùżëwôj `--profile <name>`, jeżlë twój agent òbsługùje wicy kòntów Omi. Kòżdi
  profil mô swòje pòswiadczenié i bazã API.
* Ùżëwôj `--api-base http://localhost:8080` do testowaniô lokalnégò backendu.
* Ùżëwôj `OMI_LOCAL_API_URL` i `OMI_LOCAL_TOKEN`, bë nadpisac lokalné
  ùstawienié Desktop API profilu dlô jednégò przebiegu.
* Ùżëwôj `--verbose` do debugowaniô — logùje `METHOD path → status (Ns)` na
  stderr bez wëstôwianiô na stdout, tak że trib JSON òstôwô pòprôwny.
* Bë przekazac zamkłosc do kònfersacëji, ùżëwôj `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
