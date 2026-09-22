# omi-cli aģentiem

> Praktisks ceļvedis vidēm, kuras vada LLM modeļi (Claude Code, Cursor, jūsu pielāgotie boti).

## Kāpēc CLI ir ērts aģentiem

* **Stabils JSON līgums.** Karodziņš `--json` izvada derīgu JSON dokumentu uz stdout un *tikai* JSON dokumentu — bez progresa ziņojumiem, bez ielādes animācijām. Kļūdas tiek nosūtītas uz stderr formātā `{"error": "...", "detail": "..."}`.
* **Stabili izejas kodi (exit codes).** `0` kārtībā / `1` lietošanas kļūda / `2` autentifikācijas kļūda / `3` servera kļūda / `4` pārsniegts pieprasījumu limits / `5` nav atrasts. Aģenti var pieņemt lēmumus uz šo kodu pamata, neparsējot dabiskās valodas ziņojumus.
* **Nav interaktīvu uzvedņu bezgalvas režīmā (headless).** Destruktīvām komandām padodiet `--yes` (vai `-y`); padodiet `--api-key` vai iestatiet vides mainīgo `OMI_API_KEY`, lai izlaistu interaktīvo pieteikšanos.
* **Iecietīga atkārtošanas uzvedība.** Kļūdu kodi `429` un `5xx` tiek automātiski mēģināti vēlreiz ar eksponenciālu aizturi (backoff) pirms kļūdas parādīšanas.

## Autentifikācija (vienreizēja, veic cilvēks)

Lietotājs iegūst izstrādātāja API atslēgu no Omi tīmekļa lietotnes
(`https://app.omi.me` → Developer → API Keys) un palaiž vienu no šīm komandām:

```bash
omi auth login                          # interaktīva ielīmēšana; atslēga netiek saglabāta čaulas vēsturē
# vai
export OMI_API_KEY=omi_dev_...          # pagaidu, piemērots konteineriem
```

## Piecas darbības, ko aģenti veic visbiežāk

### 1. Atmiņu lasīšana (memories)

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Atmiņas izveide

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Sarunu lasīšana

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Atvērto uzdevumu lasīšana (action items)

```bash
omi action-item list --json --open
```

### 5. Uzdevuma atzīmēšana kā pabeigtu

```bash
omi action-item complete --json a1b2c3d4
```

## Vietējais darbvirsmas API (Local Desktop API)

Kad Omi Desktop iespējo savu vietējo API, aģenti var vaicāt ierīces ekrāna vēsturi, kopsavilkumus, SQL un uzdevumus, neizmantojot mākoņa API:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# vai pagaidu sesijām:
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

Pabeidziet vai dzēsiet uzdevumus tikai tad, kad lietotājs to nepārprotami pieprasa:

```bash
omi --json local task complete task_1
```
