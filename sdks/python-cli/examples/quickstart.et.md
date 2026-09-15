# omi-cli — kiirjuhend eesti keeles

> Praktiline juhend Omiga töötamiseks terminalist. Sobib nii inimesele kui ka AI-agendile.

`omi-cli` on [Omi](https://omi.me) arendaja-API ametlik käsurea liides.
See annab kiire ja skriptitava juurdepääsu Omi neljale põhiüksusele:
mälestustele (memories), vestlustele (conversations), tegevustele (action items) ja eesmärkidele (goals).

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Dokumentatsioon:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Lähtekood:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Paigaldamine

Soovitatav viis on `pipx`: see paigaldab tööriista isoleeritud keskkonda,
nii et selle sõltuvused ei lähe teie projektidega konflikti.

```bash
# soovitatav: paigaldus pipx-iga
pipx install omi-cli

# või pip-iga
pip install omi-cli
```

> **Tähtis: paketi nimi ja käsu nimi on erinevad.**
> * Paigaldatakse pakett **`omi-cli`** (eraldi pakett `omi` on teine, mitteseotud projekt).
> * Pärast paigaldust käivitatakse käsk **`omi`**.

Kontrollige, et paigaldus õnnestus:

```bash
omi --version
omi --help
```

---

## 2. Sisselogimine

`omi-cli` toetab kahte sisselogimisviisi.

| Viis | Millal sobib | Käsk |
| :--- | :--- | :--- |
| **Arendajavõti (`omi_dev_*`)** | CI/CD, skriptid, AI-agendid | `omi auth login --api-key ...` või keskkonnamuutuja |
| **Sisselogimine brauseri kaudu (Google/Apple)** | Töö enda arvutis | `omi auth login --browser` |

### Interaktiivne sisselogimine

Ilma lippudeta küsib käsk ise, kuidas soovite sisse logida:

```bash
omi auth login
# 1) Browser — sisselogimine Google'i või Apple'i kaudu (mugav inimesele)
# 2) API key — kleepige arendajavõti lehelt app.omi.me (mugav agentidele ja CI-le)
```

Võtme valimisel varjatakse sisend, nii et võti ei jää terminali ajalukku.

### Otse brauseri kaudu

```bash
omi auth login --browser
```

### Arendajavõtmega

Võtme saate lehelt [app.omi.me](https://app.omi.me) jaotisest **Developer → API Keys**.

```bash
# salvestada võti seadistusse
omi auth login --api-key omi_dev_...

# või edastada keskkonna kaudu — parem CI/CD ja konteinerite jaoks
export OMI_API_KEY=omi_dev_...
```

Muutujat `OMI_API_KEY` kasutatakse siis, kui aktiivsel profiilil pole salvestatud võtit,
seega konteineris ei ole vaja midagi kettale kirjutada. Kui profiilis on võti
juba olemas, läheb see keskkonnamuutujast ette.

### Sisselogimise kontroll

Kaks käsku vastavad erinevatele küsimustele ja neid ei tohiks segi ajada:

* `omi auth status` — mis on salvestatud **lokaalselt**: profiil, varjatud võti, kehtivus.
  Töötab ilma võrguta.
* `omi auth whoami` — päring **Omi serverisse**: kontrollib, et võti tõeliselt
  vastu võetakse. Vajab võrku.

```bash
omi auth status    # kohalik kontroll, võrguühenduseta
omi auth whoami    # kontroll serveris
```

Aegumais oleva OAuth-seansi värskendamine ilma uuesti sisse logimata — kehtib ainult brauseri kaudu sisselogimisel (OAuth). `omi_dev_*` võtmete puhul see käsk ei värskenda; vahetage võti veebirakenduses `Developer → API Keys` all:

```bash
omi auth refresh
```

Väljalogimine:

```bash
omi auth logout
```

---

## 3. Põhikäsud

### Mälestused (memories)

Faktid ja teadmised, mis süsteem teie kohta meelde jätnud on.

```bash
# mälestuste loend
omi memory list

# luua uus
omi memory create "Kasutaja eelistab tumedat teemat" --category lifestyle

# vaadata konkreetset
omi memory get <MEMORY_ID>
```

### Vestlused (conversations)

Kõne- ja tekstiajalugu seadmest või rakendusest.

```bash
# viimased 5 vestlust
omi conversation list --limit 5

# kogu vestlus koos transkriptsiooniga
omi conversation get <CONVERSATION_ID> --include-transcript
```

### Tegevused (action items)

Tegevused, mille Omi vestlustest välja tõmbas.

```bash
# ainult tegemata
omi action-item list --open

# märkida tehtuks
omi action-item complete <ACTION_ITEM_ID>
```

### Eesmärgid (goals)

```bash
# eesmärkide loend
omi goal list

# kirjutada uus edenemisväärtus (vaja on MÕLEMAT argumenti: eesmärk ja väärtus)
omi goal progress <GOAL_ID> 25

# muudatuste ajalugu
omi goal history <GOAL_ID>
```

---

## Küsimus omade sõnadega (`ask`)

Eraldi kõrgeima taseme käsk: esitab küsimuse loomulikus keeles,
vastus koostatakse teie enda vestluste põhjal.

```bash
omi ask "mida ma kolimise osas otsustasin"
omi --json ask "millised tegevused ma lubasin sel nädalal lõpetada"
```

---

## 4. JSON ja skriptid (`--json`)

`omi-cli` oskab tagastada masinloetavat JSON-it. Lipp `--json` on **globaalne**,
seega pannakse see **enne** alamkäsku.

```bash
# mälestused: võtta id, tekst ja kategooria
omi --json memory list | jq '.[] | {id, content, category}'

# viimaste vestluste pealkirjad
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# tegemata tegevused
omi --json action-item list --open | jq '.'
```

> **Sage viga.** `--json` käib enne alamkäsku, mitte pärast seda.
> * Õigesti: `omi --json memory list`
> * Valesti: `omi memory list --json`

Režiimis `--json` ei lähe standardsesse väljundisse midagi peale JSON-i enda —
sellele võib skriptides tugineda.

---

## 5. Väljundkoodid

Koodid on stabiilsed, seega saab nende järgi skriptides ja CI-s loogikat harutada.

| Kood | Tähendus | Millal tekib |
| :---: | :--- | :--- |
| `0` | Õnnestus | Käsk lõppes |
| `1` | Väljakutse viga | omi-cli enda kontroll (nt `--browser` ja `--api-key` korraga, kehtetu valik, tühi sisend) |
| `2` | Ligipääsu- või argumentide viga | Sisse pole logitud, võti on vale või aegunud — samuti parseri vead (tundmatu lipp, puuduv argument) |
| `3` | Serveri viga | Vastus 5xx, timeout, ühendust pole |
| `4` | Liiga palju päringuid | 429 Too Many Requests |
| `5` | Ei leitud | 404, määratud identifikaatorit pole olemas |

Kontrolli näide Bashis:

```bash
if omi --json auth whoami > /dev/null 2>&1; then
  echo "võti töötab"
else
  code=$?
  [ "$code" -eq 2 ] && echo "vaja on uuesti sisse logida"
  [ "$code" -eq 3 ] && echo "server ei ole kättesaadav, proovige hiljem"
fi
```

---

## 6. Keskkonnamuutujad

### Bash / Zsh (Linux, macOS)

```bash
export OMI_API_KEY="omi_dev_teie_voti"

omi --json memory list --limit 10
```

Et võti uutes seanssides kätte saadaks, lisage rida faili `~/.bashrc` või `~/.zshrc`.

### PowerShell (Windows)

```powershell
$env:OMI_API_KEY = "omi_dev_teie_voti"

# JSON-i töötlus PowerShelliga
(omi --json memory list | ConvertFrom-Json) | Select-Object id, content
```

Püsiv seadistus:

```powershell
[Environment]::SetEnvironmentVariable("OMI_API_KEY", "omi_dev_teie_voti", "User")
```

---

## 7. Kohalik Omi Desktop rakendus

Kui Omi töölauarakendus töötab, on osa andmeid kättesaadav otse,
pilvest mööda minnes.

```bash
# määrata kohaliku API aadress
omi local configure --url http://127.0.0.1:47778 --token TEIE_TOKEN

# kontrollida, et see vastab
omi --json local status

# otsida ekraaniajaloost
omi --json local search-screen "tariifid" --days 7 --app Safari

# ekraanipilt identifikaatori järgi
omi --json local screenshot 123 --output /tmp/omi-shot.jpg

# suvaline SQL päring kohalikust andmebaasist
omi --json local sql "SELECT appName, COUNT(*) FROM screenshots GROUP BY appName"
```

Tööjärjekord: kõigepealt `local status`, siis `local tools` — et teada saada
saadaolevad tööriistad ja nende parameetrid — ja alles seejärel väljakutsed.

---

## 8. Profiilid

Kui kontosid või keskkondi on mitu, jagage need profiilideks.
Seaded hoitakse failis `~/.omi/config.toml`.

```bash
# sisselogimine isiklikku profiili
omi --profile personal auth login

# sisselogimine tööprofiili
omi --profile work auth login

# käsu käivitamine konkreetses profiilis
omi --profile work memory list
```

Kui profiili ei määrata, kasutab CLI esmalt keskkonnamuutuja `OMI_PROFILE` profiili, seejärel konfiguratsioonifaili aktiivset profiili, lõpuks `default`. Eelistusjärjekord: `--profile` → `OMI_PROFILE` → aktiivne profiil `~/.omi/config.toml`-is → `default`.

Vaadata ja muuta ennast konfiguratsiooni:

```bash
# mis on praegu seadistatud
omi config show

# kus asub konfiguratsioonifail
omi config path

# muuta väärtust
omi config set api_base https://api.omi.me
```

---

## 9. Edasi

* [`agent_quickstart.md`](./agent_quickstart.md) — kuidas ühendada `omi-cli` AI-agendiga.
* [`shell_examples.sh`](./shell_examples.sh) — valmis shell-näited.
* [Omi dokumentatsioon](https://docs.omi.me/doc/developer/cli/introduction) — täielik käskude viide.
