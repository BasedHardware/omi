# omi-cli tekoälyagenteille

> Käytännön opas LLM-pohjaisille ympäristöille (Claude Code, Cursor, omat botit).

## Miksi CLI on agenttiystävällinen

* **Vakaa JSON-sopimus.** Valitsin `--json` tulostaa kelvollisen JSON-dokumentin standarditulosteeseen (stdout) ja *vain* JSON-dokumentin — ei edistymisviestejä, ei latauskuvakkeita. Virheet ohjataan standardivirhetulosteeseen (stderr) muodossa `{"error": "...", "detail": "..."}`.
* **Vakaat poistumiskoodit.** `0` ok / `1` käyttövirhe / `2` todennusvirhe / `3` palvelinvirhe / `4` pyyntöjen enimmiäismäärä saavutettu / `5` ei löydy. Agentit voivat haarautua näiden koodien perusteella ilman luonnollisen kielen virheviestien jäsentämistä.
* **Ei interaktiivisia kehotteita headless-tilassa.** Käytä valitsinta `--yes` (tai `-y`) tuhoisille komennoille; käytä valitsinta `--api-key` tai aseta ympäristömuuttuja `OMI_API_KEY` ohittaaksesi interaktiivisen kirjautumisen.
* **Anteeksiantava uudelleenyritystoiminta.** Koodit `429` ja `5xx` yritetään automaattisesti uudelleen eksponentiaalisella viiveellä (backoff) ennen virheen ilmoittamista.

## Todennus (kertaluonteinen, ihmisen suorittama)

Käyttäjä hankkii kehittäjän API-avaimen Omi-verkkosovelluksesta
(`https://app.omi.me` → Developer → API Keys) ja suorittaa jommankumman seuraavista:

```bash
omi auth login                          # interaktiivinen liittäminen; avain ei tallennu komentorivihistoriaan
# tai
export OMI_API_KEY=omi_dev_...          # lyhytkestoinen, konttiystävällinen
```

## Viisi yleisintä agenttien suorittamaa toimintoa

### 1. Muistojen lukeminen (memories)

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

### 4. Avoimien tehtävien lukeminen (action items)

```bash
omi action-item list --json --open
```

### 5. Tehtävän merkitseminen suoritetuksi

```bash
omi action-item complete --json a1b2c3d4
```

## Paikallinen työpöytä-API (Local Desktop API)

Kun Omi Desktop tarjoaa paikallisen API:nsa, agentit voivat kysellä laitteen näyttöhistoriaa, yhteenvetoja, SQL:ää ja tehtäviä ilman pilven dev-API:a:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# tai lyhytkestoisiin istuntoihin:
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

Merkitse tehtävät valmiiksi tai poista ne vain silloin, kun käyttäjä nimenomaisesti pyytää:

```bash
omi --json local task complete task_1
```
