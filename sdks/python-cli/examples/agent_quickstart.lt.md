# omi-cli agentams

> Praktinis vadovas LLM valdomoms aplinkoms (Claude Code, Cursor, jūsų asmeniniai robotai).

## Kodėl CLI yra pritaikyta agentams

* **Stabili JSON sutartis.** Vėliavėlė `--json` į stdout išveda galiojantį JSON dokumentą ir *tik* JSON dokumentą — jokių eigos pranešimų, jokių įkėlimo animacijų. Klaidos siunčiamos į stderr formatu `{"error": "...", "detail": "..."}`.
* **Stabilūs išėjimo kodai (exit codes).** `0` gerai / `1` naudojimo klaida / `2` autentifikavimo klaida / `3` serverio klaida / `4` viršytas užklausų limitas / `5` nerasta. Agentai gali priimti sprendimus pagal šiuos kodus neanalizuodami natūralios kalbos pranešimų.
* **Jokių interaktyvių raginimų foniniu režimu (headless).** Destruktyvioms komandoms perduokite `--yes` (arba `-y`); perduokite `--api-key` arba nustatykite aplinkos kintamąjį `OMI_API_KEY`, kad praleistumėte interaktyvų prisijungimą.
* **Atlaidus kartojimo elgesys.** Klaidų kodai `429` ir `5xx` automatiškai kartojami su eksponentiniu atidėjimu (backoff) prieš pateikiant klaidą.

## Autentifikavimas (vienkartinis, atlieka žmogus)

Vartotojas gauna kūrėjo API raktą iš Omi žiniatinklio programos
(`https://app.omi.me` → Developer → API Keys) ir paleidžia vieną iš šių komandų:

```bash
omi auth login                          # interaktyvus įklijavimas; raktas neišsaugomas apvalkalo istorijoje
# arba
export OMI_API_KEY=omi_dev_...          # laikinas, tinkamas konteineriams
```

## Penki veiksmai, kuriuos agentai atlieka dažniausiai

### 1. Prisiminimų skaitymas (memories)

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Prisiminimo sukūrimas

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Pokalbių skaitymas

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Atvirų užduočių skaitymas (action items)

```bash
omi action-item list --json --open
```

### 5. Užduoties pažymėjimas kaip atliktos

```bash
omi action-item complete --json a1b2c3d4
```

## Vietinis darbalaukio API (Local Desktop API)

Kai Omi Desktop įgalina vietinį API, agentai gali pasiekti įrenginio ekrano istoriją, santraukas, SQL ir užduotis nenaudodami debesies API:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# arba laikinoms sesijoms:
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

Užduotis baikite arba ištrinkite tik tada, kai vartotojas to aiškiai paprašo:

```bash
omi --json local task complete task_1
```
