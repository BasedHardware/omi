# omi-cli — sparti pradžia lietuvių kalba

> Praktinis vadovas darbui su Omi iš terminalo. Tinka ir žmogui, ir AI agentui.

`omi-cli` yra oficiali komandinės eilutės sąsaja [Omi](https://omi.me) kūrėjų API.
Ji suteikia greitą ir tinkamą scenarijams prieigą prie keturių pagrindinių Omi esybių:
prisiminimų (memories), pokalbių (conversations), užduočių (action items) ir tikslų (goals).

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Dokumentacija:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Išeities kodas:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Diegimas

Rekomenduojamas būdas — `pipx`: jis įdiegia įrankį izoliuotoje aplinkoje,
todėl jo priklausomybės nekonfliktuoja su jūsų projektais.

```bash
# rekomenduojama: diegimas per pipx
pipx install omi-cli

# arba per pip
pip install omi-cli
```

> **Svarbu: paketo pavadinimas ir komandos pavadinimas skiriasi.**
> * Diegiamas paketas **`omi-cli`** (atskirasis paketas `omi` yra kitas, nesusijęs projektas).
> * Įdiegus paleidžiama komanda **`omi`**.

Patikrinkite, ar diegimas pavyko:

```bash
omi --version
omi --help
```

---

## 2. Prisijungimas

`omi-cli` palaiko du prisijungimo būdus.

| Būdas | Kada tinka | Komanda |
| :--- | :--- | :--- |
| **Kūrėjo raktas (`omi_dev_*`)** | CI/CD, scenarijai, AI agentai | `omi auth login --api-key ...` arba aplinkos kintamasis |
| **Prisijungimas per naršyklę (Google/Apple)** | Darbas prie savo kompiuterio | `omi auth login --browser` |

### Interaktyvus prisijungimas

Be jokių vėliavėlių komanda pati paklaus, kuriuo būdu norite jungtis:

```bash
omi auth login
# 1) Browser — prisijungimas per Google arba Apple (patogu žmogui)
# 2) API key — įklijuoti kūrėjo raktą iš app.omi.me (patogu agentams ir CI)
```

Pasirinkus raktą, įvestis maskuojama, todėl raktas nepasilieka terminalo istorijoje.

### Iš karto per naršyklę

```bash
omi auth login --browser
```

### Kūrėjo raktu

Raktas gaunamas [app.omi.me](https://app.omi.me) skiltyje **Developer → API Keys**.

```bash
# išsaugoti raktą konfigūracijoje
omi auth login --api-key omi_dev_...

# arba perduoti per aplinką — geriau tinka CI/CD ir konteineriams
export OMI_API_KEY=omi_dev_...
```

Kintamasis `OMI_API_KEY` naudojamas, kai aktyviame profile raktas neišsaugotas,
todėl konteineryje nieko nereikia rašyti į diską. Jei raktas profile jau
yra, jis turi pirmenybę prieš aplinkos kintamąjį.

### Prisijungimo patikra

Dvi komandos atsako į skirtingus klausimus, jų painioti nereikėtų:

* `omi auth status` — kas išsaugota **lokaliai**: profilis, maskuotas raktas, galiojimas.
  Veikia be tinklo.
* `omi auth whoami` — užklausa **į Omi serverį**: tikrina, ar serveris iš tiesų
  priima raktą. Reikia tinklo.

```bash
omi auth status    # vietinė patikra, neprisijungus
omi auth whoami    # patikra serveryje
```

Atnaujinkite baigiančią galioti OAuth sesiją be pakartotinio prisijungimo — taikoma tik prisijungimui naršyklėje (OAuth). `omi_dev_*` raktams ši komanda nieko neatnaujina; raktą pakeiskite žiniatinklio programoje skiltyje `Developer → API Keys`:

```bash
omi auth refresh
```

Atsijungimas:

```bash
omi auth logout
```

---

## 3. Pagrindinės komandos

### Prisiminimai (memories)

Faktai ir žinios, kurias sistema apie jus įsiminė.

```bash
# prisiminimų sąrašas
omi memory list

# sukurti naują
omi memory create "Vartotojas teikia pirmenybę tamsiai temai" --category lifestyle

# peržiūrėti konkretų
omi memory get <MEMORY_ID>
```

### Pokalbiai (conversations)

Kalbos ir teksto istorija iš įrenginio arba programos.

```bash
# paskutiniai 5 pokalbiai
omi conversation list --limit 5

# visas pokalbis su transkripcija
omi conversation get <CONVERSATION_ID> --include-transcript
```

### Užduotys (action items)

Darbai, kuriuos Omi išskyrė iš pokalbių.

```bash
# tik neatliktos
omi action-item list --open

# pažymėti atlikta
omi action-item complete <ACTION_ITEM_ID>
```

### Tikslai (goals)

```bash
# tikslų sąrašas
omi goal list

# įrašyti naują pažangos reikšmę (reikia ABIEJŲ argumentų: tikslo ir reikšmės)
omi goal progress <GOAL_ID> 25

# pakeitimų istorija
omi goal history <GOAL_ID>
```

---

## Klausimas savo žodžiais (`ask`)

Atskira aukščiausio lygio komanda: užduoda klausimą natūralia kalba,
atsakymas konstruojamas iš jūsų pačių pokalbių.

```bash
omi ask "ką aš nusprendžiau dėl persikraustymo"
omi --json ask "kokias užduotis pažadėjau užbaigti šią savaitę"
```

---

## 4. JSON ir scenarijai (`--json`)

`omi-cli` moka grąžinti mašininiu būdu skaitomą JSON. Vėliavėlė `--json` yra **globali**,
todėl rašoma **prieš** subkomandą.

```bash
# prisiminimai: ištraukti id, tekstą ir kategoriją
omi --json memory list | jq '.[] | {id, content, category}'

# paskutinių pokalbių antraštės
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# neatliktos užduotys
omi --json action-item list --open | jq '.'
```

> **Dažna klaida.** `--json` rašomas prieš subkomandą, o ne po jos.
> * Teisingai: `omi --json memory list`
> * Neteisingai: `omi memory list --json`

Režime `--json` į standartinę išvestį nepateikia nieko, išskyrus patį JSON, —
tuo galima remtis scenarijuose.

---

## 5. Išėjimo kodai

Kodai stabilūs, todėl pagal juos galima šakoti logiką scenarijuose ir CI.

| Kodas | Reikšmė | Kada pasitaiko |
| :---: | :--- | :--- |
| `0` | Sėkmė | Komanda įvykdyta |
| `1` | Iškvietimo klaida | Paties omi-cli tikrinimas (pvz., `--browser` ir `--api-key` kartu, neteisingas pasirinkimas, tuščia įvestis) |
| `2` | Prieigos arba argumentų klaida | Neprisijungta, raktas neteisingas arba nebegalioja — taip pat analizatoriaus klaidos (nežinoma vėliavėlė, trūkstamas argumentas) |
| `3` | Serverio klaida | Atsakymas 5xx, timeout, nėra ryšio |
| `4` | Per daug užklausų | 429 Too Many Requests |
| `5` | Nerasta | 404, nurodytas identifikatorius neegzistuoja |

Patikros pavyzdys Bash'e:

```bash
if omi --json auth whoami > /dev/null 2>&1; then
  echo "raktas veikia"
else
  code=$?
  [ "$code" -eq 2 ] && echo "reikia prisijungti iš naujo"
  [ "$code" -eq 3 ] && echo "serveris nepasiekiamas, pakartokite vėliau"
fi
```

---

## 6. Aplinkos kintamieji

### Bash / Zsh (Linux, macOS)

```bash
export OMI_API_KEY="omi_dev_jusu_raktas"

omi --json memory list --limit 10
```

Kad raktas būtų užkraunamas naujose sesijose, pridėkite eilutę į `~/.bashrc` arba `~/.zshrc`.

### PowerShell (Windows)

```powershell
$env:OMI_API_KEY = "omi_dev_jusu_raktas"

# JSON analizė su PowerShell
(omi --json memory list | ConvertFrom-Json) | Select-Object id, content
```

Nuolatinis nustatymas:

```powershell
[Environment]::SetEnvironmentVariable("OMI_API_KEY", "omi_dev_jusu_raktas", "User")
```

---

## 7. Vietinė Omi Desktop programėlė

Jei paleista darbalaukio Omi programa, dalis duomenų pasiekiama tiesiogiai,
aplenkiant debesį.

```bash
# nurodyti vietinio API adresą
omi local configure --url http://127.0.0.1:47778 --token JUSU_TOKENAS

# patikrinti, ar ji atsako
omi --json local status

# paieška ekrano istorijoje
omi --json local search-screen "tarifai" --days 7 --app Safari

# ekrano kopija pagal identifikatorių
omi --json local screenshot 123 --output /tmp/omi-shot.jpg

# savavališka SQL užklausa vietinėje bazėje
omi --json local sql "SELECT appName, COUNT(*) FROM screenshots GROUP BY appName"
```

Darbo eiga: pirmiausia `local status`, tada `local tools` — kad sužinotumėte
pasiekiamus įrankius ir jų parametrus — ir tik tada iškvietimai.

---

## 8. Profiliai

Jei turite kelias paskyras ar aplinkas, išskirkite jas profiliais.
Nustatymai saugomi `~/.omi/config.toml`.

```bash
# prisijungti prie asmeninio profilio
omi --profile personal auth login

# prisijungti prie darbinio
omi --profile work auth login

# vykdyti komandą konkrečiame profile
omi --profile work memory list
```

Jei profilio nenurodote, CLI pirmiausia naudoja profilį iš aplinkos kintamojo `OMI_PROFILE`, tada aktyvų profilį iš konfigūracijos failo, galiausiai `default`. Prioritetų tvarka: `--profile` → `OMI_PROFILE` → aktyvus profilis `~/.omi/config.toml` → `default`.

Peržiūrėti ir keisti pačią konfigūraciją:

```bash
# kas dabar sukonfigūruota
omi config show

# kur guli konfigūracijos failas
omi config path

# pakeisti reikšmę
omi config set api_base https://api.omi.me
```

---

## 9. Kas toliau

* [`agent_quickstart.md`](./agent_quickstart.md) — kaip prijungti `omi-cli` prie AI agento.
* [`shell_examples.sh`](./shell_examples.sh) — paruošti shell pavyzdžiai.
* [Omi dokumentacija](https://docs.omi.me/doc/developer/cli/introduction) — pilnas komandų žinynas.
