# omi-cli — Esperanta rapidgvidilo

> Praktika gvidilo por labori kun Omi el la terminalo. Taŭga kaj por homoj kaj por AI-agentoj.

`omi-cli` estas la oficiala komandlinia kliento por la programista API de [Omi](https://omi.me).
Ĝi donas rapidan kaj skripteblan aliron al la kvar kernaj estaĵoj de Omi:
memoraĵoj, konversacioj, agtaskoj kaj celoj.

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Dokumentado:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Fontkodo:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Instalado

La rekomendita metodo estas `pipx`: ĝi instalas la ilon en izolita medio,
tial ke ĝiaj dependencoj ne konfliktas kun viaj projektoj.

```bash
# rekomendite: instalado per pipx
pipx install omi-cli

# aŭ per pip
pip install omi-cli
```

> **Grave: la pakaĵnomo kaj la komandnomo malsamas.**
> * La instalata pakaĵo estas **`omi-cli`** (la aparta pakaĵo `omi` estas alia, nerilata projekto).
> * Post la instalado vi rulas la komandon **`omi`**.

Kontrolu ke ĉio funkcias:

```bash
omi --version
omi --help
```

---

## 2. Aŭtentigo

`omi-cli` subtenas du ensalutmetodojn.

| Metodo | Taŭga por | Komando |
| :--- | :--- | :--- |
| **Programista ŝlosilo (`omi_dev_*`)** | CI/CD, skriptoj, AI-agentoj | `omi auth login --api-key ...` aŭ medio-variablo |
| **Ensaluto per retumilo (Google/Apple)** | Laboro ĉe via propra komputilo | `omi auth login --browser` |

### Interaga ensaluto

Sen flagoj la komando mem demandas kiun metodon vi volas uzi:

```bash
omi auth login
# 1) Browser — ensalutu per Google aŭ Apple (oportuna por homoj)
# 2) API key — algluu programistan ŝlosilon el app.omi.me (oportuna por agentoj kaj CI)
```

Se vi elektas la ŝlosilon, la enigo kaŝiĝas, por ke la ŝlosilo ne restu en la terminala historio.

### Rekte per retumilo

```bash
omi auth login --browser
```

### Per programista ŝlosilo

La ŝlosilon vi ricevas ĉe [app.omi.me](https://app.omi.me) sub **Developer → API Keys**.

```bash
# konservu la ŝlosilon en la agordo
omi auth login --api-key omi_dev_...

# aŭ pasu ĝin per la medio — preferinde por CI/CD kaj ujoj
export OMI_API_KEY=omi_dev_...
```

La medio-variablo `OMI_API_KEY` uziĝas kiam neniu ŝlosilo konserviĝas en la aktiva profilo,
do en ujo nenio devas esti skribata al la disko. Se la profilo jam havas ŝlosilon,
ĝi prioritatas super la medio-variablo.

### Kontrolu la ensaluton

Du komandoj respondas malsamajn demandojn kaj ne estu konfuzataj:

* `omi auth status` — kio konserviĝas **loke**: profilo, maskita ŝlosilo, limdato.
  Funkcias sen reto.
* `omi auth whoami` — peto **al la servilo Omi**: kontrolas ke la ŝlosilo vere
  akceptiĝas. Postulas reton.

```bash
omi auth status    # loka kontrolo, senrete
omi auth whoami    # kontrolo ĉe la servilo
```

Ĝisdatigu eksvalidiĝontan OAuth-sesion sen reensaluto — validas nur por retumila ensaluto (OAuth). Por ŝlosiloj `omi_dev_*` ĉi tiu komando nenion ĝisdatigas; anstataŭigu la ŝlosilon en la retaplikaĵo sub `Developer → API Keys`:

```bash
omi auth refresh
```

Elsalutu:

```bash
omi auth logout
```

---

## 3. Bazaj komandoj

### Memoraĵoj (memories)

Faktoj kaj scio kiujn la sistemo memoris pri vi.

```bash
# listo de memoraĵoj
omi memory list

# kreu novan
omi memory create "La uzanto preferas malluman etoson" --category lifestyle

# rigardu specifan
omi memory get <MEMORY_ID>
```

### Konversacioj (conversations)

Parol- kaj teksthistorio el la aparato aŭ la aplikaĵo.

```bash
# la lastaj 5 konversacioj
omi conversation list --limit 5

# plena konversacio kun transskribo
omi conversation get <CONVERSATION_ID> --include-transcript
```

### Agtaskoj (action items)

Taskoj kiujn Omi elkonkludis el konversacioj.

```bash
# nur malfermitaj
omi action-item list --open

# marku kiel plenumitan
omi action-item complete <ACTION_ITEM_ID>
```

### Celoj (goals)

```bash
# listo de celoj
omi goal list

# registru novan progresvaloron (postulas AMBAŬ argumentojn: celo kaj valoro)
omi goal progress <GOAL_ID> 25

# ŝanĝhistorio
omi goal history <GOAL_ID>
```

---

## Demandu per viaj propraj vortoj (`ask`)

Aparta pintkomando: faras demandon en natura lingvo,
kaj la respondo konstruiĝas el viaj propraj konversacioj.

```bash
omi ask "kion mi decidis pri la translokiĝo"
omi --json ask "kiujn taskojn mi promesis fini ĉi-semajne"
```

---

## 4. JSON kaj skriptoj (`--json`)

`omi-cli` povas eligi maŝinlegeblan JSON. La flago `--json` estas **ĝenerala**
kaj tial metiĝas **antaŭ** la subkomandon.

```bash
# memoraĵoj: elprenu id, tekston kaj kategorion
omi --json memory list | jq '.[] | {id, content, category}'

# titoloj de la lastaj konversacioj
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# malfermitaj agtaskoj
omi --json action-item list --open | jq '.'
```

> **Ofta eraro.** `--json` venas antaŭ la subkomando, ne poste.
> * Ĝuste: `omi --json memory list`
> * Malĝuste: `omi memory list --json`

En reĝimo `--json` nenio krom la JSON mem skribiĝas al stdout —
skriptoj povas fidi je tio.

---

## 5. Elirkodoj

La kodoj estas stabilaj, do logiko en skriptoj kaj CI povas disbranĉi laŭ ili.

| Kodo | Signifo | Kiam |
| :---: | :--- | :--- |
| `0` | Sukceso | La komando plenumiĝis |
| `1` | Alvokeraro | propra validado de omi-cli (ekz. kaj `--browser` kaj `--api-key` samtempe, malvalida ensalutelekto, malplena stdin) |
| `2` | Aliro- aŭ argumenteraro | ne ensalutita, malvalida aŭ eksvalida ŝlosilo — krome sintakseraroj (nekonata flago, mankanta argumento) |
| `3` | Servileraro | 5xx-respondo, limtempo, neniu konekto |
| `4` | Tro da petoj | 429 Too Many Requests |
| `5` | Ne trovita | 404, id ne ekzistas |

Ekzemplo de kontrolo en Bash:

```bash
if omi --json auth whoami > /dev/null 2>&1; then
  echo "la ŝlosilo funkcias"
else
  code=$?
  [ "$code" -eq 2 ] && echo "reensalutu"
  [ "$code" -eq 3 ] && echo "la servilo ne haveblas, provu denove poste"
fi
```

---

## 6. Medio-variabloj

### Bash / Zsh (Linux, macOS)

```bash
export OMI_API_KEY="omi_dev_via_ŝlosilo"

omi --json memory list --limit 10
```

Por ke la ŝlosilo ŝargiĝu en novaj sesioj, aldonu la linion al `~/.bashrc` aŭ `~/.zshrc`.

### PowerShell (Windows)

```powershell
$env:OMI_API_KEY = "omi_dev_via_ŝlosilo"

# JSON-analizo per PowerShell
(omi --json memory list | ConvertFrom-Json) | Select-Object id, content
```

Por daŭra agordo:

```powershell
[Environment]::SetEnvironmentVariable("OMI_API_KEY", "omi_dev_via_ŝlosilo", "User")
```

---

## 7. La aplikaĵo Omi Desktop loke

Se la labortabla aplikaĵo Omi rulas, parto de la datumoj atingeblas rekte,
preter la nubo.

```bash
# indiku la adreson de la loka API
omi local configure --url http://127.0.0.1:47778 --token VIA_ĴETONO

# kontrolu ke ĝi respondas
omi --json local status

# serĉo en la ekranhistorio
omi --json local search-screen "prezoj" --days 7 --app Safari

# ekrankopio laŭ id
omi --json local screenshot 123 --output /tmp/omi-shot.jpg

# ajna SQL kontraŭ la loka datumbazo
omi --json local sql "SELECT appName, COUNT(*) FROM screenshots GROUP BY appName"
```

Laborfluo: unue `local status`, poste `local tools` — por vidi la haveblajn
ilojn kaj iliajn parametrojn, kaj nur poste vokoj.

---

## 8. Profiloj

Se vi havas plurajn kontojn aŭ mediojn, disigu ilin per profiloj.
La agordoj konserviĝas en `~/.omi/config.toml`.

```bash
# ensaluto al persona profilo
omi --profile personal auth login

# ensaluto al laborprofilo
omi --profile work auth login

# rulu komandon en specifa profilo
omi --profile work memory list
```

Se vi ne specifas profilon, la CLI unue uzas la valoron de la medio-variablo `OMI_PROFILE`, poste la aktivan profilon el la agordodosiero, poste `default`. Prioritata ordo: `--profile`, poste `OMI_PROFILE`, poste la aktiva profilo en `~/.omi/config.toml`, poste `default`.

Rigardu kaj ŝanĝu la agordon mem:

```bash
# kio estas agordita nun
omi config show

# kie la agordodosiero kuŝas
omi config path

# ŝanĝu valoron
omi config set api_base https://api.omi.me
```

---

## 9. Sekvaj paŝoj

* [`agent_quickstart.md`](./agent_quickstart.md) — kiel konekti `omi-cli` al AI-agento.
* [`shell_examples.sh`](./shell_examples.sh) — pretaj ekzemploj por la ŝelo.
* [Dokumentado de Omi](https://docs.omi.me/doc/developer/cli/introduction) — la plena komandreferenco.
