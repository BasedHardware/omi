# omi-cli za AI agente

> Praktični vodnik za sisteme, vodene z LLM (Claude Code, Cursor, lastni boti).

## Zakaj je CLI prijazen do agentov

* **Stabilna JSON pogodba.** Zastavica `--json` posreduje veljaven dokument JSON na stdout in
  *izključno* dokument JSON — brez sporočil o napredku ali animacij nalaganja. Napake se
  posredujejo na stderr kot `{"error": "...", "detail": "..."}`.
* **Stabilne izhodne kode.** `0` v redu / `1` napačna uporaba / `2` avtentikacija / `3` strežnik /
  `4` presežena omejitev zahtevkov / `5` ni mogoče najti. Agenti se lahko neposredno vejajo na
  podlagi teh kod brez analize naravnega jezika.
* **Brez interaktivnih pozivov v headless okoljih.** Za destruktivne ukaze uporabite `--yes` (ali `-y`);
  uporabite `--api-key` ali nastavite okoljsko spremenljivko `OMI_API_KEY`, da preskočite
  interaktivno prijavo.
* **Prizanesljivo ponavljanje zahtevkov.** Napake tipa `429` in `5xx` se samodejno ponovijo z
  eksponentnim zamikom (backoff), preden se prijavijo navzven.

## Avtentikacija (enkratna, s strani človeka)

Uporabnik pridobi razvojni API ključ v spletni aplikaciji Omi
(`https://app.omi.me` → Developer → API Keys) in stori eno od naslednjega:

```bash
omi auth login                          # interaktivno lepljenje; ključ se ne shrani v zgodovino ukazne vrstice
# ali
export OMI_API_KEY=omi_dev_...          # začasno, primerno za vsebnike
```

## Pet najpogostejših opravil agentov

### 1. Branje spominov

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Ustvarjanje spomina

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Branje pogovorov

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Branje odprtih akcijskih postavk

```bash
omi action-item list --json --open
```

### 5. Označevanje postavke kot zaključene

```bash
omi action-item complete --json a1b2c3d4
```

## Lokalni Desktop API

Ko Omi Desktop omogoči svoj lokalni API, lahko agenti poizvedujejo po lokalni zgodovini zaslona
naprave, povzetkih, SQL podatkih in opravilih brez uporabe oblačnega razvijalskega API-ja:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# ali za začasne seje:
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

Opravila dokončajte ali izbrišite samo takrat, ko uporabnik to izrecno zahteva:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

Ukaz `omi local screenshot SCREENSHOT_ID --output PATH` shrani posnetek zaslona na disk
in še naprej izpisuje JSON na stdout za skripte. ID posnetka zaslona običajno izhaja iz ukaza
`local search-screen` ali SQL poizvedbe v tabeli `screenshots`. Če Desktop vrne strukturirano
napako, kot je `screenshot_pending`, `screenshot_file_missing` ali `screenshot_chunk_corrupted`,
način JSON ohrani polja `reason`, `hint` in `screenshot_id` na stderr, tako da lahko agenti
poskusijo starejši ID ali sporočijo točno oviro. Pred posredovanjem orodjem za računalniški vid
preverite uspešne izhode z ukazom `file PATH`.

## Praktičen primer: Python zanka za agente

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

## Obravnava omejitev zahtevkov (Rate Limits)

Spomini: 120/uro. Pogovori: 25/uro. Paketno ustvarjanje: 15/uro.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Nasveti

* Uporabite `--profile <name>`, če vaš agent upravlja več računov Omi hkrati. Vsak
  profil ima lastne poverilnice in osnovni API naslov.
* Uporabite `--api-base http://localhost:8080` za lokalno testiranje zalednega sistema.
* Uporabite spremenljivki `OMI_LOCAL_API_URL` in `OMI_LOCAL_TOKEN` za preglasitev lokalnih
  nastavitev Desktop API profila za posamezen zagon.
* Uporabite `--verbose` za razhroščevanje — beleži `METHOD path → status (Ns)` na stderr
  brez vpliva na stdout, zato način JSON ostaja veljaven.
* Za posredovanje vsebine v pogovor uporabite `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
