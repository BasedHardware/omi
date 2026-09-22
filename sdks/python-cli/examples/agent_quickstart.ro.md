# omi-cli pentru agenți

> Ghid practic pentru medii bazate pe LLM (Claude Code, Cursor, boți proprii).

## De ce CLI-ul este optimizat pentru agenți

* **Contract JSON stabil.** Fanionul `--json` emite un document JSON valid la stdout și *exclusiv* un document JSON — fără mesaje de progres, fără indicatori de încărcare. Erorile sunt trimise la stderr sub forma `{"error": "...", "detail": "..."}`.
* **Coduri de ieșire stabile.** `0` ok / `1` eroare de utilizare / `2` eroare de autentificare / `3` eroare de server / `4` limită de apelare atinsă / `5` negăsit. Agenții pot executa ramificări pe baza acestor coduri fără a parsa mesaje în limbaj natural.
* **Fără solicitări interactive în mod headless.** Transmiteți `--yes` (sau `-y`) pentru comenzi distructive; transmiteți `--api-key` sau setați `OMI_API_KEY` pentru a omite autentificarea interactivă.
* **Comportament tolerant la reîncercare.** Codurile `429` și `5xx` sunt reîncercate automat cu backoff exponențial înainte de a raporta eroarea.

## Autentificare (unică, realizată de utilizator)

Utilizatorul obține o cheie API de dezvoltator din aplicația web Omi
(`https://app.omi.me` → Developer → API Keys) și rulează una dintre opțiuni:

```bash
omi auth login                          # lipire interactivă; cheia nu este salvată în istoricul shell-ului
# sau
export OMI_API_KEY=omi_dev_...          # efemer, optimizat pentru containere
```

## Cele cinci acțiuni cele mai frecvente ale agenților

### 1. Citirea amintirilor (memories)

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Crearea unei amintiri

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Citirea conversațiilor

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Citirea sarcinilor deschise (action items)

```bash
omi action-item list --json --open
```

### 5. Marcarea unei sarcini ca finalizată

```bash
omi action-item complete --json a1b2c3d4
```

## API local Desktop (Local Desktop API)

Când Omi Desktop își expune API-ul local, agenții pot interoga istoricul ecranului de pe dispozitiv, recapitulările, SQL și sarcinile fără a utiliza API-ul cloud:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# sau pentru sesiuni efemere:
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

Finalizați sau ștergeți sarcini numai atunci când utilizatorul solicită în mod explicit:

```bash
omi --json local task complete task_1
```
