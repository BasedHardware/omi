# omi-cli ar gyfer asiantau

> Canllaw ymarferol ar gyfer amgylcheddau a yrrir gan LLM (Claude Code, Cursor, eich botiau eich hun).

## Pam bod y CLI yn gyfeillgar i asiantau

* **Cytundeb JSON sefydlog.** Mae'r faner `--json` yn anfon dogfen JSON ddilys i stdout ac *yn unig* dogfen JSON — dim negeseuon cynnydd, dim sbinwyr. Mae gwallau'n mynd i stderr fel `{"error": "...", "detail": "..."}`.
* **Codau ymadael sefydlog.** `0` iawn / `1` gwall defnydd / `2` gwall dilysu / `3` gwall gweinydd / `4` terfyn cyfradd wedi'i gyrraedd / `5` heb ei ddarganfod. Gall asiantau weithredu ar sail y codau hyn heb orfod dosrannu negeseuon iaith naturiol.
* **Dim awgrymiadau rhyngweithiol mewn cyd-destun di-ben (headless).** Pasio `--yes` (neu `-y`) i orchmynion dinistriol; pasio `--api-key` neu osod y newidyn amgylcheddol `OMI_API_KEY` i hepgor mewngofnodi rhyngweithiol.
* **Ymddygiad ail-geisio maddau.** Mae codau gwall `429` a `5xx` yn cael eu hail-geisio'n awtomatig gyda gohiriad cynyddol (backoff) cyn cyflwyno gwall.

## Dilysu (un tro, gan berson)

Mae'r defnyddiwr yn cael allwedd API datblygwr o ap gwe Omi
(`https://app.omi.me` → Developer → API Keys) a rhedeg un o'r canlynol:

```bash
omi auth login                          # gludo rhyngweithiol; allwedd heb ei chadw yn hanes y gragen
# neu
export OMI_API_KEY=omi_dev_...          # dros dro, cyfleus ar gyfer cynwysyddion (containers)
```

## Y pum peth y mae asiantau'n eu gwneud amlaf

### 1. Darllen atgofion (memories)

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Creu atgof

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Darllen sgyrsiau

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Darllen tasgau gweithredu agored (action items)

```bash
omi action-item list --json --open
```

### 5. Marcio eitem weithredu fel un wedi'i chwblhau

```bash
omi action-item complete --json a1b2c3d4
```

## API Bwrdd Gwaith Lleol (Local Desktop API)

Pan fydd Omi Desktop yn datgelu ei API lleol, gall asiantau ymholi hanes sgrin y ddyfais, crynodebau, SQL a thasgau heb ddefnyddio API'r cwmwl:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# neu, ar gyfer sesiynau byrhoedlog:
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

Cwblhewch neu ddilëwch dasgau dim ond pan fydd y defnyddiwr yn gofyn yn benodol:

```bash
omi --json local task complete task_1
```
