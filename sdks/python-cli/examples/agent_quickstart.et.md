# omi-cli agentidele

> Praktiline juhend LLM-põhistele keskkondadele (Claude Code, Cursor, kohandatud robotid).

## Miks CLI on agendisõbralik

* **Stabiilne JSON leping.** Lipp `--json` väljastab kehtiva JSON-dokumendi stdout-i ja *ainult* JSON-dokumendi — ilma edenemissõnumiteta, ilma laadimisikoonideta. Vead suunatakse stderr-i vormingus `{"error": "...", "detail": "..."}`.
* **Stabiilsed väljumiskoodid (exit codes).** `0` korras / `1` kasutusviga / `2` autentimisviga / `3` serveriviga / `4` päringulimiit ületatud / `5` ei leitud. Agendid saavad teha otsuseid nende koodide põhjal ilma loomuliku keele sõnumeid analüüsimata.
* **Puuduvad interaktiivsed viibad peata režiimis (headless).** Edastage `--yes` (või `-y`) hävitavatele käskudele; edastage `--api-key` või määrake keskkonnamuutuja `OMI_API_KEY`, et vältida interaktiivset sisselogimist.
* **Paindlik uuestiproovimise käitumine.** Veakoode `429` ja `5xx` proovitakse automaatselt uuesti koos eksponentsiaalse viivitusega (backoff) enne veateate kuvamist.

## Autentimine (ühekordne, teostab inimene)

Kasutaja hangib arendaja API võtme Omi veebirakendusest
(`https://app.omi.me` → Developer → API Keys) ja käivitab ühe järgmistest:

```bash
omi auth login                          # interaktiivne kleepimine; võtit ei salvestata kesta ajalukku
# või
export OMI_API_KEY=omi_dev_...          # ajutine, sobib hästi konteineritesse
```

## Viis toimingut, mida agendid kõige sagedamini teevad

### 1. Mälestuste lugemine (memories)

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Mälestuse loomine

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Vestluste lugemine

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Avatud ülesannete lugemine (action items)

```bash
omi action-item list --json --open
```

### 5. Ülesande märkimine tehtuks

```bash
omi action-item complete --json a1b2c3d4
```

## Kohalik töölaua API (Local Desktop API)

Kui Omi Desktop lubab oma kohaliku API, saavad agendid pärida seadmesisest ekraaniajalugu, kokkuvõtteid, SQL-i ja ülesandeid ilma pilve-API-t kasutamata:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# või ajutiste seansside jaoks:
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

Lõpetage või kustutage ülesandeid ainult siis, kui kasutaja seda selgesõnaliselt palub:

```bash
omi --json local task complete task_1
```
