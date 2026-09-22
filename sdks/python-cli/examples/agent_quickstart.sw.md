# omi-cli kwa mawakala

> Mwongozo wa vitendo kwa mifumo inayoendeshwa na LLM (Claude Code, Cursor, roboti zako binafsi).

## Kwa nini CLI inafaa kwa mawakala

* **Mkataba thabiti wa JSON.** Bendera ya `--json` hutoa hati halali ya JSON kwa stdout na *hati ya JSON pekee* — hakuna jumbe za maendeleo, hakuna vigeuzi vya upakiaji. Makosa hupelekwa kwa stderr kama `{"error": "...", "detail": "..."}`.
* **Nambari thabiti za kutoka (exit codes).** `0` sawa / `1` kosa la matumizi / `2` kosa la uthibitishaji / `3` kosa la seva / `4` kikomo cha maombi kimefikiwa / `5` haijapatikana. Mawakala wanaweza kufanya maamuzi bila kuchanganua jumbe za lugha ya asili.
* **Hakuna vidokezo shirikishi katika hali isiyo na kiolesura (headless).** Pitisha `--yes` (au `-y`) kwa amri zinazoharibu; pitisha `--api-key` au weka badiliko la mazingira la `OMI_API_KEY` ili kuruka kuingia.
* **Tabia ya kujaribu tena yenye kusamehe.** Nambari za makosa `429` na `5xx` hujaribiwa tena kiotomatiki kwa kucheleweshwa kulingana na fomula (backoff) kabla ya kutoa hitilafu.

## Uthibitishaji (mara moja, unafanywa na binadamu)

Mtumiaji hupata ufunguo wa API ya msanidi programu kutoka kwa programu ya wavuti ya Omi
(`https://app.omi.me` → Developer → API Keys) na kuendesha mojawapo ya yafuatayo:

```bash
omi auth login                          # kubandika kwa maingiliano; ufunguo hauhifadhiwi kwenye historia ya ganda
# au
export OMI_API_KEY=omi_dev_...          # ya muda, inafaa kwa vyombo (containers)
```

## Mambo matano ambayo mawakala hufanya zaidi

### 1. Soma kumbukumbu (memories)

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Unda kumbukumbu

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Soma mazungumzo

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Soma majukumu yaliyo wazi (action items)

```bash
omi action-item list --json --open
```

### 5. Weka alama kwenye jukumu kuwa limekamilika

```bash
omi action-item complete --json a1b2c3d4
```

## Local Desktop API (API ya Ndani ya Kompyuta ya Mezani)

Wakati Omi Desktop inapowasha API yake ya ndani, mawakala wanaweza kuuliza historia ya skrini ya kifaa, mihtasari, SQL na majukumu bila kutumia API ya wingu:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# au, kwa vipindi vya muda mfupi:
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

Kamilisha au futa majukumu pale tu mtumiaji anapoomba kwa uwazi:

```bash
omi --json local task complete task_1
```
