# omi-cli za agente

> Praktični vodič za okruženja temeljena na LLM-u (Claude Code, Cursor, vlastiti botovi).

## Zašto je CLI prilagođen agentima

* **Stabilan JSON ugovor.** Zastavica `--json` ispisuje valjani JSON dokument na stdout i *isključivo* JSON dokument — bez poruka o napretku, bez animacija učitavanja. Pogreške se šalju na stderr u formatu `{"error": "...", "detail": "..."}`.
* **Stabilni izlazni kodovi.** `0` u redu / `1` pogreška u korištenju / `2` pogreška u provjeri autentičnosti / `3` poslužiteljska pogreška / `4` premašeno ograničenje zahtjeva / `5` nije pronađeno. Agenti mogu donositi odluke na temelju ovih kodova bez parsiranja poruka prirodnog jezika.
* **Bez interaktivnih upita u headless načinu.** Proslijedite `--yes` (ili `-y`) za destruktivne naredbe; proslijedite `--api-key` ili postavite varijablu `OMI_API_KEY` za preskakanje interaktivne prijave.
* **Prilagodljivo ponavljanje upita.** Kodovi pogrešaka `429` i `5xx` automatski se ponavljaju uz eksponencijalno odgađanje (backoff) prije prijave pogreške.

## Provjera autentičnosti (jednokratna, provodi čovjek)

Korisnik preuzima razvojni API ključ iz web aplikacije Omi
(`https://app.omi.me` → Developer → API Keys) i pokreće jedno od sljedećeg:

```bash
omi auth login                          # interaktivno lijepljenje; ključ se ne sprema u povijest ljuske
# ili
export OMI_API_KEY=omi_dev_...          # privremeno, pogodno za kontejnere
```

## Pet najčešćih radnji agenata

### 1. Čitanje uspomena (memories)

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Stvaranje uspomene

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Čitanje razgovora

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Čitanje otvorenih zadataka (action items)

```bash
omi action-item list --json --open
```

### 5. Označavanje zadatka kao dovršenog

```bash
omi action-item complete --json a1b2c3d4
```

## Lokalni Desktop API (Local Desktop API)

Kada Omi Desktop omogući svoj lokalni API, agenti mogu pregledavati povijest zaslona na uređaju, sažetke, SQL i zadatke bez upotrebe API-ja u oblaku:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# ili za privremene sesije:
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

Dovršite ili izbrišite zadatke isključivo kada korisnik to izričito zatraži:

```bash
omi --json local task complete task_1
```
