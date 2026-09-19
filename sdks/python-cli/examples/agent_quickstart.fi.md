# omi-cli agenteille

> Käytännön opas LLM-ohjatuille ympäristöille (Claude Code, Cursor, omat botit).

## Miksi CLI on agenttiystävällinen

* **Vakaa JSON-sopimus.** Valitsin `--json` tulostaa stdoutiin kelvollisen JSON-asiakirjan ja *vain* JSON-asiakirjan — ei edistymisviestejä tai latausanimaatioita. Virheet ohjataan stderr-tulosteeseen muodossa `{"error": "...", "detail": "..."}`.
* **Vakaat poistumiskoodit.** `0` ok / `1` käyttövirhe / `2` todennusvirhe / `3` palvelinvirhe / `4` nopeusrajoitus / `5` ei löydy. Agentit voivat haarautua näiden perusteella ilman luonnollisen kielen virheviestien jäsentämistä.
* **Ei interaktiivisia kehotteita taustaympäristöissä.** Lisää `--yes` (tai `-y`) tuhoaviin komentoihin; anna `--api-key` tai aseta `OMI_API_KEY` ohittaaksesi vuorovaikutteisen kirjautumisen.
* **Armollinen uudelleenyritystoiminta.** Koodit `429` ja `5xx` yritetään automaattisesti uudelleen eksponentiaalisella viiveellä ennen niiden raportointia.

## Todennus (kertaluonteinen, ihmisen tekemä)

Käyttäjä hakee kehittäjän API-avaimen Omi-verkkosovelluksesta (`https://app.omi.me` → Developer → API Keys) ja tekee jommankumman seuraavista:

```bash
omi auth login                          # interaktiivinen liittäminen; avain ei tallennu komentorivihistoriaan
# tai
export OMI_API_KEY=omi_dev_...          # väliaikainen, konttiystävällinen
```

## Viisi yleisintä asiaa, joita agentit tekevät

### 1. Muistojen lukeminen

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Muiston luominen

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Keskustelujen lukeminen

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Avointen tehtävien lukeminen

```bash
omi action-item list --json --open
```

### 5. Tehtävän merkitseminen tehdyksi

```bash
omi action-item complete --json a1b2c3d4
```

## Paikallinen Desktop API

Kun Omi Desktop tarjoaa paikallisen API-rajapintansa, agentit voivat hakea laitteen näyttöhistoriaa, yhteenvetoja, SQL-tietoja ja tehtäviä ilman pilven kehittäjä-API:a:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# tai väliaikaisille istunnoille:
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

Merkitse valmiiksi tai poista tehtäviä vain silloin, kun käyttäjä pyytää sitä nimenomaisesti:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` tallentaa näyttökuvan levylle ja tulostaa komentosarjoille edelleen JSON-muotoista dataa stdoutiin. Näyttökuvan ID saadaan yleensä komennosta `local search-screen` tai SQL-kyselystä tauluun `screenshots`. Jos Desktop palauttaa jäsennellyn virheen, kuten `screenshot_pending`, `screenshot_file_missing` tai `screenshot_chunk_corrupted`, JSON-tila säilyttää kentät `reason`, `hint` ja `screenshot_id` stderrissä, jotta agentit voivat yrittää vanhemmalla ID:llä uudelleen tai ilmoittaa tarkan esteen. Vahvista onnistuneet tiedostot komennolla `file PATH` ennen niiden välittämistä konenäkötyökaluille.

## Käytännön esimerkki: Python-agentsilmukka

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Kutsuu omi CLI:tä JSON-tilassa ja nostaa poikkeuksen epäonnistuneilla poistumiskoodeilla."""
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
        raise RuntimeError(f"omi päättyi koodilla {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Lukee kaikki avoimet tehtävät ja merkitsee yli 30 päivää vanhat valmiiksi.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Nopeusrajoitusten hallinta

Muistot: 120/tunti. Keskustelut: 25/tunti. Eräluonti: 15/tunti.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # nopeusrajoitus
    err = json.loads(result.stderr)
    # err["detail"] näyttää tältä: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Vinkkejä

* Käytä `--profile <nimi>`, jos agenttisi käsittelee useita Omi-tilejä. Jokaisella profiililla on omat tunnistetiedot ja API-osoite.
* Käytä `--api-base http://localhost:8080` paikalliseen taustajärjestelmän testaukseen.
* Käytä ympäristömuuttujia `OMI_LOCAL_API_URL` ja `OMI_LOCAL_TOKEN` korvaamaan profiilin paikalliset Desktop API -asetukset yhdelle suoritukselle.
* Käytä `--verbose` virheenkorjaukseen — se kirjaa `METHOD path → status (Ns)` stderr-virtaan vaikuttamatta stdoutiin, joten JSON-tila pysyy kelvollisena.
* Jos haluat ohjata sisältöä keskusteluun putken (pipe) kautta, käytä `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
