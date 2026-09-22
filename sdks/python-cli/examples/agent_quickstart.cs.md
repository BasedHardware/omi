# omi-cli pro agenty

> Praktický průvodce pro prostředí řízená LLM (Claude Code, Cursor, vlastní boti).

## Proč je CLI přívětivé pro agenty

* **Stabilní kontrakt JSON.** Přepínač `--json` vypisuje platný dokument JSON na standardní výstup (stdout) a *výhradně* dokument JSON — žádné stavové zprávy, žádné animace načítání. Chyby směřují na standardní chybový výstup (stderr) ve formátu `{"error": "...", "detail": "..."}`.
* **Stabilní návratové kódy.** `0` v pořádku / `1` chyba použití / `2` chyba autentizace / `3` chyba serveru / `4` překročen limit požadavků / `5` nenalezeno. Agenti se mohou podle těchto kódů rozhodovat bez nutnosti parsovat text v přirozeném jazyce.
* **Žádné interaktivní výzvy v bezhlavém režimu (headless).** Pro destruktivní příkazy zadejte `--yes` (nebo `-y`); zadejte `--api-key` nebo nastavte proměnnou `OMI_API_KEY` pro přeskočení interaktivního přihlášení.
* **Tolerantní chování při opakování.** Kódy `429` a `5xx` se před vrácením chyby automaticky opakují s exponenciálním odstupem (backoff).

## Autentizace (jednorázová, prováděná člověkem)

Uživatel získá vývojářský API klíč z webové aplikace Omi
(`https://app.omi.me` → Developer → API Keys) a provede jedno z následujících:

```bash
omi auth login                          # interaktivní vložení; klíč se neuloží do historie shellu
# nebo
export OMI_API_KEY=omi_dev_...          # efemérní, vhodné pro kontejnery
```

## Pět nejčastějších úkonů agentů

### 1. Čtení vzpomínek (memories)

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Vytvoření vzpomínky

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Čtení konverzací

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Čtení otevřených úkolů (action items)

```bash
omi action-item list --json --open
```

### 5. Označení úkolu jako hotového

```bash
omi action-item complete --json a1b2c3d4
```

## Lokální Desktop API (Local Desktop API)

Když Omi Desktop zpřístupní své lokální API, agenti mohou dotazovat historii obrazovky na zařízení, rekapitulace, SQL a úkoly bez použití cloudového dev API:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# nebo pro efemérní relace:
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

Úkoly dokončujte nebo mazejte pouze na výslovnou žádost uživatele:

```bash
omi --json local task complete task_1
```
