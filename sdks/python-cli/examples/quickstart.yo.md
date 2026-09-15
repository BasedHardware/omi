# omi-cli — Ìtọ́nisọ̀nà Ìbẹ̀rẹ̀ Kíákíá n'Èdè Yorùbá (Yoruba Quickstart)

> Ìtọ́nisọ̀nà tí ó wúlò tí ó sì ń fihàn bí a ṣe ń ṣiṣẹ́ pẹ̀lú Omi láti inú tẹminali. A ṣe é fún àwọn olùgbéésẹ̀ (developers) àti àwọn aṣojú AI (AI agents).

`omi-cli` ni ohun èlò àṣẹ ìlà-ojú (CLI) tí ó jẹ́ tí ó sì fún API àwọn olùgbéésẹ̀ [Omi](https://omi.me). Ó fúnyẹ́ ìṣàkóso àti ìdàgbàsókè lórí àwọn nǹkan mẹ́rin pàtàkì: àwọn ìrántí (memories), àwọn ìjíròrò (conversations), àwọn iṣẹ́ tí a dá lẹ́rő láti ṣe (action items), àti àwọn àfojúsùn (goals).

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Ìwé ìtọ́nisọ̀nà osì:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Orísun kódù:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Ìfi sori ẹrọ (Installation)

Ọ̀nà tí a níyì jùlọ ni kí o lo `pipx`: ó ń fi ohun èlò náà sí ayíká kan tí ó yàtọ̀ (isolated environment) kí ó má baà ṣe àkóràn pẹ̀lú iṣẹ́ àwọn ilé-iṣẹ́ mìíràn rẹ:

```bash
# Ọ̀nà tí a nígbà níyì: ìfi sori ẹrọ pẹ̀lú pipx
pipx install omi-cli

# Tàbí pẹ̀lú tiwulú pẹ̀lú pip
pip install omi-cli
```

> **Kí o mọ̀: Orúkọ àpò àti orúkọ àṣà kò dọ̀gba.**
> * Orúkọ àpò lórí PyPI ni **`omi-cli`** (orúkọ `omi` fúnra rẹ̀ jẹ́ iṣẹ́ míràn tí kò ní àṣepọ̀ mọ́ ẹ̀yí).
> * Lẹ́yìn ìfi sori ẹrọ, ohun tí o ń pè ní tẹminali ni **`omi`**.

Ẹ̀rọ ìdánwò pé ó ṣiṣẹ́ dáadáa pẹ̀lú ọ̀nà ìrànlọ́wọ́:

```bash
omi --version
omi --help
```

---

## 2. Ìfọwọ́sí (Authentication)

`omi-cli` ń gbà ọ̀nà méjì pàtàkì láti wọ inú:

| Ọ̀nà | Ìgbà tí ó dára jùlọ | Àṣà |
| :--- | :--- | :--- |
| **Bọtìnnì API olùgbéésẹ̀ (`omi_dev_*`)** | Ìdàgbàsókè àìní-ènìyàn, CI/CD, sáfátì àìní-fóótò, àwọn aṣojú AI | `omi auth login --api-key ...` tàbí oníyìpò ayíká (environment variable) |
| **Browser OAuth (Google/Apple)** | Kọ̀mpútá ti ara ẹni àti àwọn olùgbéésẹ̀ ìbílẹ̀ | `omi auth login --browser` (Google) / `--provider apple` |

### Ìwọle tí ó ń béèrè (Interactive login)

Bí o bá ṣi i láì fi ọ̀nà kan sílẹ̀, yóò bẹ̀ wọ́n kí o yan:

```bash
omi auth login
# 1) Browser — wọ inú pẹ̀lú Google (tàbí àkántì Apple: --provider apple)
# 2) API key — fi bọtìnnì API tí o dá síní app.omi.me
```

### Ìwọle tàrà nípasẹ̀ browser

```bash
# Ìbẹ̀rẹ̀ pẹ̀lú Google
omi auth login --browser

# Tàbí pẹ̀lú Apple
omi auth login --browser --provider apple
```

### Ìwọle pẹ̀lú bọtìnnì API olùgbéésẹ̀

Dá bọtìnnì rẹ sí nínú [app.omi.me](https://app.omi.me) lábẹ́ **Developer → API Keys**:

```bash
# Fi bọtìnnì pamọ́ sínú profaili ìbílẹ̀ pẹ̀lú àṣà
omi auth login --api-key omi_dev_...

# Tàbí fi sí ọ̀nà oníyìpò ayíká (èyí tó dára jù fún containers àti CI/CD)
# Àkíyèsí: Bí bọtìnnì ti wà nínú profaili tí ń ṣiṣẹ́ tẹ́lẹ̀, ṣe `omi auth logout` kọ́kọ́.
export OMI_API_KEY="omi_dev_your_actual_key_here"
```

### Ìdánwò ipò ìfọwọ́sí

Àwọn àṣà méjì yìí ń fún ní ìwì̀fúnni ti o yàtọ̀, a kò gbọdì̀ dá wọ́n pọ̀:

* `omi auth status` — ó ń fi hàn ohun tí wà **nínú kọ̀mpútá rẹ (lọ́nà àìní-ayélujára)**: profaili tí ń ṣiṣẹ́, bọtìnnì tí a fi ìdí àrò (masked), àti ìgbà tí yóò parí. Kò ní ayélujára.
* `omi auth whoami` — ó ń sọ̀rọ̀ pẹ̀lú **sáfátì Omi**: ó tún ń ṣe àyẹ̀wò pé bọtìnnì rẹ ṣiṣẹ́ òdodo. Ó nílò ayélujára.

```bash
omi auth status
omi auth whoami
```

Láti jáde:

```bash
omi auth logout
# Bí OMI_API_KEY bá wà nínú ayíká, yọ kúrò nibẹ̀ náà (Bash/Zsh: `unset OMI_API_KEY`).
```

---

## 3. Àwọn Àṣà Kíkéré (Basic Commands)

### Àwọn ìrántí (Memories)

Ìwì̀fúnni kékeré tí Omi kọ́kọ́ kọ àti pamọ́:

```bash
# Ṣe àkójọ àwọn ìrántí tí a pamọ́
omi memory list

# Dá ìrántí tuntun sílẹ̀
omi memory create "Mo fẹ́ àwọn èsì tí ó ní àwọn àpẹẹrẹ Python" --category work

# Wà nkọni ẹ̀kúnrẹ́rẹ́ ti ìrántí kan
omi memory get <MEMORY_ID>
```

### Àwọn ìjíròrò (Conversations)

Àkọsílẹ̀ ìfọ̀rọ̀wánilẹ́nuwò àti ìjíròrò láti ẹ̀rọ Omi:

```bash
# Ṣe àkójọ ìjíròrò mẹ́sán-án tí ó ṣẹ̀ṣẹ̀ wáyé
omi conversation list --limit 5

# Wà ẹ̀kúnrẹ́rẹ́ àti ọ̀rọ̀ gbogbo ti ìjíròrò
omi conversation get <CONVERSATION_ID> --include-transcript
```

### Àwọn iṣẹ́ tí a dá lẹ́rő láti ṣe (Action Items)

Iṣẹ́ tí wọ́n yọ kúrò ní àìmọ̀-ara-ènìyàn nínú àwọn ìjíròrò:

```bash
# Ṣe àkójọ iṣẹ́ tí kò tíì parí
omi action-item list --open

# Parí iṣẹ́ kan
omi action-item complete <ACTION_ITEM_ID>
```

### Àwọn àfojúsùn (Goals)

Ìlọsíwájú àti àwọn àfojúsùn tó gùn:

```bash
# Ṣe àkójọ àwọn àfojúsùn tí ń ṣiṣẹ́
omi goal list

# Dá àfojúsùn iye tuntun sílẹ̀
omi goal create "Mu omi 2L lójoojúmọ́" --type numeric --target 2 --unit liters
```

---

## 4. Ìdàgbàsókè àti ìjáde JSON (`--json`)

`omi-cli` ní ìtìlẹ́yìn dákun-dun fún ìdàgbàsókè ìfáńsí (automation pipelines). Bí o bá fi àmì `--json` sí, ìjáde yóò jáde ní JSON tó tọ́:

```bash
# Ṣe àkójọ ìrántí gẹ́gẹ́ bí JSON, jẹ́ jq gba àwọn ìpínlẹ̀ já
omi --json memory list | jq '.[] | {id, content, category}'

# Gba àkọlé ti ìjíròrò tuntun
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# Fi àwọn iṣẹ́ tí ń dúró hàn gẹ́gẹ́ bí JSON
omi --json action-item list --open | jq '.'
```

> **Ofì ìṣàkóso pàtàkì:** Àmì `--json` jẹ́ **àṣà àpapọ̀** kí ó sì tẹ̀lé ṣájú iṣẹ́ kékeré:
> * Ó tọ́: `omi --json memory list`
> * Kò tọ́: `omi memory list --json`

---

## 5. Kóòdù Ìjáde (Exit Codes)

Fún ìtọ́jú àṣìṣe tí ó ní ìtìjú nínú àkọsílẹ̀ shell àti iṣẹ́ CI/CD:

| Kóòdù Ìjáde | Ó túmọ̀ | Ìtumọ̀ si |
| :---: | :--- | :--- |
| `0` | **Aṣeyọrí** | Iṣẹ́ náà parí láìsí àṣìṣe. |
| `1` | **Àṣìṣe ìlò (Ìdànwò àṣìṣe)** | Iye tí kò tọ́ tàbí àṣìṣe ìdánwò ohun èlò; àṣìṣe ìṣàkóso ọ̀rọ̀ Click padà `2`. |
| `2` | **Àṣìṣe ìfọwọ́sí / ìṣàkóso CLI** | Àfọwọ́sí kò sí, bọtìnnì parí, tàbí àṣà Click tí a mọ̀. |
| `3` | **Àṣìṣe sáfátì / nẹ́tíwọ̀kì** | Èsì HTTP 5xx, àsìkò tí ó pari (timeout), tàbí kò sí ọ̀nà dé sáfátì. |
| `4` | **Ìdínkù ìyíyí (Rate Limited)** | HTTP 429 — ìbéèrè náà kọjá oke ìyíyí. |
| `5` | **A kò rí i (Not Found)** | HTTP 404 — nǹkan tí a ń wá kò sí. |

---

## 6. Àpẹẹrẹ Fún Ayíká Shell (Shell Examples)

### Bash / Zsh (Linux / macOS)

```bash
# Bọtìnnì API fún ìgbà yìí
export OMI_API_KEY="omi_dev_your_actual_key_here"

# Ṣiṣẹ́ àṣà kí o tún ṣe ìdánwò kóòdù ìjáde
omi --json memory list --limit 10
if [ $? -ne 0 ]; then
    echo "A kò lè béèrè àwọn ìrántí oníṣẹ́." >&2
fi
```

### PowerShell (Windows)

```powershell
# Fi bọtìnnì API sí oníyìpò ayíká
$env:OMI_API_KEY = "omi_dev_your_actual_key_here"

# Yí ìjáde JSON padà sí nǹkan tí PowerShel lè lo
$memories = omi --json memory list | ConvertFrom-Json

# Lo $LASTEXITCODE láti ṣe ìdánwò àṣìṣe
if ($LASTEXITCODE -ne 0) {
    Write-Error "Ìwà omi kọ̀ láti ṣiṣẹ́ pẹ̀lú kóòdù $LASTEXITCODE."
}
```

---

## 7. Ìṣàpọ̀ API Ìbílẹ̀ (Local Desktop API)

Nígbà tí àpótí Omi Desktop bá ń ṣiṣẹ́ lórí kọ̀mpútá rẹ, o lè béèrè nínú ìwì̀fúnni ìbílẹ̀ láìfi ọwọ́ sí ojú òjú ìwọle ayélujára (cloud):

```bash
# Ṣètò njade ìbílẹ̀ (fi oníyìpò ayíká pamọ́ bọtìnnì)
export OMI_LOCAL_API_URL="http://127.0.0.1:47778"
read -r -s -p "Desktop token: " OMI_LOCAL_TOKEN; echo
export OMI_LOCAL_TOKEN

# Ṣe ìdánwò ìbáṣepọ̀ ìbílẹ̀
omi --json local status

# Ṣàwárí nínú ìtàn-àkọlé ìbojú tí ó ṣẹ̀ṣẹ̀ kọjá
omi --json local search-screen "Ìròyìn oṣù" --days 7 --app Safari
```

---

## 8. Ìṣàkóso ọ̀pọ̀lọpọ̀ Profaili (Profiles)

Yí àkántì ara ẹni àti iṣẹ́, tàbí ayíká ìdánwò, pọ̀ pẹ̀lú `--profile`. Ìtòsọ́nà ń bẹ nínú `~/.omi/config.toml`:

```bash
# Dá profaili ara ẹni sílẹ̀ kí o wọ inú
omi --profile personal auth login

# Profaili iṣẹ́
omi --profile work auth login

# Ṣiṣẹ́ àṣà lábẹ́ profaili kan
omi --profile work memory list

# Profaili ìdánwò pẹ̀lú ojú ìwọle API míràn
omi --profile staging --api-base https://api-staging.omi.me memory list
```

---

## 9. Àbò àti Ìmọ̀tótó Ìṣe Dáadáa (Security Best Practices)

* **Máṣe gbé bọtìnnì API sínú ibi ìpamọ̀ kódù:** kí o lò ìdajì àṣírí (secret managers) tàbí fáìlì `.env` tí `.gitignore` bọ́.
* **Ìtàn-àkọọ̀lẹ shell:** Lórí kọ̀mpútá tí wọ́n ń pín, máṣe fi bọtìnnì nínú àyọkà ìlà-ojú; kí o lò ìwọle ìbáṣepọ̀ tàbí `OMI_API_KEY`.
* **Ìdínkù àwọn ayíká:** Gbé àwọn ìdánilẹ́kọ̀ọ́ ti àyíká ìtòsọ́nà `~/.omi/` nínú ẹ̀rọ Unix (`chmod 700 ~/.omi`).
