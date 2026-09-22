# omi-cli za agente

> Praktičan vodič za okruženja zasnovana na LLM modelima (Claude Code, Cursor, prilagođeni botovi).

## Zašto je CLI prilagođen agentima

* **Stabilan JSON ugovor.** Zastavica `--json` ispisuje ispravan JSON dokument na stdout i *isključivo* JSON dokument — bez poruka o napretku, bez animacija učitavanja. Greške se šalju na stderr u formatu `{"error": "...", "detail": "..."}`.
* **Stabilni izlazni kodovi.** `0` u redu / `1` greška u korišćenju / `2` greška autentifikacije / `3` greška servera / `4` prekoračeno ograničenje zahteva / `5` nije pronađeno. Agenti mogu donositi odluke na osnovu ovih kodova bez parsiranja poruka na prirodnom jeziku.
* **Bez interaktivnih upita u headless režimu.** Prosledite `--yes` (ili `-y`) za destruktivne komande; prosledite `--api-key` ili postavite promenljivu `OMI_API_KEY` da biste preskočili interaktivnu prijavu.
* **Prilagodljivo ponavljanje zahteva.** Kodovi grešaka `429` i `5xx` se automatski ponavljaju uz eksponencijalno odlaganje (backoff) pre prijavljivanja greške.

## Autentifikacija (jednokratna, izvršava čovek)

Korisnik preuzima razvojni API ključ iz Omi veb aplikacije
(`https://app.omi.me` → Developer → API Keys) i pokreće jedno od sledećeg:

```bash
omi auth login                          # interaktivno lepljenje; ključ se ne čuva u istoriji ljuske
# ili
export OMI_API_KEY=omi_dev_...          # privremeno, pogodno za kontejnere
```

## Pet najčešćih radnji agenata

### 1. Čitanje uspomena (memories)

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Kreiranje uspomene

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

### 5. Označavanje zadatka kao završenog

```bash
omi action-item complete --json a1b2c3d4
```

## Lokalni Desktop API (Local Desktop API)

Kada Omi Desktop omogući svoj lokalni API, agenti mogu pregledati istoriju ekrana na uređaju, sažetke, SQL i zadatke bez korišćenja API-ja u oblaku:

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

Završavajte ili brišite zadatke isključivo kada korisnik to izričito zatraži:

```bash
omi --json local task complete task_1
```
