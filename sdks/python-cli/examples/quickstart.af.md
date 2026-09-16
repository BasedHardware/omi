# omi-cli — Afrikaanse vinnige-begin-gids

> Praktiese gids om met Omi vanuit die terminaal te werk. Geskik vir beide mense en KI-agente.

`omi-cli` is die amptelike opdragreël-kliënt vir die [Omi](https://omi.me) ontwikkelaars-API.
Dit bied vinnige, skripvriendelike toegang tot Omi se vier kernentiteite:
herinneringe, gesprekke, aksie-items en doelwitte.

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Dokumentasie:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Bronkode:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Installasie

Die aanbevole metode is `pipx`: dit installeer die nut in 'n geïsoleerde omgewing,
sodat sy afhanklikhede nie met jou projekte bots nie.

```bash
# aanbeveel: installasie via pipx
pipx install omi-cli

# of via pip
pip install omi-cli
```

> **Belangrik: die pakketnaam en die opdragmaam verskil.**
> * Die pakket wat geïnstalleer word is **`omi-cli`** (die aparte `omi`-pakket is 'n ander, onverwante projek).
> * Na installasie voer jy die opdrag **`omi`** uit.

Maak seker alles werk:

```bash
omi --version
omi --help
```

---

## 2. Verifikasie

`omi-cli` ondersteun twee maniere om aan te meld.

| Metode | Geskik vir | Opdrag |
| :--- | :--- | :--- |
| **Ontwikkelaarsleutel (`omi_dev_*`)** | CI/CD, skripte, KI-agente | `omi auth login --api-key ...` of omgewingsveranderlike |
| **Blaaier-aanmelding (Google/Apple)** | Werk op jou eie rekenaar | `omi auth login --browser` |

### Interaktiewe aanmelding

Sonder vlae vra die opdrag self watter metode jy wil gebruik:

```bash
omi auth login
# 1) Browser — meld aan met Google of Apple (gerieflik vir mense)
# 2) API key — plak 'n ontwikkelaarsleutel vanaf app.omi.me (gerieflik vir agente en CI)
```

As jy die sleutel kies, word die invoer versteek sodat die sleutel nie in die terminaalgeskiedenis agterbly nie.

### Direk via die blaaier

```bash
omi auth login --browser
```

### Via ontwikkelaarsleutel

Die sleutel word verkry op [app.omi.me](https://app.omi.me) onder **Developer → API Keys**.

```bash
# stoor die sleutel in die konfigurasie
omi auth login --api-key omi_dev_...

# of gee dit via die omgewing deur — verkieslik vir CI/CD en houers
export OMI_API_KEY=omi_dev_...
```

Die omgewingsveranderlike `OMI_API_KEY` word gebruik wanneer daar geen sleutel in die aktiewe profiel gestoor is nie,
so in 'n houer hoef niks na die skyf geskryf te word nie. As die profiel reeds 'n sleutel het,
geniet dit voorrang bo die omgewingsveranderlike.

### Kontroleer aanmelding

Twee opdragte beantwoord verskillende vrae en moet nie verwar word nie:

* `omi auth status` — wat **plaaslik** gestoor is: profiel, gemaskerde sleutel, vervaldatum.
  Werk sonder netwerk.
* `omi auth whoami` — navraag **aan die Omi-bediener**: kontroleer dat die sleutel werklik
  aanvaar word. Vereis netwerk.

```bash
omi auth status    # plaaslike kontrole, vanlyn
omi auth whoami    # kontrole op die bediener
```

Verfris 'n OAuth-sessie wat besig is om te verval sonder om weer aan te meld — geld slegs vir blaaier-aanmelding (OAuth). Vir `omi_dev_*`-sleutels voer hierdie opdrag geen verfrissing uit nie; vervang die sleutel in die webtoepassing onder `Developer → API Keys`:

```bash
omi auth refresh
```

Meld af:

```bash
omi auth logout
```

---

## 3. Basiese opdragte

### Herinneringe (memories)

Feite en kennis wat die stelsel van jou onthou.

```bash
# lys van herinneringe
omi memory list

# skep 'n nuwe een
omi memory create "Die gebruiker verkies donker tema" --category lifestyle

# bekyk 'n spesifieke een
omi memory get <MEMORY_ID>
```

### Gesprekke (conversations)

Spraak- en teksgeskiedenis vanaf die toestel of die toepassing.

```bash
# die jongste 5 gesprekke
omi conversation list --limit 5

# 'n hele gesprek met transkripsie
omi conversation get <CONVERSATION_ID> --include-transcript
```

### Aksie-items (action items)

Take wat Omi uit gesprekke afgelei het.

```bash
# slegs oop items
omi action-item list --open

# merk as voltooi
omi action-item complete <ACTION_ITEM_ID>
```

### Doelwitte (goals)

```bash
# lys van doelwitte
omi goal list

# registreer 'n nuwe vorderingswaarde (vereis ALBEI argumente: doelwit en waarde)
omi goal progress <GOAL_ID> 25

# veranderingsgeskiedenis
omi goal history <GOAL_ID>
```

---

## Vra vrae in jou eie woorde (`ask`)

'n Aparte toppvlak-opdrag: stel 'n vraag in natuurlike taal,
en die antwoord word uit jou eie gesprekke gebou.

```bash
omi ask "wat het ek oor die verhuising besluit"
omi --json ask "watter take het ek belowe om hierdie week af te handel"
```

---

## 4. JSON en skripte (`--json`)

`omi-cli` kan masjienleesbare JSON lewer. Die vlag `--json` is **globaal**
en word dus **voor** die subopdrag geplaas.

```bash
# herinneringe: onttrek id, teks en kategorie
omi --json memory list | jq '.[] | {id, content, category}'

# titels van die jongste gesprekke
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# oop aksie-items
omi --json action-item list --open | jq '.'
```

> **Algemene fout.** `--json` kom voor die subopdrag, nie daarna nie.
> * Reg: `omi --json memory list`
> * Verkeerd: `omi memory list --json`

In `--json`-modus word niks anders as die JSON self na stdout geskryf nie —
skripte kan daarop staatmaak.

---

## 5. Afsluitkodes

Die kodes is stabiel, sodat logika in skripte en CI daarop kan vertak.

| Kode | Betekenis | Wanneer |
| :---: | :--- | :--- |
| `0` | Sukses | Die opdrag is uitgevoer |
| `1` | Oproepfout | omi-cli se eie validering (bv. beide `--browser` en `--api-key` gelyk, ongeldige aanmeldkeuse, leë stdin) |
| `2` | Toegangs- of argumentfout | Nie aangemeld nie, ongeldige of vervalle sleutel — asook ontlederfoute (onbekende vlag, ontbrekende argument) |
| `3` | Bedienerfout | 5xx-antwoord, time-out, geen verbinding |
| `4` | Te veel versoeke | 429 Too Many Requests |
| `5` | Nie gevind nie | 404, id bestaan nie |

Voorbeeld van 'n kontrole in Bash:

```bash
if omi --json auth whoami > /dev/null 2>&1; then
  echo "die sleutel werk"
else
  code=$?
  [ "$code" -eq 2 ] && echo "meld weer aan"
  [ "$code" -eq 3 ] && echo "die bediener is onbeskikbaar, probeer later weer"
fi
```

---

## 6. Omgewingsveranderlikes

### Bash / Zsh (Linux, macOS)

```bash
export OMI_API_KEY="omi_dev_jou_sleutel"

omi --json memory list --limit 10
```

Om die sleutel in nuwe sessies te laai, voeg die reel by `~/.bashrc` of `~/.zshrc`.

### PowerShell (Windows)

```powershell
$env:OMI_API_KEY = "omi_dev_jou_sleutel"

# JSON-ontleding met PowerShell
(omi --json memory list | ConvertFrom-Json) | Select-Object id, content
```

Vir permanente opstelling:

```powershell
[Environment]::SetEnvironmentVariable("OMI_API_KEY", "omi_dev_jou_sleutel", "User")
```

---

## 7. Die Omi Desktop-toepassing plaaslik

As die Omi-leskermtoepassing loop, is 'n deel van die data direk beskikbaar,
sonder om die wolk te gebruik.

```bash
# spesifiseer die adres van die plaaslike API
omi local configure --url http://127.0.0.1:47778 --token JOU_TOKEN

# kontroleer dat dit antwoord
omi --json local status

# soektog in die skermgeskiedenis
omi --json local search-screen "pryse" --days 7 --app Safari

# skermfoto volgens id
omi --json local screenshot 123 --output /tmp/omi-shot.jpg

# enige SQL teen die plaaslike databasis
omi --json local sql "SELECT appName, COUNT(*) FROM screenshots GROUP BY appName"
```

Werkvloei: eers `local status`, dan `local tools` — om beskikbare
nutsprogramme en hul parameters te sien, en eers daarna oproepe.

---

## 8. Profiele

As jy meer as een rekening of omgewing het, skei hulle met profiele.
Die instellings word in `~/.omi/config.toml` gestoor.

```bash
# aanmelding by persoonlike profiel
omi --profile personal auth login

# aanmelding by werkprofiel
omi --profile work auth login

# voer 'n opdrag in 'n spesifieke profiel uit
omi --profile work memory list
```

As jy geen profiel spesifiseer nie, gebruik die CLI eers die waarde van die `OMI_PROFILE`-omgewingsveranderlike, dan die aktiewe profiel uit die konfigurasielêer, dan `default`. Voorrangsvolgorde: `--profile`, dan `OMI_PROFILE`, dan die aktiewe profiel in `~/.omi/config.toml`, dan `default`.

Bekyk en wysig die konfigurasie self:

```bash
# wat is tans gekonfigureer
omi config show

# waar die konfigurasielêer lê
omi config path

# verander 'n waarde
omi config set api_base https://api.omi.me
```

---

## 9. Volgende stappe

* [`agent_quickstart.md`](./agent_quickstart.md) — hoe om `omi-cli` aan 'n KI-agent te koppel.
* [`shell_examples.sh`](./shell_examples.sh) — kant-en-klare voorbeelde vir die shell.
* [Omi-dokumentasie](https://docs.omi.me/doc/developer/cli/introduction) — die volledige opdragverwysing.
