# omi-cli pre agentov

> Praktický sprievodca pre prostredia riadené LLM (Claude Code, Cursor, vlastní boti).

## Prečo je CLI prívetivé pre agentov

* **Stabilný kontrakt JSON.** Prepínač `--json` vypisuje platný JSON dokument na štandardný výstup (stdout) a *výhradne* JSON dokument — žiadne stavové hlásenia, žiadne indikátory načítania. Chyby smerujú na štandardný chybový výstup (stderr) vo formáte `{"error": "...", "detail": "..."}`.
* **Stabilné návratové kódy.** `0` v poriadku / `1` chyba použitia / `2` chyba autentifikácie / `3` chyba servera / `4` prekročený limit volaní / `5` nenájdené. Agenti sa môžu podľa týchto kódov rozhodovať bez nutnosti parsovať hlásenia v prirodzenom jazyku.
* **Žiadne interaktívne výzvy v bezhlavom režime (headless).** Pre deštruktívne príkazy zadajte `--yes` (alebo `-y`); zadajte `--api-key` alebo nastavte premennú prostredia `OMI_API_KEY` na preskočenie interaktívneho prihlásenia.
* **Odolné správanie pri opakovaní.** Chybové kódy `429` a `5xx` sa pred vrátením chyby automaticky opakujú s exponenciálnym odstupom (backoff).

## Autentifikácia (jednorazová, vykonávaná človekom)

Používateľ získa vývojársky API kľúč z webovej aplikácie Omi
(`https://app.omi.me` → Developer → API Keys) a vykoná jednu z možností:

```bash
omi auth login                          # interaktívne vloženie; kľúč sa neuloží do histórie shellu
# alebo
export OMI_API_KEY=omi_dev_...          # dočasné, vhodné pre kontajnery
```

## Päť najčastejších úkonov agentov

### 1. Čítanie spomienok (memories)

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Vytvorenie spomienky

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Čítanie konverzácií

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Čítanie otvorených úloh (action items)

```bash
omi action-item list --json --open
```

### 5. Označenie úlohy ako dokončenej

```bash
omi action-item complete --json a1b2c3d4
```

## Lokálne Desktop API (Local Desktop API)

Keď Omi Desktop sprístupní svoje lokálne API, agenti sa môžu dopytovať na históriu obrazovky na zariadení, rekapitulácie, SQL a úlohy bez použitia cloudového dev API:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# alebo pre dočasné relácie:
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

Úlohy dokončujte alebo mažte výhradne na výslovnú žiadosť používateľa:

```bash
omi --json local task complete task_1
```
