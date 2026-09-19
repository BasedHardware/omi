# omi-cli agentams

> Praktinis vadovas LLM valdomiems įrankiams (Claude Code, Cursor, jūsų botams).

## Kodėl ši CLI sąsaja yra patogi agentams

* **Stabilus JSON kontraktas.** Parametras `--json` išveda galiojantį JSON dokumentą į stdout ir
  *tik* JSON dokumentą — jokių eigos pranešimų ar animacijų. Klaidos išvedamos į
  stderr formatu `{"error": "...", "detail": "..."}`.
* **Stabilūs išėjimo kodai.** `0` sėkminga / `1` naudojimo klaida / `2` autentifikavimas / `3` serverio klaida / `4` užklausų ribojimas / `5` nerasta. Agentai gali atlikti logikos šakojimą pagal šiuos kodus be būtinybės analizuoti natūralios kalbos klaidas.
* **Jokių interaktyvių užklausų automatiniame režime.** Naudokite `--yes` (arba `-y`)
  destruktyvioms komandoms; naudokite `--api-key` arba nustatykite `OMI_API_KEY`, kad praleistumėte interaktyvų prisijungimą.
* **Atlaidus pakartotinių bandymų elgesys.** Klaidų `429` ir `5xx` atveju atliekami pakartotiniai
  bandymai su delsos intervalu prieš pateikiant klaidą.

## Autentifikavimas (vienkartinis, atliekamas žmogaus)

Vartotojas gauna kūrėjo API raktą Omi internetinėje programėlėje
(`https://app.omi.me` → Developer → API Keys) ir atlieka vieną iš šių veiksmų:

```bash
omi auth login                          # interaktyvus įklijavimas; raktas neišsaugomas komandų istorijoje
# arba
export OMI_API_KEY=omi_dev_...          # laikinas, tinkamas konteineriams
```

## Penki veiksmai, kuriuos agentai atlieka dažniausiai

### 1. Skaityti prisiminimus

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Sukurti prisiminimą

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Skaityti pokalbius

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Skaityti atidarytas užduotis

```bash
omi action-item list --json --open
```

### 5. Pažymėti užduotį kaip atliktą

```bash
omi action-item complete --json a1b2c3d4
```

## Vietinė Darbalaukio API (Desktop API)

Kai Omi Desktop pateikia vietinę API, agentai gali atlikti užklausas į įrenginio ekrano istoriją,
santraukas, SQL ir užduotis nenaudodami debesijos API:

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

Užduotis užbaikite arba ištrinkite tik tada, kai vartotojas to aiškiai paprašo:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

Komanda `omi local screenshot SCREENSHOT_ID --output PATH` įrašo ekrano kopiją į
diską ir toliau pateikia JSON į stdout skriptams. Ekrano kopijos ID paprastai gaunamas
iš komandos `local search-screen` arba SQL užklausos lentelėje `screenshots`. Jei Desktop
grąžina struktūrizuotą klaidą, pavyzdžiui, `screenshot_pending`, `screenshot_file_missing`
arba `screenshot_chunk_corrupted`, JSON režimas išsaugo laukus `reason`, `hint` ir
`screenshot_id` stderr sraute, kad agentai galėtų bandyti su senesniu ID arba pranešti
apie tikslią kliūtį. Patvirtinkite sėkmingus išvesties failus naudodami `file PATH` prieš perduodami juos vizualiniams įrankiams.

## Išsamus pavyzdys: Python agento ciklas

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Iškviečia omi CLI JSON režimu, sukeldamas išimtį esant klaidų kodams."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI išveda struktūrizuotas klaidas į stderr JSON režimu:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Nuskaito visas atidarytas užduotis ir pažymi senesnes nei 30 dienų kaip atliktas.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Užklausų ribojimų valdymas (rate limits)

Prisiminimai: 120/val. Pokalbiai: 25/val. Masinis kūrimas: 15/val.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # pasiektas užklausų limitas
    err = json.loads(result.stderr)
    # err["detail"] atrodo taip: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Patarimai

* Naudokite `--profile <pavadinimas>`, jei jūsų agentas valdo kelias Omi paskyras. Kiekvienas
  profilis turi atskirus prisijungimo duomenis ir API adresą.
* Vietinio serverio testavimui naudokite `--api-base http://localhost:8080`.
* Naudokite kintamuosius `OMI_LOCAL_API_URL` ir `OMI_LOCAL_TOKEN`, kad perrašytumėte profilio vietinius
  Desktop API nustatymus vienam paleidimui.
* Derinimui naudokite `--verbose` — įrašo `METHOD path → status (Ns)` į stderr
  nedarant įtakos stdout srautui, todėl JSON režimas išlieka galiojantis.
* Norėdami nukreipti turinį į pokalbį per kanalą (pipe), naudokite `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
