# omi-cli — amurid urar di Taqbaylit

> Amurid iselsan i usnifel di terminel. Yelha i medden d widak n lǧamiɛ n intelǧensa artifisiel.

`omi-cli` d amsaǧǧu n uzrir n tilufa n l-API n imselsiyen [Omi](https://omi.me).
Yettawi anekcum urar yerna ittusnifel ɣer wid n lɣerba n Omi:
taklit, tidiwenniyin, tinbal n lɣerba, d wid n leḥtiǧat.

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Tasemlit:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Tangalt n uselkim:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Asesteb

Tarrayt tettusmiwerwa d `pipx`: tesseqdac amsaǧǧu deg yiwen n weglim iǧerrden,
ihi ur yettwakkat ar isudem n tneɣbula n lproje-k.

```bash
# yettusmiwerwa: sesteb s pipx
pipx install omi-cli

# neɣ s pip
pip install omi-cli
```

> **D axatar: isem n lpaquet d isem n lferqa ur d-yemṣilal.**
> * Lpaquet yettwasesteb d **`omi-cli`** (lpaquet iǧerrden `omi` d lproje-nniḍen, ur d-yemḥeddad).
> * Mbaɛd asesteb tesseḍam taluft **`omi`**.

Sentem ma yekkat kulec:

```bash
omi --version
omi --help
```

---

## 2. Asentem

`omi-cli` yesebba snat n tneqqumt n ujerreḍ.

| Tarrayt | Yelha i | Taluft |
| :--- | :--- | :--- |
| **Tasarut n imselsi (`omi_dev_*`)** | CI/CD, tiscripten, imesḍa AI | `omi auth login --api-key ...` neɣ tagnayt n weglim |
| **Ajerreḍ s lminig (Google/Apple)** | Axeddim ɣef uselkim-ik | `omi auth login --browser` |

### Ajerreḍ interactiv

Sker-d s war tifanout, ad-k-yeqsɛ anwa tarrayt ad tesseqdceḍ.

```bash
omi auth login
# 1) Browser — jerreḍ s Google neɣ Apple (i medden)
# 2) API key — sekcem tsarut n imselsi seg app.omi.me (i imesḍa/CI)
```

Ma tferneḍ tsarut, anekcum yettuffar ihi tsarut ur teqqel ɣer uzmez n terminel.

### Ajerreḍ srid s lminig

```bash
omi auth login --browser
```

### Ajerreḍ s tsarut n imselsi

Awi tsarut seg [app.omi.me](https://app.omi.me) deg **Developer → API Keys**.

```bash
# sekles tsarut deg uswel
omi auth login --api-key omi_dev_...

# neɣ affek-tt s weglim — yelha i CI/CD d iseklilen
export OMI_API_KEY=omi_dev_...
```

Tagnayt n weglim `OMI_API_KEY` tettuseqdec m'ur tella tsarut yettwasekles
deg uneɣli itteddu, ihi deg yiwen n useklil ur xeddem ara d-yettwaru ɣer udisq.
Ma llan yella tsarut deg uneɣli, tsarut-nni tesseggma tagnayt n weglim.

### Senqed anekcum

Snat tneqqumt ddun ɣef iseqsiyen iǧerrden — ur ten-tekkem ara:

* `omi auth status` — ayen yettwasekles **dagini**: uneɣli, tsarut yettuferren, azemz n taggara.
  Tettkeddu war unemtaɣ.
* `omi auth whoami` — aseqqeq **ɣer unewwaɣ n Omi**: yessefqed tsarut tettwaqbel s tideṭ.
  Yesseɣ unemtaɣ.

```bash
omi auth status    # asenqad n dagini, war unemtaɣ
omi auth whoami    # asenqad n unewwaɣ
```

Smayyu tajennayt iqujran war jerreḍ-nniḍen — taluft-a tesɛa azal **kan i yinengan
n lminig/OAuth**. I uneɣli i yettwasentem s tsarut API (`omi_dev_*`),
`omi auth refresh` ur yettwakker s tuccḍa n useqdec (tangalt 1): ulac tajennayt
ad tettwamayyu — beddel tsarut deg usnas n Omi n uweb ma yesseɣ:

```bash
omi auth refresh
```

Ffeɣ:

```bash
omi auth logout
```

---

## 3. Tilufa n lɣerba

### Taklit (memories)

Tililiyin d tmusniwin i yewwez system ɣer kečč.

```bash
# tabdart n taklit
omi memory list

# xleq tiɣmert
omi memory create "Aseqdac iḥemmel uburik uzrem" --category lifestyle

# wali tiɣmert
omi memory get <MEMORY_ID>
```

### Tidiwenniyin (conversations)

Azmez n taɣbalut d uḍris n wensa neɣ usnas.

```bash
# 5 n tidiwenniyin tineggura
omi conversation list --limit 5

# tidiwennit temmel s tira
omi conversation get <CONVERSATION_ID> --include-transcript
```

### Tinbal n lɣerba (action items)

Tidmawin i yuɣeṛ Omi seg tidiwenniyin.

```bash
# kan wid yeldin
omi action-item list --open

# seddem tsemḍeɣt
omi action-item complete <ACTION_ITEM_ID>
```

### Leḥtiǧat (goals)

```bash
# tabdart n leḥtiǧat
omi goal list

# sekles azal amaynu n usfari (yesseɣ sin n iseqsiyen: leḥtiǧa d wazal)
omi goal progress <GOAL_ID> 25

# azmez n usnifel
omi goal history <GOAL_ID>
```

---

## Sseqdec tutlayt tamagnut (`ask`)

Taluft-nniḍen n wussan igerrzen: teṭṭef aseqsi s tutlayt tamagnut,
yerna tiririt tettwaxleq seg tidiwenniyin-ik.

```bash
omi ask "acu i yuɣeṛ ɣef usellek"
omi --json ask "anwa tinbal n lɣerba i jebbeḍ ad xedmeɣ dduqqel-a"
```

---

## 4. JSON d tiscripten (`--json`)

`omi-cli` yezmer ad d-yelqe JSON i yezmiren ad tt-yeɣeṛ lmachine.
Tifanout `--json` d **tamatut** — ilaq ad tt-tesɣimiɛdeɣ **qbel** tluft.

```bash
# taklit: awi id, aḍris d tagnayt
omi --json memory list | jq '.[] | {id, content, category}'

# tiqwalin n tidiwenniyin tineggura
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# tinbal n lɣerba yeldin
omi --json action-item list --open | jq '.'
```

> **Tuccḍa taɣbalut.** `--json` ddu qbel tluft, ula mbaɛd.
> * Ihih: `omi --json memory list`
> * Yir: `omi memory list --json`

Deg wussan `--json`, iznan n usfari d wid yellan i medden yeffaɣen —
stdout ɣur-s kan yiwen n wegzir JSON iǧehden. Tuccḍiwin ṛuḥen ɣer stderr
s wawal `{"error": "...", "detail": "..."}`.

---

## 5. Tingalin n tuffɣa

Tingalin n tuffɣa ǧehden i usnifel deg tiscripten.

| Tangalt | Azal |
| :--- | :--- |
| `0` | Yekker |
| `1` | Tuccḍa n useqdec (tifanout yir, aseqsi ilaqan iǧemɛen) |
| `2` | Asentem ur yekker — jerreḍ yesseɣ |
| `3` | Tuccḍa n unewwaɣ/unemtaɣ |
| `4` | Tarmit n tuzzma — ɛreḍ tikelt nniḍen |
| `5` | Aɣbalu ur yettwaf |

```bash
if ! omi memory get "$MEMO_ID" --json > /tmp/m.json; then
  code=$?
  case $code in
    2) omi auth login --browser ;;
    5) echo "taklit-nni ulac-itt" ;;
    *) echo "tuccḍa $code" ;;
  esac
fi
```

---

## 6. Uneɣli d uswel

Ma ɣur-k aṭas n imiḍanen neɣ iseglimen, ferzen-ten s uneɣli.
Tineɣlin ttwaseklesen deg `~/.omi/config.toml`.

```bash
# jerreḍ ɣer uneɣli udmawan
omi --profile personal auth login

# jerreḍ ɣer uneɣli n lɣerba
omi --profile work auth login

# sker taluft deg uneɣli iḍerran
omi --profile work memory list
```

Uneɣli ittuseqdac yettwafqen s tneqqumt-a: tifanout `--profile` (neɣ `-p`)
teseɣ aseggma ɣef kulec; mbaɛd tagnayt n weglim `OMI_PROFILE`; mbaɛd uneɣli
itteddu deg `~/.omi/config.toml`; yerna deg taggara uneɣli `default` am ḥebbs.

Wali yerna beddel uswel yelweṛ:

```bash
# acu yettwasɣimiɛen tura
omi config show

# anda yella ufaylu n uswel
omi config path

# beddel azal
omi config set api_base https://api.omi.me
```

---

## 7. Tawacult iḍarren

* [`agent_quickstart.md`](./agent_quickstart.md) — amek ad terneḍ `omi-cli` ɣer lǧamiɛ AI.
* [`shell_examples.sh`](./shell_examples.sh) — tisunɣarin n shell iheggin.
* [Tasemlit n Omi](https://docs.omi.me/doc/developer/cli/introduction) — tamusni tamellalt n tilufa.
