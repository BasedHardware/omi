# omi-cli — guid å vî-vite e walon

> On guid pratike po travaler avou Omi a pårti d' on terminå. Boun tant po les djins ki po les ågints AI.

`omi-cli` c' est l' cliyint oficir d' ligne di comande po l' API des diswalpeus [Omi](https://omi.me).
I dene on accès rade et scriptåve ås cwate mwaissezès sorcêyes d' Omi:
li mimoere, les covinces, les ponts d' accion et les bûts.

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Documintåcion:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Codse-sårdou:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Estallaedje

Li metôde ricmandêye c' est `pipx`: i estale l' usteye dins on environmint izolé,
paski ses dipindinces ni s' batront nén avou vosd projèts.

```bash
# ricmandé: estaler avou pipx
pipx install omi-cli

# oudonbén avou pip
pip install omi-cli
```

> **Impor tant: li no do paki et l' no del comande ni s' matchèt nén.**
> * Li paki k' on estale c' est **`omi-cli`** (li påkiet `omi` c' est on ôte projet, rén a voe).
> * Asteure k' il est estalé, on tape li comande **`omi`**.

Verifyîz ki tot vå:

```bash
omi --version
omi --help
```

---

## 2. Autantifiaedje

`omi-cli` sopôrte deus manires di s' clitchî.

| Metôde | Boun po | Comande |
| :--- | :--- | :--- |
| **Clê di diswalpeu (`omi_dev_*`)** | CI/CD, scripts, ågints AI | `omi auth login --api-key ...` oudonbén variable d' environmint |
| **Clitchiaedje pås påzireus (Google/Apple)** | Travaler so s' compôte | `omi auth login --browser` |

### Clitchiaedje interactiv

Roulez sins tchuzeu et il vos dmindrå ké metôde vôloz.

```bash
omi auth login
# 1) Browser — clitchî avou Google oudonbén Apple (po les djins)
# 2) API key — metoz li clê di diswalpeu d' app.omi.me (po les ågints/CI)
```

Si vos tchoezîz li clê, li tapaedje est catchî po ki li clê ni dmorre nén e l' istwere do terminå.

### Clitchî divièlmint på påzireus

```bash
omi auth login --browser
```

### Clitchî avou ene clê di diswalpeu

Travådîz li clê so [app.omi.me](https://app.omi.me) dizo **Developer → API Keys**.

```bash
# clapîz li clê dins l' configuraedje
omi auth login --api-key omi_dev_...

# oudonbén passez-li pår l' environmint — miôx po CI/CD et les conteneurs
export OMI_API_KEY=omi_dev_...
```

Li variable d' environmint `OMI_API_KEY` si eploye cwand nol clê n' est clapêye
dins l' profil actif, paski dins on conteneur rén n' doet esse scrît so disc.
Si l' profil a ddja ene clê, cisse clê la a l' pråsse so li variable d' environmint.

### Verifyîz l' accès

Deus comandes respondèt a des kestions diferinnes — ni s' mele nén:

* `omi auth status` — çou k' est clapé **la-minme**: profil, clê maskêye, date di fén.
  Oûye sins rweyåw.
* `omi auth whoami` — ene dmande **å serveur Omi**: verifyî ki li clê est vrêye acceptêye.
  I fåt l' rweyåw.

```bash
omi auth status    # contrôle la-minme, sås rweyåw
omi auth whoami    # contrôle sol serveur
```

Rinouvler on jeton ki finit sins riclitchî — cisse comande la våt **rén ki po les sessions
d' påzireus/OAuth**. Po on profil autantifié avou ene clê API (`omi_dev_*`),
`omi auth refresh` fåt fawte avou ene arêre d' eployaedje (côde 1): pont d' jeton
a rinovler — candjez li clê dins l' app web Omi si i fåt:

```bash
omi auth refresh
```

S' disclitchî:

```bash
omi auth logout
```

---

## 3. Comandêyes di båze

### Mimoere (memories)

Li fåts et li savwer ki l' sistinme a riclomé so vos.

```bash
# l' liste des mimoeres
omi memory list

# fwaitchîz ene novele
omi memory create "Li uzeu vout l' tim neûre" --category lifestyle

# loukîz ene particulire
omi memory get <MEMORY_ID>
```

### Covinces (conversations)

L' istwere d' vwès et d' tecse do dispôzif oudonbén del app.

```bash
# les 5 covinces les pus ricintes
omi conversation list --limit 5

# ene covince inteure avou s' transcript
omi conversation get <CONVERSATION_ID> --include-transcript
```

### Ponts d' accion (action items)

Les ôvres ki Omi a rtrié des covinces.

```bash
# rén ki les oûvertes
omi action-item list --open

# metoz come finêye
omi action-item complete <ACTION_ITEM_ID>
```

### Bûts (goals)

```bash
# l' liste des bûts
omi goal list

# ritchesse ene novele valoe d' progrès (i fåt LES DEUS årgumints: bût et valoe)
omi goal progress <GOAL_ID> 25

# l' istwere des candjmints
omi goal history <GOAL_ID>
```

---

## Kestioner e-n lingaedje naturå (`ask`)

Ene comande å pus håt livea: i prind ene kestion e lingaedje naturå,
et li respondou est basti so vos covinces.

```bash
omi ask "cwèç ki dj' a stindou so l' demeindaedje"
omi --json ask "kîs ponts d' accion dj' a promou d' fini cisse samwinne"
```

---

## 4. JSON et scripts (`--json`)

`omi-cli` pout produre on JSON léjib pår l' machine. Li tchuzeu `--json` est
**gloûbål** et doet esse metou **divant** li sûbcomande.

```bash
# mimoeres: rtrayîz id, tecse et categoreye
omi --json memory list | jq '.[] | {id, content, category}'

# les tites des covinces ricintes
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# les ponts d' accion oûverts
omi --json action-item list --open | jq '.'
```

> **Fåte comunne.** `--json` vént divant li sûbcomande, nén après.
> * Boun: `omi --json memory list`
> * Fôs: `omi memory list --json`

Dins l' moude `--json`, les messaedjes di progrès et les spinneus po les djins
dispårètèt — stdout ni contint rén k' on seûl documint JSON valåbe. Les fåtes
vont å stderr sol fôme `{"error": "...", "detail": "..."}`.

---

## 5. Côdes di rexhowe

Des côdes di rexhowe ståves po dicerdier e scripts.

| Côde | Sinifiaedje |
| :--- | :--- |
| `0` | Siccess |
| `1` | Arêre d' eployaedje (fôs tchuzeu, årgumint oblidjê mancant) |
| `2` | Autantifiaedje fayi — clitchiaedje rikixhît |
| `3` | Arêre di serveur/rweyåw |
| `4` | Limite di rêye — ritchessez pus tåd |
| `5` | Sorcêye nén trovêye |

```bash
if ! omi memory get "$MEMO_ID" --json > /tmp/m.json; then
  code=$?
  case $code in
    2) omi auth login --browser ;;
    5) echo "cisse mimoere la n' est pont" ;;
    *) echo "arêre $code" ;;
  esac
fi
```

---

## 6. Profils et configuraedje

Si vos avoz puzeurs contes oudonbén environmints, disseparîz-les avou des profils.
Les regladjes sont clapés e `~/.omi/config.toml`.

```bash
# clitchîz å profil da vosse
omi --profile personal auth login

# clitchîz å profil d' ôvraedje
omi --profile work auth login

# roulez ene comande dins on profil daçné
omi --profile work memory list
```

Li profil eployî est diterminé e ç' ÔRE LA: li tchuzeu `--profile` (oudonbén `-p`)
a l' pråsse so tot; après li variable d' environmint `OMI_PROFILE`; après li profil
actif e `~/.omi/config.toml`; et e-n fén li profil `default` come retcheymint.

Loukîz et candjîz l' configuraedje di s' minme:

```bash
# çou k' est reglé å moumint
omi config show

# wice k' est l' fichié di configuraedje
omi config path

# candjîz ene valoe
omi config set api_base https://api.omi.me
```

---

## 7. Prodjins pas

* [`agent_quickstart.md`](./agent_quickstart.md) — kimint raloyî `omi-cli` a on ågint AI.
* [`shell_examples.sh`](./shell_examples.sh) — des egzimpes di shell tertos prêts.
* [Documintåcion Omi](https://docs.omi.me/doc/developer/cli/introduction) — li rifirece inteure des comandes.
