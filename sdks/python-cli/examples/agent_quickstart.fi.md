# omi-cli agenteille

> Käytännön opas LLM-ohjatuille työkaluille (Claude Code, Cursor, omat botit).

## Miksi CLI on agenttiystävällinen

* **Vakaa JSON-sopimus.** `--json` tulostaa kelvollisen JSON-dokumentin stdout-virtaan ja
  *vain* JSON-dokumentin — ei edistymisviestejä, ei animaatioita. Virheet tulostuvat
  stderr-virtaan muodossa `{"error": "...", "detail": "..."}`.
* **Vakaat poistumiskoodit.** `0` ok / `1` käyttövirhe / `2` todennusvirhe / `3` palvelinvirhe / `4` nopeusrajoitus / `5` ei löydy. Agentit voivat haarautua näiden perusteella ilman luonnollisen kielen virheiden jäsentämistä.
* **Ei interaktiivisia kehotteita tausta-ajossa.** Välitä `--yes` (tai `-y`) tuhoaville
  komennoille; välitä `--api-key` tai aseta `OMI_API_KEY` ohittaaksesi interaktiivisen kirjautumisen.
* **Joustava uudelleenyrityskäyttäytyminen.** Koodit `429` ja `5xx` yritetään uudelleen viiveellä
  ennen virheen nostamista.

## Todennus (ihmisen tekemä kertaluonteinen toimi)

Käyttäjä hankkii kehittäjän API-avaimen Omi-verkkosovelluksesta
(`https://app.omi.me` → Developer → API Keys) ja joko:

```bash
omi auth login                          # interaktiivinen liittäminen; avain ei tallennu komentohistoriaan
# tai
export OMI_API_KEY=omi_dev_...          # väliaikainen, konttiystävällinen
```

## Viisi asiaa, joita agentit tekevät eniten

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

### 4. Lue avoimet toimenpiteet

```bash
omi action-item list --json --open
```

### 5. Merkitse toimenpide tehdyksi

```bash
omi action-item complete --json a1b2c3d4
```

## Paikallinen Työpöytä-API (Desktop API)

Kun Omi Desktop tarjoaa paikallisen API:nsa, agentit voivat tehdä hakuja laitteen ruutuhistoriasta,
koosteista, SQL:stä ja tehtävistä ilman pilvi-API:a:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# tai väliaikaisia istuntoja varten:
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

Suorita tai poista tehtäviä vain silloin, kun käyttäjä nimenomaisesti sitä pyytää:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

Komento `omi local screenshot SCREENSHOT_ID --output PATH` kirjoittaa kuvankaappauksen
levylle ja tulostaa samalla JSON:ia stdout-virtaan skriptejä varten. Kuvankaappauksen ID saadaan
yleensä komennolla `local search-screen` tai SQL-kyselyllä `screenshots`-taulusta. Jos Työpöytä
palauttaa jäsennellyn virheen kuten `screenshot_pending`, `screenshot_file_missing`
tai `screenshot_chunk_corrupted`, JSON-tila säilyttää kentät `reason`, `hint` ja
`screenshot_id` stderr-virrassa, jotta agentit voivat yrittää vanhempaa ID:tä tai ilmoittaa
tarkan esteen. Vahvista onnistuneet tulosteet komennolla `file PATH` ennen niiden välittämistä
näkömalleille.

## Työskentelyesimerkki: Python-agenttisilmukka

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Kutsu omi CLI:tä JSON-tilassa ja nosta poikkeus virhekoodeilla."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI tulostaa jäsennellyt virheet stderr-virtaan JSON-tilassa:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Lue kaikki avoimet toimenpiteet ja merkitse yli 30 päivää vanhat suoritetuiksi.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Nopeusrajoitusten käsittely

Muistot: 120/tunti. Keskustelut: 25/tunti. Eräluonnit: 15/tunti.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # nopeusrajoitettu
    err = json.loads(result.stderr)
    # err["detail"] näyttää tältä: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Vinkkejä

* Käytä valitsinta `--profile <nimi>`, jos agenttisi käsittelee useita Omi-tilejä. Jokaisella
  profiililla on omat tunnistetietonsa ja API-osoitteensa.
* Käytä valitsinta `--api-base http://localhost:8080` paikallista taustapalvelimen testausta varten.
* Käytä ympäristömuuttujia `OMI_LOCAL_API_URL` ja `OMI_LOCAL_TOKEN` korvaamaan profiilin paikalliset
  Desktop API -asetukset yhdelle ajolle.
* Käytä valitsinta `--verbose` virheenkorjaukseen — se kirjaa `METHOD path → status (Ns)` stderr-virtaan
  vaikuttamatta stdout-virtaan, jolloin JSON-tila säilyy kelvollisena.
* Sisällön putkittamiseksi keskusteluun käytä valitsinta `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
