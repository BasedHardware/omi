# omi-cli agenteille

> Käytännöllinen opas LLM-harnessille (Claude Code, Cursor, omat botsisi).

## Miksi CLI on agenttystäysteori

* **Vakaa JSON-sopimus.** `--json` tulostaa kelvollisen JSON-dokumentin stdout-jokeen ja
  *vain* JSON-dokumentin — ei etenemisviestejä, ei spinneriä. Virheet menevät
  stderr-jokeen muodossa `{"error": "...", "detail": "..."}`.
* **Vakaat exit-koodit.** `0` ok / `1` käyttö / `2` auth / `3` server / `4`
  rate limited / `5` ei löytynyt. Agentit voivat haarautua näiden perusteella
  ilman luonnollisen kielen virheiden jäsentämistä.
* **Ei interaktiivisia kysyjiä headless-ympäristössä.** Välitä `--yes` (tai `-y`)
  tuhoaviin komentoihin; välitä `--api-key` tai aseta `OMI_API_KEY` ohittaaksesi
  interaktiivisen kirjautumisen.
* **Antelias uusintakäytös.** `429` ja `5xx` yritetään uudelleen backoffilla ennen
  esiintuloa.

## Auth (kerran, ihminen)

Käyttäjä hankkii dev API-avaimen Omi-webbisovelluksesta
(`https://app.omi.me` → Developer → API Keys) ja joko:

```bash
omi auth login                          # interactive paste; key not in shell history
# or
export OMI_API_KEY=omi_dev_...          # ephemeral, container-friendly
```

## Viisi asiaa, jotka agentit tekevät useimmin

### 1. Lue muistoja

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Luo muisto

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Lue keskusteluja

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Lue avoimia action itemeja

```bash
omi action-item list --json --open
```

### 5. Merkitse action item valmiiksi

```bash
omi action-item complete --json a1b2c3d4
```

## Paikallinen Desktop API

Kun Omi Desktop paljastaa paikallisen API:nsa, agentit voivat kysyä laitteen
ruutuhistoriaa, recapsia, tehtäviä ja SQL:ää käyttämättä pilven dev API:ta:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# or, for ephemeral sessions:
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

Valmiiksi merkitse tai poista tehtäviä vain kun käyttäjä pyytää sitä selvästi:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` kirjoittaa kuvakaappauksen
levylle ja tulostaa silti JSON:ia stdout-jokeen skripteille. Kuvakaappauksen ID
tulee yleensä `local search-screen`-komennosta tai SQL:stä `screenshots`-taulusta.
Jos Desktop palauttaa rakenteellisen virheen kuten `screenshot_pending`,
`screenshot_file_missing` tai `screenshot_chunk_corrupted`, JSON-tila säilyttää
`reason`-, `hint`- ja `screenshot_id`-kentät stderr-jokeen, jotta agentit voivat
yrittää vanhempaa ID:ta tai raportoida täsmällisen esteen. Vahvista onnistuneet
tulosteet komennolla `file PATH` ennen kuin lähetät ne vision-työkaluille.

## Käytännön esimerkki: Python agent loop

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

## Rate limit -hallinta

Muistoja: 120/tunti. Keskusteluja: 25/tunti. Eräluonnoksia: 15/tunti.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Vinkkejä

* Käytä `--profile <nimi>` jos agenttisi hallinnoi useita Omi-tilejä. Jokaisella
  profiililla on omat valtuutuksensa ja API base.
* Käytä `--api-base http://localhost:8080` paikallista backend-testausta varten.
* Käytä `OMI_LOCAL_API_URL` ja `OMI_LOCAL_TOKEN` ohittaaksesi profiilikohtaiset
  Desktop API -asetukset kerralla.
* Käytä `--verbose` virheidenjäljitykseen — se kirjaa `METHOD path → status (Ns)` stderr-jokeen
  vaikuttamatta stdout-jokeen, joten JSON-tila pysyy kelvollisena.
* Sisällön putkittamiseen keskusteluun käytä `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
