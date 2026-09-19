# omi-cli za agente

> Praktični vodnik za orodja, ki jih poganjajo modeli LLM (Claude Code, Cursor, lastni boti).

## Zakaj je CLI prijazen do agentov

* **Stabilna pogodba JSON.** Orodje `--json` posreduje veljaven dokument JSON na stdout in
  *izključno* dokument JSON — brez sporočil o napredku ali animacij. Napake se izpišejo na
  stderr v obliki `{"error": "...", "detail": "..."}`.
* **Stabilne izhodne kode.** `0` v redu / `1` napaka pri uporabi / `2` avtentikacija / `3` napaka strežnika / `4` omejitev hitrosti / `5` ni mogoče najti. Agenti se lahko vejijo glede na te kode brez razčlenjevanja sporočil v naravnem jeziku.
* **Brez interaktivnih pozivov v brezglavih okoljih.** Uporabite `--yes` (ali `-y`) pri
  destruktivnih ukazih; uporabite `--api-key` ali nastavite `OMI_API_KEY`, da preskočite interaktivno prijavo.
* **Prizanesljivo vedenje pri ponovnem poskusu.** Napaki `429` in `5xx` se pred sprožitvijo
  ponovno poskusita s postopnim zamikom.

## Avtentikacija (enkratno dejanje s strani človeka)

Uporabnik pridobi razvojni ključ API v spletni aplikaciji Omi
(`https://app.omi.me` → Developer → API Keys) in izbere eno od možnosti:

```bash
omi auth login                          # interaktivno lepljenje; ključ se ne shrani v zgodovino lupine
# ali
export OMI_API_KEY=omi_dev_...          # začasno, primerno za vsebnike
```

## Pet stvari, ki jih agenti najpogosteje izvajajo

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

### 4. Branje odprtih opravil

```bash
omi action-item list --json --open
```

### 5. Označevanje opravila kot dokončanega

```bash
omi action-item complete --json a1b2c3d4
```

## Lokalni API za namizje (Desktop API)

Ko Omi Desktop omogoči lokalni API, lahko agenti poizvedujejo po zgodovini zaslona na napravi,
povzetkih, SQL in nalogah brez uporabe oblačnega API-ja:

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

Naloge dokončajte ali izbrišite le, če uporabnik to izrecno zahteva:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

Ukaz `omi local screenshot SCREENSHOT_ID --output PATH` shrani posnetek zaslona na
disk in še naprej izpisuje JSON na stdout za skripte. ID posnetka zaslona običajno izhaja
iz ukaza `local search-screen` ali poizvedbe SQL nad tabelo `screenshots`. Če namizje
vrne strukturirano napako, kot so `screenshot_pending`, `screenshot_file_missing`
ali `screenshot_chunk_corrupted`, način JSON ohrani polja `reason`, `hint` in
`screenshot_id` na stderr, da lahko agenti poskusijo s starejšim ID-jem ali sporočijo
točno oviro. Pred posredovanjem orodjem za vid preverite veljavnost izhodov z ukazom `file PATH`.

## Praktični primer: zanka agenta v Pythonu

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Zaženi omi CLI v načinu JSON in sproži izjemo ob napakah."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI v načinu JSON izpisuje strukturirane napake na stderr:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Preberi vsa odprta opravila in označi tista, starejša od 30 dni, kot zaključena.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Ravnanje z omejitvami hitrosti (rate limits)

Spomini: 120/uro. Pogovori: 25/uro. Paketno ustvarjanje: 15/uro.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # omejitev hitrosti
    err = json.loads(result.stderr)
    # err["detail"] izgleda tako: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Nasveti

* Uporabite `--profile <ime>`, če vaš agent upravlja več računov Omi. Vsak
  profil ima lastne poverilnice in osnovni naslov API.
* Za lokalno testiranje zaledja uporabite `--api-base http://localhost:8080`.
* Uporabite `OMI_LOCAL_API_URL` in `OMI_LOCAL_TOKEN` za prepis lokalnih nastavitev
  namiznega API-ja za en zagon.
* Za odpravljanje napak uporabite `--verbose` — beleži `METHOD path → status (Ns)` na stderr
  brez vpliva na stdout, zato način JSON ostaja veljaven.
* Za posredovanje vsebine v pogovor prek cevi uporabite `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
