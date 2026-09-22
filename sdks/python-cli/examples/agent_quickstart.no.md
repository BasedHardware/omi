# omi-cli for agenter

> Praktisk veiledning for LLM-drevne miljøer (Claude Code, Cursor, egne boter).

## Hvorfor CLI-en er agentvennlig

* **Stabil JSON-kontrakt.** Flagget `--json` sender et gyldig JSON-dokument til stdout og *utelukkende* et JSON-dokument — ingen fremdriftsmeldinger, ingen spinnere. Feil sendes til stderr i formatet `{"error": "...", "detail": "..."}`.
* **Stabile avslutningskoder.** `0` ok / `1` bruksfeil / `2` autentiseringsfeil / `3` serverfeil / `4` hastighetsgrense nådd / `5` ikke funnet. Agenter kan ta beslutninger basert på disse kodene uten å måtte parse meldinger i naturlig språk.
* **Ingen interaktive ledetekster i hodeløs (headless) modus.** Send inn `--yes` (eller `-y`) for destruktive kommandoer; send inn `--api-key` eller angi miljøvariabelen `OMI_API_KEY` for å hoppe over interaktiv innlogging.
* **Robust håndtering av nye forsøk.** Feilkodene `429` og `5xx` prøves automatisk på nytt med eksponensiell tilbakeholdelse (backoff) før feil rapporteres.

## Autentisering (engangs, utføres av et menneske)

Brukeren henter en API-utviklernøkkel fra Omi-nettappen
(`https://app.omi.me` → Developer → API Keys) og kjører ett av følgende:

```bash
omi auth login                          # interaktiv innliming; nøkkelen lagres ikke i skallhistorikken
# eller
export OMI_API_KEY=omi_dev_...          # flyktig, container-vennlig
```

## Fem vanligste agenthandlinger

### 1. Les minner (memories)

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Opprett et minne

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Les samtaler

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Les åpne gjøremål (action items)

```bash
omi action-item list --json --open
```

### 5. Merk et gjøremål som fullført

```bash
omi action-item complete --json a1b2c3d4
```

## Lokalt Desktop API (Local Desktop API)

Når Omi Desktop tilgjengeliggjør sitt lokale API, kan agenter hente skjermhistorikk på enheten, sammendrag, SQL og oppgaver uten å bruke sky-API-et:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# eller for midlertidige økter:
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

Fullfør eller slett oppgaver kun når brukeren uttrykkelig ber om det:

```bash
omi --json local task complete task_1
```
