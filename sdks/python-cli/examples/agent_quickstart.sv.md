# omi-cli för agenter

> Praktisk guide för LLM-drivna miljöer (Claude Code, Cursor, egna bottar).

## Varför CLI:et är agentvänligt

* **Stabilt JSON-kontrakt.** Flaggan `--json` matar ut ett giltigt JSON-dokument till stdout och *endast* ett JSON-dokument — inga förloppsmeddelanden, inga laddningsindikatorer. Fel skickas till stderr som `{"error": "...", "detail": "..."}`.
* **Stabila slutkoder.** `0` ok / `1` användningsfel / `2` autentiseringsfel / `3` serverfel / `4` anropsgräns nådd / `5` hittades inte. Agenter kan förrena logik baserat på dessa koder utan att behöva tolka felmeddelanden på naturligt språk.
* **Inga interaktiva frågor i headless-kontext.** Ange `--yes` (eller `-y`) för destruktiva kommandon; ange `--api-key` eller sätt miljövariabeln `OMI_API_KEY` för att hoppa över interaktiv inloggning.
* **Förlåtande beteende vid återförsök.** `429` och `5xx` försöks automatiskt igen med exponentiell backoff innan felet returneras.

## Autentisering (engångsåtgärd, utförs av människan)

Användaren hämtar en utvecklar-API-nyckel från Omi-webbappen
(`https://app.omi.me` → Developer → API Keys) och kör antingen:

```bash
omi auth login                          # interaktiv inklistring; nyckeln sparas inte i skalets historik
# eller
export OMI_API_KEY=omi_dev_...          # efemärt, container-vänligt
```

## De fem vanligaste åtgärderna som agenter utför

### 1. Läs minnen (memories)

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Skapa ett minne

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Läs konversationer

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Läs öppna åtgärdspunkter (action items)

```bash
omi action-item list --json --open
```

### 5. Markera en åtgärdspunkt som klar

```bash
omi action-item complete --json a1b2c3d4
```

## Lokalt Desktop-API (Local Desktop API)

När Omi Desktop exponerar sitt lokala API kan agenter fråga historik på enheten, sammanfattningar, SQL och uppgifter utan att använda molnets dev-API:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# eller för efemära sessioner:
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

Slutför eller ta endast bort uppgifter när användaren uttryckligen ber om det:

```bash
omi --json local task complete task_1
```
