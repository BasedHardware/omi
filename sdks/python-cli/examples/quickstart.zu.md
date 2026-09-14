# omi-cli — Umhlahlandlela Wokuqala Ngokushesha NgesiZulu (Zulu Quickstart)

> Umhlahlandlela osebenzayo wokusebenza ne-Omi kusuka kutheminali. Ulungele abantu kanye nama-agent e-AI.

I-`omi-cli` iyi-client esemthethweni ye-command-line interface (CLI) ye-developer API yakwa-[Omi](https://omi.me). Inikeza ukufinyelela okusheshayo nokulungele izikripthi ezinhlotsheni ezine eziyinhloko: izinkumbulo (memories), izingxoxo (conversations), izinto okufanele zenziwe (action items), kanye nezinjongo (goals).

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Amadokhumenti Asemthethweni:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Ikhodi Yomthombo (Source Code):** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Ukufaka (Installation)

Indlela enconywayo ukusebenzisa i-`pipx`: ifaka ithuluzi endaweni ehlukile ukuze amaphakethe alo angangqubuzani namaphrojekthi akho:

```bash
# Indlela enconywayo: ukufaka nge-pipx
pipx install omi-cli

# Noma usebenzisa i-pip
pip install omi-cli
```

> **Okubalulekile: Igama lephakethe negama lomyalo ahlukile.**
> * Iphakethe elifakwayo lithi **`omi-cli`** (iphakethe elihlukile elithi `omi` liyiphrojekthi ehlukile engahlobene nalena).
> * Ngemuva kokufaka, usebenzisa umyalo othi **`omi`**.

Qinisekisa ukuthi yonke into isebenza kahle:

```bash
omi --version
omi --help
```

---

## 2. Ukuqinisekisa Nokungena (Authentication)

I-`omi-cli` isekela izindlela ezimbili zokungena:

| Indlela | Ilungele | Umyalo |
| :--- | :--- | :--- |
| **Ukhiye Wonjiniyela (`omi_dev_*`)** | I-CI/CD, izikripthi, ama-agent e-AI | `omi auth login --api-key ...` noma okuguquguqukayo kwendawo |
| **Ukungena Nge-Browser (Google/Apple)** | Ukusebenza kukhompyutha yakho | `omi auth login --browser` |

### Ukungena Ngokuxoxa (Interactive login)

Uma usebenzisa umyalo ngaphandle kwamafulegi, ukubuza ukuthi iyiphi indlela oyikhethayo:

```bash
omi auth login
# 1) Browser — ngena nge-Google noma i-Apple (kulula kubantu)
# 2) API key — faka ukhiye wonjiniyela owuthola ku-app.omi.me (kulula kuma-agent ne-CI)
```

Uma ukhetha ukhiye we-API, okufakwayo kuyafihlwa ukuze ukhiye wakho ungaveli emlandweni wetheminali.

### Ngena ngqo nge-browser

```bash
omi auth login --browser
```

Nge-Apple:

```bash
omi auth login --browser --provider apple
```

### Ngena ngokhiye wonjiniyela (API key)

Ukhiye utholakala ku-[app.omi.me](https://app.omi.me) ngaphansi kwe-**Developer → API Keys**.

```bash
# Londoloza ukhiye ekucushweni kwasendaweni
omi auth login --api-key "omi_dev_ukhiye_wakho_lapha"

# Noma udlulise njengokuguquguqukayo kwendawo — kunconywa kakhulu ku-CI/CD nakuma-container
export OMI_API_KEY="omi_dev_ukhiye_wakho_lapha"
```

I-variable yendawo ethi `OMI_API_KEY` isetshenziswa lapho kungekho khiye olondolozwe kuphrofayela esebenzayo, okusho ukuthi kuma-container akukho okudinga ukubhalwa kudiski.

### Ukuhlola isimo sokungena

Imiyalo emibili iphendula imibuzo ehlukene, futhi akufanele ididaniswe:

* `omi auth status` — ihlola okukhona **endaweni yakho (offline)**: iphrofayela, ukhiye ofihliwe, nosuku lokuphelelwa yisikhathi. Ayidingi i-inthanethi.
* `omi auth whoami` — ixhuma **kuseva yakwa-Omi**: iqinisekisa ukuthi ukhiye uyamukeleka ngempela. Idinga i-inthanethi.

```bash
omi auth status    # Ukuhlola kwasendaweni, akukho-inthanethi
omi auth whoami    # Ukuhlola kuseva
```

Ukuvuselela ithokheni eliphelelwa yisikhathi ngaphandle kokungena kabusha (kusebenza kuphela ngokungena nge-browser):

```bash
omi auth refresh
```

Phuma:

```bash
omi auth logout
```

---

## 3. Imiyalo Eyisisekelo

### Izinkumbulo (Memories)

Amaqiniso nolwazi uhlelo olukukhumbule ngawe:

```bash
# Uhlu lwezinkumbulo
omi memory list

# Dala inkumbulo entsha
omi memory create "Umsebenzisi ukhetha itimu emnyama (dark theme)" --category lifestyle

# Buka inkumbulo ethile
omi memory get <MEMORY_ID>
```

### Izingxoxo (Conversations)

Umlando wezwi nombhalo ovela kudivayisi noma ku-app:

```bash
# Izingxoxo ezingu-5 zakamuva
omi conversation list --limit 5

# Ingxoxo ephelele enombhalo wokulotshiweyo (transcript)
omi conversation get <CONVERSATION_ID> --include-transcript
```

### Izinto Okufanele Zenziwe (Action Items)

Imisebenzi nemithwalo i-Omi eyithole ezingxoxweni:

```bash
# Ezingakaqedwa kuphela
omi action-item list --open

# Phawula njengeqediwe
omi action-item complete <ACTION_ITEM_ID>
```

### Izinjongo (Goals)

Izinhlelo nezinjongo zesikhathi eside:

```bash
# Uhlu lwezinjongo
omi goal list

# Qopha intuthuko yenjongo (kudinga zombili izimpikiswano: injongo nenani)
omi goal progress <GOAL_ID> 25

# Umlando woshintsho lwenjongo
omi goal history <GOAL_ID>
```

---

## Buza i-Omi ngamazwi akho (`ask`)

Umyalo ohlukile osezingeni eliphezulu: ubuza umbuzo ngolimi lwemvelo, bese impendulo yakhiwa kusuka ezingxoxweni zakho zangaphambili:

```bash
omi ask "yisiphi isinqumo engasithatha mayelana nohambo"
omi --json ask "yimiphi imisebenzi engathembisa ukuyiqeda kuleli sonto"
```

---

## 4. Ukuzenzakalela ne-JSON (`--json`)

Kuma-agent e-AI nasezikripthini, i-`omi-cli` ingakhiqiza i-JSON efundeka ngomshini. Ifulegi elithi `--json` liyi-**global** futhi kufanele libekwe **ngaphambi** komyalo omncane.

```bash
# Izinkumbulo: khipha i-id ne-content
omi --json memory list | jq '.[] | {id, content}'

# Izihloko zezinkulumo zakamuva
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# Izinto okufanele zenziwe ezivulekile
omi --json action-item list --open | jq '.'
```

> **Iphutha elijwayelekile:** `--json` iza ngaphambi komyalo omncane, hhayi ngemuva.
> * Kulungile: `omi --json memory list`
> * Akulungile: `omi memory list --json`

---

## 5. Isivumelwano Samakhodi Okuphuma (Exit Codes Contract)

Amakhodi okuphuma aboshelwe ngokuqinile kusivumelwano esichazwe ku-[omi_cli/errors.py](https://github.com/BasedHardware/omi/blob/main/sdks/python-cli/omi_cli/errors.py), ukuze izikripthi ne-CI zikwazi ukwethembela kuwo:

| Ikhodi | Igama Lophawu | Incazelo Nesimo |
| :---: | :--- | :--- |
| **0** | `EXIT_OK` | Impumelelo — Umyalo uphumelele ngokugcwele |
| **1** | `EXIT_USAGE` | Iphutha lokusetshenziswa — Umyalo ongavumelekile, izimpikiswano ezingekho, noma ukuhluleka kokuqinisekisa |
| **2** | `EXIT_AUTH` | Iphutha lokungena — Ukhiye we-API ongekho, ophelelwe yisikhathi, noma ongagunyaziwe |
| **3** | `EXIT_SERVER` | Iphutha leseva noma lokuxhuma — Impendulo ye-5xx noma inethiwekhi enqamukile |
| **4** | `EXIT_RATE_LIMITED` | Umkhawulo wezicelo wedluliwe — HTTP 429 Too Many Requests |
| **5** | `EXIT_NOT_FOUND` | Akutholakalanga — Isisetshenziswa (ID) esiceliwe asikho (HTTP 404) |

Isibonelo sokuphatha amaphutha ku-Bash:

```bash
if ! omi --json memory list > /dev/null 2>&1; then
  EXIT_CODE=$?
  case $EXIT_CODE in
    1) echo "Iphutha: Ukusetshenziswa okungavumelekile noma ifulegi elingalungile." ;;
    2) echo "Iphutha: Ukufakazela ubuqiniso kuhlulekile. Sicela usebenzise i-'omi auth login'." ;;
    3) echo "Iphutha: Iseva inenkinga noma uxhumano lunqamukile." ;;
    4) echo "Iphutha: Umkhawulo wesilinganiso wedluliwe. Sicela ulinde kancane." ;;
    5) echo "Iphutha: Isisetshenziswa asitholakalanga." ;;
    *) echo "Iphutha: Inkinga engalindelekile enekhodi engu-$EXIT_CODE." ;;
  esac
  exit $EXIT_CODE
fi
```

---

## 6. Ukusetshenziswa Okuthuthukile: I-API Yasendaweni Namaphrofayela Amaningi

### Ukuhlanganiswa kwe-Desktop API Yasendaweni

Lapho i-app ye-Omi Desktop isebenza kukhompyutha yakho, ungaxhuma ngqo esikhundleni sokuya efwini (cloud):

```bash
# Setha ikheli le-API yasendaweni
export OMI_LOCAL_API_URL="http://127.0.0.1:47778"

# Setha ithokheni lasendaweni
export OMI_LOCAL_TOKEN="ithokheni_lakho_lasendaweni"

# Hlola isimo sasendaweni
omi auth status
```

### Ukuphathwa Kwamaphrofayela Amaningi (Multi-profile)

Ungagcina amaphrofayela ahlukene ezindaweni ezahlukene (isb., eyakho siqu, yomsebenzi, noma yokuhlola):

```bash
# Ngena kuphrofayela yokuhlola (staging)
omi --profile staging auth login --api-key "omi_dev_staging_key"

# Sebenzisa umyalo ngaphansi kwaleyo phrofayela
omi --profile staging memory list
```

---

## 7. Isifinyezo

I-`omi-cli` inikeza onjiniyela nama-agent e-AI amandla aphelele edatha yakwa-Omi ngokuyilawula ngqo kusuka kutheminali. Ukuze uthole imininingwane eyengeziwe namadokhumenti e-Python SDK, vakashela ku-[docs.omi.me](https://docs.omi.me).\n