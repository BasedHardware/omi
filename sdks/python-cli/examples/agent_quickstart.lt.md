# omi-cli AI agentams

> Praktinis vadovas LLM valdomoms sistemoms (Claude Code, Cursor, individualiems botams).

## Kodėl CLI yra patogi agentams

* **Stabilus JSON kontraktas.** Vėliavėlė `--json` išveda galiojantį JSON dokumentą į stdout ir
  *tik* JSON dokumentą — jokių eigos pranešimų, jokių krovimo animacijų. Klaidos siunčiamos
  į stderr formatu `{"error": "...", "detail": "..."}`.
* **Stabilūs išėjimo kodai.** `0` sėkmė / `1` naudojimo klaida / `2` autentifikavimas /
  `3` serverio klaida / `4` viršytas užklausų limitas / `5` nerasta. Agentai gali tiesiogiai
  šakotis pagal šiuos kodus be natūralios kalbos klaidų analizės.
* **Jokių interaktyvių užklausų headless aplinkoje.** Perduokite `--yes` (arba `-y`) destruktyvioms
  komandoms; perduokite `--api-key` arba nustatykite `OMI_API_KEY`, kad praleistumėte
  interaktyvų prisijungimą.
* **Atlaidus pakartotinių bandymų elgesys.** `429` ir `5xx` klaidos automatiškai bandomos iš naujo
  su eksponentiniu delsimu (backoff) prieš pranešant apie jas.

## Autentifikavimas (vienkartinis, atliekamas žmogaus)

Vartotojas gauna kūrėjo API raktą iš Omi žiniatinklio programos
(`https://app.omi.me` → Developer → API Keys) ir atlieka vieną iš šių veiksmų:

```bash
omi auth login                          # interaktyvus įklijavimas; raktas neišsaugomas shell istorijoje
# arba
export OMI_API_KEY=omi_dev_...          # laikinas, tinkamas konteineriams
```

## Penki dažniausi agentų veiksmai

### 1. Prisiminimų skaitymas

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

### 4. Atvirų veiksmų elementų skaitymas

```bash
omi action-item list --json --open
```

### 5. Veiksmo pažymėjimas atliktu

```bash
omi action-item complete --json a1b2c3d4
```

## Vietinė Desktop API

Kai Omi Desktop įgalina savo vietinę API, agentai gali užklausti įrenginio ekrano istoriją,
santraukas, SQL ir užduotis nenaudodami debesijos dev API:

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
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

Komanda `omi local screenshot SCREENSHOT_ID --output PATH` įrašo ekrano kopiją į diską
ir toliau spausdina JSON į stdout scenarijų reikmėms. Ekrano kopijos ID paprastai gaunamas iš
`local search-screen` arba SQL užklausos lentelėje `screenshots`. Jei Desktop grąžina struktūruotą
klaidą, pvz., `screenshot_pending`, `screenshot_file_missing` arba `screenshot_chunk_corrupted`,
JSON režimas išlaiko laukus `reason`, `hint` ir `screenshot_id` stderr sraute, kad agentai galėtų
išbandyti senesnį ID arba pranešti apie tikslią kliūtį. Prieš perduodami išvestis vaizdo įrankiams,
patikrinkite sėkmingus failus naudodami `file PATH`.

## Praktinis pavyzdys: Python agento ciklas

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Invoke the omi CLI in JSON mode, raising on non-success exit codes."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # The CLI prints structured errors to stderr in JSON mode:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Read all open action items and mark anything older than 30 days complete.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Užklausų ribojimų valdymas (Rate Limits)

Prisiminimai: 120/val. Pokalbiai: 25/val. Grupiniai kūrimai: 15/val.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Patarimai

* Naudokite `--profile <name>`, jei jūsų agentas valdo kelias Omi paskyras. Kiekvienas
  profilis turi savo kredencialus ir API bazę.
* Naudokite `--api-base http://localhost:8080` vietiniam backend testavimui.
* Naudokite `OMI_LOCAL_API_URL` ir `OMI_LOCAL_TOKEN`, kad perrašytumėte profilio vietinius
  Desktop API nustatymus vienam paleidimui.
* Naudokite `--verbose` derinimui — fiksuoja `METHOD path → status (Ns)` į stderr
  nedarant įtakos stdout, todėl JSON režimas išlieka galiojantis.
* Norėdami nukreipti turinį į pokalbį, naudokite `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
