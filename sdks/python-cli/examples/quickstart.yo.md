# Ìtọ́sọ́nà ìbẹ̀rẹ̀ kíákíá omi-cli (Yoruba Quickstart)

> Ìtọ́sọ́nà tó wúlò fún ṣíṣiṣẹ́ pẹ̀lú Omi tààrà láti terminal — fún àwọn olùgbéga ẹ̀rọ àti àwọn AI agent adáṣe.

`omi-cli` ni command-line interface oníbàṣepọ̀ fún developer API ti [Omi](https://omi.me). Ó jẹ́ kí o ṣàkóso àwọn apá pàtàkì mẹ́rin ti ètò náà ní ọ̀nà tó wà létòlétò tí a sì lè ṣe ní adáṣe: ìrántí (memories), ìjíròrò (conversations), àwọn ohun ìṣe (action items) àti àwọn àfojúsùn (goals).

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Àkọsílẹ̀ oníbàṣepọ̀:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Kóòdù orísun:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

Àwọn orúkọ àṣẹ, àwọn àṣàyàn àti àwọn ìfiránṣẹ́ ètò náà wà ní èdè Gẹ̀ẹ́sì; ọ̀rọ̀ àlàyé ìtọ́sọ́nà yìí nìkan ni ó wà ní èdè Yorùbá. README èdè Gẹ̀ẹ́sì ni orísun àkọ́kọ́.

---

## 1. Ìfisórí (Installation)

Láti yẹra fún ìjàkadì dependency kí o sì ṣiṣẹ́ CLI náà ní àyíká tó dá dúró, a gba `pipx` níyànjú:

```bash
# Ìmọ̀ràn: ìfisórí tó dá dúró pẹ̀lú pipx
pipx install omi-cli

# Àṣàyàn mìíràn: pẹ̀lú pip nínú Python virtual environment tí a ti tan
pip install omi-cli
```

> **Àkíyèsí: Orúkọ package àti orúkọ àṣẹ**
> * Orúkọ package náà lórí PyPI ni **`omi-cli`** (orúkọ `omi` jẹ́ ti package mìíràn tí kò ní í ṣe pẹ̀lú rẹ̀).
> * Àṣẹ tí o ń ṣiṣẹ́ ní terminal ni **`omi`** nìkan.

Jẹ́rìí sí pé ìfisórí náà ń ṣiṣẹ́:

```bash
omi --version
omi --help
```

Tí terminal kò bá rí `omi`, ṣàyẹ̀wò pé virtual environment ti tan tàbí pé fólúdà tí `pipx` ń fi àwọn fáìlì ìṣiṣẹ́ sí wà nínú `PATH` rẹ.

---

## 2. Ìfẹ̀rí ìdánimọ̀ (Authentication)

`omi-cli` ń ṣe àtìlẹ́yìn fún ọ̀nà ìfẹ̀rí ìdánimọ̀ pàtàkì méjì:

| Ọ̀nà | Ìlò | Àpẹẹrẹ |
| :--- | :--- | :--- |
| **Bọ́tìnì API olùgbéga (`omi_dev_*`)** | Àwọn script, CI/CD, àwọn server aláìní ìbòjú, àwọn AI agent | `omi auth login --api-key ...` tàbí `OMI_API_KEY` |
| **OAuth ẹ̀rọ aṣàwákiri (Google/Apple)** | Àwọn ibùdó iṣẹ́ àdúgbò àti àwọn olùgbéga | `omi auth login --browser` (Google) / `--provider apple` |

### Ìwọlé alábàáṣepọ̀
Ṣiṣẹ́ láìsí flag kankan láti yan ọ̀nà náà ní ọ̀nà alábàáṣepọ̀:

```bash
omi auth login
# 1) Browser — ó ń ṣí ẹ̀rọ aṣàwákiri fún ìwọlé Google (lo `--provider apple` fún Apple)
# 2) API key — lẹ̀ bọ́tìnì API láti app.omi.me (a fi ìkọ̀wé náà pamọ́)
```

### Ìwọlé tààrà nípasẹ̀ ẹ̀rọ aṣàwákiri
```bash
# Àṣàyàn àkọ́kọ́: ìwọlé Google
omi auth login --browser

# Àṣàyàn mìíràn: ìwọlé Apple
omi auth login --browser --provider apple
```

### Lílo bọ́tìnì API olùgbéga
Ṣẹ̀dá bọ́tìnì kan ní [app.omi.me](https://app.omi.me) lábẹ́ **Developer → API Keys**:

```bash
# Fi bọ́tìnì náà pamọ́ sínú profile àdúgbò tó ń ṣiṣẹ́
omi auth login --api-key omi_dev_token_gidi_rẹ

# Tàbí ṣètò rẹ̀ gẹ́gẹ́ bí environment variable (ó dára jù fún container àti CI/CD)
export OMI_API_KEY="omi_dev_token_gidi_rẹ"
```

> A ń lo `OMI_API_KEY` nìkan nígbà tí profile tó ń ṣiṣẹ́ kò bá ní bọ́tìnì tí a ti fi pamọ́. Tí o bá ti wọlé tẹ́lẹ̀ pẹ̀lú `omi auth login` tí o sì fẹ́ kí environment variable náà ṣiṣẹ́, kọ́kọ́ ṣiṣẹ́ `omi auth logout`.

### Ṣíṣàyẹ̀wò ipò ìfẹ̀rí ìdánimọ̀
* `omi auth status`: ó ń fi profile tó ń ṣiṣẹ́ àti ìwé-ẹ̀rí tí a bò hàn (ó ń ṣiṣẹ́ ní àdúgbò/láìsí ìsopọ̀; ọjọ́ ìparí kan àwọn token OAuth nìkan).
* `omi auth whoami`: ó ń fi ìbéèrè ránṣẹ́ sí server Omi láti jẹ́rìí sí ìwúlò (ó nílò nẹ́tíwọ́ọ̀kì).

```bash
omi auth status
omi auth whoami
```

Sọ token OAuth di tuntun láìsí wíwọlé lẹ́ẹ̀kansí:

```bash
omi auth refresh
```

> `omi auth refresh` ń ṣiṣẹ́ nìkan fún àwọn profile tí ó wọlé nípasẹ̀ ẹ̀rọ aṣàwákiri (OAuth). Fún àwọn profile tí ó dá lórí bọ́tìnì API, kò sí ohun tí a lè sọ di tuntun, àṣẹ náà sì ń parí pẹ̀lú ìfiránṣẹ́ «Nothing to refresh» àti exit code `1`.

Ìjáde:
```bash
omi auth logout
# Tí a bá ti ṣètò OMI_API_KEY nínú àyíká, yọ ọ́ kúrò pẹ̀lú (Bash/Zsh: `unset OMI_API_KEY`).
```

---

## 3. Àwọn àṣẹ pàtàkì

### Ìrántí (Memories)
Àwọn òtítọ́ tó wà létòlétò àti àwọn àkíyèsí ipò tí Omi ti fi pamọ́:

```bash
# Ṣe àtòjọ àwọn ìrántí
omi memory list

# Ṣẹ̀dá ìrántí tuntun pẹ̀lú ẹ̀ka
omi memory create "Mo fẹ́ràn àwọn ìdáhùn ìmọ̀-ẹ̀rọ kúkúrú pẹ̀lú àwọn àpẹẹrẹ Python" --category work

# Gba ìrántí kan pàtó nípasẹ̀ ID
omi memory get <MEMORY_ID>
```

### Ìjíròrò (Conversations)
Àwọn àgbéjáde ohùn, àwọn àkọsílẹ̀ àti àwọn ìjíròrò tí àwọn ẹ̀rọ Omi ṣàkọsílẹ̀:

```bash
# Ṣe àtòjọ ìjíròrò 5 tó kẹ́yìn
omi conversation list --limit 5

# Gba àwọn àlàyé ìjíròrò kan pẹ̀lú àkọsílẹ̀ kíkún
omi conversation get <CONVERSATION_ID> --include-transcript
```

### Àwọn ohun ìṣe (Action Items)
Àwọn iṣẹ́ tí a fà jáde ní adáṣe láti inú àwọn ìjíròrò:

```bash
# Ṣe àtòjọ àwọn ohun ìṣe tí kò tíì parí
omi action-item list --open

# Sàmì sí ohun ìṣe kan pé ó ti parí
omi action-item complete <ACTION_ITEM_ID>
```

### Àwọn àfojúsùn (Goals)
Àwọn àmì ìlọsíwájú àti àwọn àfojúsùn ìgbà pípẹ́:

```bash
# Ṣe àtòjọ àwọn àfojúsùn tó ń ṣiṣẹ́
omi goal list

# Ṣẹ̀dá àfojúsùn oníṣirò tuntun
omi goal create "Mu omi lítà 2 lójoojúmọ́" --type numeric --target 2 --unit liters

# Ṣe ìmúdójúìwọ̀n iye lọ́wọ́lọ́wọ́ ti àfojúsùn kan (ID àti iye tuntun)
omi goal progress <GOAL_ID> 1.5
```

---

## 4. Adáṣe létòlétò àti àbájáde JSON (`--json`)

A kọ́ `omi-cli` fún adáṣe nínú àwọn pipeline àti àwọn toolchain. Flag àgbáyé `--json` ń dá JSON mímọ́ tí ẹ̀rọ lè kà padà:

```bash
# Ṣe àtòjọ àwọn ìrántí gẹ́gẹ́ bí JSON kí o sì sẹ́ pẹ̀lú jq
omi --json memory list | jq '.[] | {id, content, category}'

# Gba àwọn àkọlé ìjíròrò àìpẹ́
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# Wo gbogbo àwọn ohun ìṣe tí kò tíì parí gẹ́gẹ́ bí JSON aláìṣe
omi --json action-item list --open | jq '.'
```

> **Òfin ìlànà-ọ̀rọ̀ pàtàkì:**
> `--json` jẹ́ **àṣàyàn àgbáyé** a sì gbọ́dọ̀ fi sí **ṣáájú** subcommand:
> * Tó tọ́: `omi --json memory list`
> * Àṣìṣe: `omi memory list --json`

### Pípín ojú-ìwé (Pagination)
Àwọn àṣẹ `list` ń ṣe àtìlẹ́yìn fún `--limit` àti `--offset`:

```bash
omi --json memory list --limit 50 --offset 50
```

### Gbígbé jáde sínú fáìlì
Láti dènà àwọn àwọ̀ ANSI tàbí àwọn àmì ìdarí láti ba fáìlì jẹ́, darí stdout tààrà nínú shell:

```bash
# Gbé àwọn ìrántí jáde tààrà sínú fáìlì JSON mímọ́
omi --json memory list > memories.json
```

---

## 5. Àwọn kóòdù ìjáde (Exit Codes Contract)

Fún ìmúṣẹ àṣìṣe tó ṣeé gbẹ́kẹ̀lé nínú CI/CD àti àwọn script, `omi-cli` ń tẹ̀lé àdéhùn kóòdù ìjáde tó le (wo `omi_cli/errors.py`):

| Kóòdù | Orúkọ | Àlàyé àti àpẹẹrẹ |
| :---: | :--- | :--- |
| `0` | **Àṣeyọrí (`EXIT_OK`)** | Iṣẹ́ náà parí láìsí àṣìṣe. |
| `1` | **Àṣìṣe ìlò (`EXIT_USAGE`)** | Àwọn àṣìṣe ìfẹ̀rí ti omi-cli fúnra rẹ̀: `--browser` àti `--api-key` tí kò lè jọ wà, àṣàyàn tí kò tọ́ nínú ìwọlé alábàáṣepọ̀, ìkọ̀wé òfo láti stdin, tàbí `omi auth refresh` lórí profile bọ́tìnì API. |
| `2` | **Àṣìṣe ìfẹ̀rí ìdánimọ̀ (`EXIT_AUTH`)** | Ìwé-ẹ̀rí tí kò sí tàbí tí kò tọ́, tàbí ìgbà tí ó ti parí. Àkíyèsí: flag àìmọ̀ tàbí argument tí ó sọnù ni Click fúnra rẹ̀ ń kọ̀, ó sì ń jáde pẹ̀lú kóòdù `2` pẹ̀lú. |
| `3` | **Àṣìṣe server (`EXIT_SERVER`)** | HTTP 5xx láti server Omi tàbí ìdílọ́wọ́ nẹ́tíwọ́ọ̀kì. |
| `4` | **Ìdínkù ìwọ̀n (`EXIT_RATE_LIMITED`)** | HTTP 429 — àwọn ìbéèrè púpọ̀ jù ní ìgbà kúkúrú. |
| `5` | **A kò rí i (`EXIT_NOT_FOUND`)** | HTTP 404 — ohun tí a béèrè fún (ìrántí, ìjíròrò, ohun ìṣe) kò sí. |

---

## 6. Àwọn àpẹẹrẹ fún àwọn shell oríṣiríṣi

### Bash / Zsh (Linux / macOS)
```bash
# Ṣètò bọ́tìnì API fún ìgbà yìí
export OMI_API_KEY="omi_dev_token_gidi_rẹ"

# Ṣiṣẹ́ àṣẹ kí o sì ṣàyẹ̀wò kóòdù ìjáde
omi --json memory list --limit 10
if [ $? -ne 0 ]; then
    echo "Àṣìṣe nínú gbígba àwọn ìrántí láti Omi." >&2
fi
```

### PowerShell (Windows)
```powershell
# Ṣàlàyé environment variable nínú PowerShell
$env:OMI_API_KEY = "omi_dev_token_gidi_rẹ"

# Yí àbájáde JSON padà tààrà sí PowerShell object
$memories = omi --json memory list | ConvertFrom-Json
$memories | Select-Object id, content, category

# Ṣàyẹ̀wò àṣìṣe pẹ̀lú $LASTEXITCODE
if ($LASTEXITCODE -ne 0) {
    Write-Error "Àṣẹ Omi kùnà pẹ̀lú kóòdù ìjáde $LASTEXITCODE."
}
```

---

## 7. Ìsopọ̀ API Desktop àdúgbò (Omi Desktop)

Nígbà tí Omi Desktop bá ń ṣiṣẹ́ lórí ẹ̀rọ rẹ (port àkọ́kọ́ 47778), o lè ṣiṣẹ́ tààrà pẹ̀lú ipò àdúgbò láìsí lílọ nípasẹ̀ cloud:

```bash
# Ṣètò ìsopọ̀ API àdúgbò (lo environment variable láti dáàbò bo token)
export OMI_LOCAL_API_URL="http://127.0.0.1:47778"
read -r -s -p "Tẹ token Desktop: " OMI_LOCAL_TOKEN; echo
export OMI_LOCAL_TOKEN

# Jẹ́rìí sí ipò ìsopọ̀ àdúgbò
omi --json local status

# Wá nínú ìtàn ìbòjú àdúgbò
omi --json local search-screen "Ìròyìn ìdámẹ́rin ọdún" --days 7 --app Safari
```

Dípò àwọn environment variable o lè fi àwọn ètò pamọ́ sórí profile: `omi local configure --url http://127.0.0.1:47778 --token ...`.

---

## 8. Ṣíṣàkóso àwọn profile púpọ̀ (Profiles)

Lo `--profile` láti yípadà láìsí wàhálà láàrín àkàǹtì ti ara ẹni, profile iṣẹ́ tàbí àyíká ìdánwò. A fi àwọn ètò pamọ́ sínú `~/.omi/config.toml`. Ètò ìṣáájú: flag `--profile`, lẹ́yìn náà environment variable `OMI_PROFILE`, àti níkẹyìn profile `default`.

```bash
# Ṣẹ̀dá kí o sì wọlé sí profile ti ara ẹni
omi --profile personal auth login

# Ṣẹ̀dá kí o sì wọlé sí profile iṣẹ́
omi --profile work auth login

# Ṣiṣẹ́ àṣẹ pẹ̀lú profile kan pàtó
omi --profile work memory list

# Yan profile nípasẹ̀ environment variable
export OMI_PROFILE=work
omi memory list

# Lo endpoint àdáni fún ìdánwò
omi --profile staging --api-base https://api.staging.omi.me memory list
```

---

## 9. Àwọn ìtọ́sọ́nà ààbò àti àwọn àṣà tó dára jù

* **Má ṣe kọ àwọn bọ́tìnì sínú kóòdù:** Má ṣe ṣe commit àwọn bọ́tìnì API (`omi_dev_*`) sí Git repository láé. Lo àwọn fáìlì `.env` tí ó wà nínú `.gitignore` tàbí àwọn olùṣàkóso àṣírí tó ní ààbò.
* **Dáàbò bo ìtàn shell:** Lórí àwọn server tí a ń pín, má ṣe fi àwọn bọ́tìnì ránṣẹ́ gẹ́gẹ́ bí argument command-line ní gbangba; lo ìwọlé alábàáṣepọ̀ tàbí `OMI_API_KEY`.
* **Dín àwọn ìyọ̀ǹda fólúdà kù:** Lórí Unix/macOS, rí i dájú pé fólúdà ìṣètò ní àwọn ìyọ̀ǹda tó ní ààlà:
  ```bash
  chmod 700 ~/.omi
  chmod 600 ~/.omi/config.toml 2>/dev/null || true
  ```
* **Ìmọ́tótó ìgbà:** Nígbà tí o bá ń wó àwọn àyíká ìgbà díẹ̀ lulẹ̀, rántí láti yọ environment variable kúrò:
  ```bash
  unset OMI_API_KEY
  ```
