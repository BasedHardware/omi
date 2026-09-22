# omi-cli for agenter

> Praktisk vejledning til LLM-drevne miljøer (Claude Code, Cursor, brugerdefinerede bots).

## Hvorfor CLI'en er agent-venlig

* **Stabil JSON-kontrakt.** Flaget `--json` udskriver et gyldigt JSON-dokument til standard output (stdout) og *udelukkende* et JSON-dokument — ingen statusmeddelelser, ingen indlæsningsikoner. Fejl sendes til standard error (stderr) i formatet `{"error": "...", "detail": "..."}`.
* **Stabile afslutningskoder.** `0` ok / `1` brugsfejl / `2` godkendelsesfejl / `3` serverfejl / `4` anmodningsgrænse overskredet / `5` ikke fundet. Agenter kan forgrene logik på baggrund af disse koder uden at behøve at parse fejlmeddelelser i naturligt sprog.
* **Ingen interaktive meddelelser i headless-tilstand.** Tilføj `--yes` (eller `-y`) for destruktive kommandoer; tilføj `--api-key` eller indstil miljøvariablen `OMI_API_KEY` for at springe interaktivt login over.
* **Fleksibel genprøvningsadfærd.** Fejlkoder `429` og `5xx` genprøves automatisk med eksponentiel backoff, før fejlen rapporteres.

## Godkendelse (engangs, udført af menneske)

Brugeren henter en API-udviklernøgle fra Omi webappen
(`https://app.omi.me` → Developer → API Keys) og kører en af følgende:

```bash
omi auth login                          # interaktiv indsættelse; nøglen gemmes ikke i shell-historikken
# eller
export OMI_API_KEY=omi_dev_...          # kortvarig, container-venlig
```

## Fem mest almindelige agenthandlinger

### 1. Læs minder (memories)

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Opret et minde

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Læs samtaler

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Læs åbne handlingspunkter (action items)

```bash
omi action-item list --json --open
```

### 5. Markér et handlingspunkt som fuldført

```bash
omi action-item complete --json a1b2c3d4
```

## Lokalt Desktop API (Local Desktop API)

Når Omi Desktop gør sit lokale API tilgængeligt, kan agenter forespørge enhedens skærmhistorik, opsummeringer, SQL og opgaver uden at benytte cloud-API'et:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# eller for midlertidige sessioner:
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

Afslut eller slet kun opgaver, når brugeren udtrykkeligt anmoder om det:

```bash
omi --json local task complete task_1
```
