# omi-cli za agente

> Praktični vodnik za okolja, ki jih poganjajo modeli LLM (Claude Code, Cursor, lastni boti).

## Zakaj je CLI prijazen do agentov

* **Stabilna pogodba JSON.** Zastavica `--json` izpiše veljaven dokument JSON na stdout in *izključno* dokument JSON — brez sporočil o napredku, brez animacij nalaganja. Napake se pošljejo na stderr v obliki `{"error": "...", "detail": "..."}`.
* **Stabilne izhodne kode (exit codes).** `0` v redu / `1` napaka pri uporabi / `2` napaka pri preverjanju pristnosti / `3` napaka strežnika / `4` presežena omejitev zahtevkov / `5` ni mogoče najti. Agenti se lahko odločajo na podlagi teh kod brez razčlenjevanja sporočil v naravnem jeziku.
* **Brez interaktivnih pozivov v brezglavem načinu (headless).** Podajte `--yes` (ali `-y`) za destruktivne ukaze; podajte `--api-key` ali nastavite spremenljivko `OMI_API_KEY`, da preskočite interaktivno prijavo.
* **Prilagodljivo ponavljanje zahtevkov.** Kode napak `429` in `5xx` se samodejno ponovijo z eksponentnim zamikom (backoff), preden se prikaže napaka.

## Preverjanje pristnosti (enkratno, izvede človek)

Uporabnik pridobi razvojni ključ API iz spletne aplikacije Omi
(`https://app.omi.me` → Developer → API Keys) in zažene eno od naslednjega:

```bash
omi auth login                          # interaktivno lepljenje; ključ se ne shrani v zgodovino lupine
# ali
export OMI_API_KEY=omi_dev_...          # začasno, primerno za vsebinke (containers)
```

## Pet najpogostejših dejanj agentov

### 1. Branje spominov (memories)

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Ustvarjanje spomina

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Branje pogovorov

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Branje odprtih nalog (action items)

```bash
omi action-item list --json --open
```

### 5. Označevanje naloge kot dokončane

```bash
omi action-item complete --json a1b2c3d4
```

## Lokalni namizni API (Local Desktop API)

Ko Omi Desktop omogoči svoj lokalni API, lahko agenti poizvedujejo po zgodovini zaslona naprave, povzetkih, SQL in nalogah brez uporabe API-ja v oblaku:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# ali za začasne seje:
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

Naloge dokončajte ali izbrišite le, ko uporabnik to izrecno zahteva:

```bash
omi --json local task complete task_1
```
