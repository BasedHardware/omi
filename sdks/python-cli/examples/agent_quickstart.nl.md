# omi-cli voor agents

> Praktische gids voor LLM-aangestuurde omgevingen (Claude Code, Cursor, eigen bots).

## Waarom de CLI agent-vriendelijk is

* **Stabiel JSON-contract.** De vlag `--json` stuurt een geldig JSON-document naar stdout en *uitsluitend* een JSON-document — geen voortgangsberichten, geen spinners. Fouten gaan naar stderr als `{"error": "...", "detail": "..."}`.
* **Stabiele exit-codes.** `0` ok / `1` gebruiksfout / `2` authenticatiefout / `3` serverfout / `4` aanroeplimiet bereikt / `5` niet gevonden. Agents kunnen vertakkingen maken op basis van deze codes zonder foutmeldingen in natuurlijke taal te moeten parsen.
* **Geen interactieve prompts in headless-context.** Geef `--yes` (of `-y`) mee voor destructieve opdrachten; geef `--api-key` mee of stel `OMI_API_KEY` in om interactief inloggen over te slaan.
* **Vergevingsgezind gedrag bij herhalingen.** Foutcodes `429` en `5xx` worden automatisch opnieuw geprobeerd met backoff voordat ze worden gerapporteerd.

## Authenticatie (eenmalig, door de mens)

De gebruiker haalt een ontwikkelaars-API-sleutel op uit de Omi-webapp
(`https://app.omi.me` → Developer → API Keys) en voert een van de volgende opties uit:

```bash
omi auth login                          # interactief plakken; sleutel komt niet in shell-geschiedenis
# of
export OMI_API_KEY=omi_dev_...          # kortstondig, container-vriendelijk
```

## De vijf meest voorkomende acties voor agents

### 1. Herinneringen lezen (memories)

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Een herinnering aanmaken

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Gesprekken lezen

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Openstaande actiepunten lezen (action items)

```bash
omi action-item list --json --open
```

### 5. Een actiepunt als voltooid markeren

```bash
omi action-item complete --json a1b2c3d4
```

## Lokale Desktop-API (Local Desktop API)

Wanneer Omi Desktop zijn lokale API beschikbaar stelt, kunnen agents schermgeschiedenis op het apparaat, samenvattingen, SQL en taken opvragen zonder de cloud-ontwikkelaars-API te gebruiken:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# of voor tijdelijke sessies:
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

Voltooi of verwijder taken alleen wanneer de gebruiker hier expliciet om vraagt:

```bash
omi --json local task complete task_1
```
