# Ntuziaka mmalite ngwa ngwa nke omi-cli (Igbo Quickstart)

> Ntuziaka bara uru maka iso Omi arụ ọrụ ozugbo site na terminal — maka ndị mmepe na ndị AI agent na-arụ ọrụ n'onwe ha.

`omi-cli` bụ command-line interface gọọmentị maka developer API nke [Omi](https://omi.me). Ọ na-enye gị ohere ijikwa akụkụ isi anọ nke sistemụ n'ụzọ a haziri ahazi ma nwee ike ime ya na-akpaghị aka: ncheta (memories), mkparịta ụka (conversations), ihe omume (action items) na ebumnuche (goals).

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Akwụkwọ gọọmentị:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Koodu isi:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

Aha iwu, nhọrọ na ozi nke mmemme na-anọgide n'asụsụ Bekee; naanị nkọwa nke ntuziaka a dị n'asụsụ Igbo. README Bekee bụ isi ntụaka.

---

## 1. Nwụnye

Iji zere esemokwu dependency ma jiri CLI rụọ ọrụ na gburugburu dịpụrụ adịpụ, a na-atụ aro `pipx`:

```bash
# A tụrụ aro: nwụnye dịpụrụ adịpụ site na pipx
pipx install omi-cli

# Ụzọ ọzọ: site na pip n'ime Python virtual environment agbanyere agbanye
pip install omi-cli
```

> **Rịba ama: Aha package na aha iwu**
> * Aha package na PyPI bụ **`omi-cli`** (aha `omi` bụ nke package ọzọ na-enweghị njikọ).
> * Iwu ị na-agba na terminal bụ naanị **`omi`**.

Gosi na nwụnye ahụ na-arụ ọrụ:

```bash
omi --version
omi --help
```

Ọ bụrụ na terminal ahụghị `omi`, hụ na virtual environment agbanyere ma ọ bụ na folda `pipx` na-etinye faịlụ executable dị na `PATH` gị.

---

## 2. Nkwenye njirimara (Authentication)

`omi-cli` na-akwado ụzọ nkwenye isi abụọ:

| Ụzọ | Ojiji | Ihe atụ |
| :--- | :--- | :--- |
| **Igodo API nke onye mmepe (`omi_dev_*`)** | Script, CI/CD, sava enweghị ihuenyo, ndị AI agent | `omi auth login --api-key ...` ma ọ bụ `OMI_API_KEY` |
| **OAuth ihe nchọgharị (Google/Apple)** | Ebe ọrụ mpaghara na ndị mmepe | `omi auth login --browser` (Google) / `--provider apple` |

### Mbanye mmekọrịta
Gbaa na-enweghị flag ọ bụla iji họrọ ụzọ ahụ na mmekọrịta:

```bash
omi auth login
# 1) Browser — na-emeghe ihe nchọgharị maka mbanye Google (jiri `--provider apple` maka Apple)
# 2) API key — mado igodo API site na app.omi.me (ezoro ihe ntinye ahụ)
```

### Mbanye ozugbo site na ihe nchọgharị
```bash
# Ndabara: mbanye Google
omi auth login --browser

# Ụzọ ọzọ: mbanye Apple
omi auth login --browser --provider apple
```

### Iji igodo API nke onye mmepe
Mepụta igodo na [app.omi.me](https://app.omi.me) n'okpuru **Developer → API Keys**:

```bash
# Ma ọ bụ tọọ ya dị ka environment variable (kacha mma maka container na CI/CD)
export OMI_API_KEY="omi_dev_token_gị_n'ezie"
```

> Na sava ndị a na-ekekọrịta, enyela igodo dị ka argument command-line n'ihu ọha; jiri mbanye mmekọrịta ma ọ bụ `OMI_API_KEY`.

```bash
# Chekwaa igodo ahụ na profaịlụ mpaghara na-arụ ọrụ
omi auth login --api-key omi_dev_token_gị_n'ezie
```

> A na-eji `OMI_API_KEY` naanị mgbe profaịlụ na-arụ ọrụ enweghị igodo echekwara. Ọ bụrụ na ị banyelarị site na `omi auth login` ma chọọ ka environment variable ahụ rụọ ọrụ, buru ụzọ gbaa `omi auth logout`.

### Ilele ọnọdụ nkwenye
* `omi auth status`: na-egosi profaịlụ na-arụ ọrụ na ihe nkwenye ekpuchiri (na-arụ ọrụ na mpaghara/na-anọghị n'ịntanetị; ụbọchị njedebe metụtara naanị token OAuth).
* `omi auth whoami`: na-eziga arịrịọ na sava Omi iji gosi na ọ dị irè (chọrọ netwọk).

```bash
omi auth status
omi auth whoami
```

Mee ka token OAuth dị ọhụrụ na-enweghị ibanye ọzọ:

```bash
omi auth refresh
```

> `omi auth refresh` na-arụ ọrụ naanị maka profaịlụ ndị banyere site na ihe nchọgharị (OAuth). Maka profaịlụ dabere na igodo API, ọ dịghị ihe a ga-eme ka ọ dị ọhụrụ, iwu ahụ na-akwụsị site na ozi «Nothing to refresh» na exit code `1`.

Ịpụ:
```bash
omi auth logout
# Ọ bụrụ na e tọrọ OMI_API_KEY na gburugburu, wepụkwa ya (Bash/Zsh: `unset OMI_API_KEY`).
```

---

## 3. Iwu isi

### Ncheta (Memories)
Eziokwu a haziri ahazi na nlebanya ọnọdụ nke Omi chekwara:

```bash
# Depụta ncheta
omi memory list

# Mepụta ncheta ọhụrụ nwere ụdị
omi memory create "Ahọrọ m azịza teknụzụ dị mkpirikpi nwere ihe atụ Python" --category work

# Nweta otu ncheta site na ID
omi memory get <MEMORY_ID>
```

### Mkparịta ụka (Conversations)
Ndekọ olu, ederede na mkparịta ụka nke ngwaọrụ Omi dekọrọ:

```bash
# Depụta mkparịta ụka 5 ikpeazụ
omi conversation list --limit 5

# Nweta nkọwa nke otu mkparịta ụka gụnyere ederede zuru ezu
omi conversation get <CONVERSATION_ID> --include-transcript
```

### Ihe omume (Action Items)
Ọrụ ewepụtara na-akpaghị aka site na mkparịta ụka:

```bash
# Depụta ihe omume mepere emepe
omi action-item list --open

# Kaa otu ihe omume dị ka emechara
omi action-item complete <ACTION_ITEM_ID>
```

### Ebumnuche (Goals)
Ihe ngosi ọganihu na ebumnuche ogologo oge:

```bash
# Depụta ebumnuche na-arụ ọrụ
omi goal list

# Mepụta ebumnuche ọnụọgụgụ ọhụrụ
omi goal create "Ṅụọ lita mmiri 2 kwa ụbọchị" --type numeric --target 2 --unit liters

# Melite uru ugbu a nke ebumnuche (ID na uru ọhụrụ)
omi goal progress <GOAL_ID> 1.5
```

---

## 4. Akpaghị aka a haziri ahazi na mmepụta JSON (`--json`)

E wuru `omi-cli` maka ọrụ akpaghị aka na pipeline na toolchain. Flag zuru ụwa ọnụ `--json` na-eweghachi JSON dị ọcha nke igwe nwere ike ịgụ:

```bash
# Depụta ncheta dị ka JSON ma jiri jq nyochaa
omi --json memory list | jq '.[] | {id, content, category}'

# Nweta isiokwu nke mkparịta ụka ndị na-adịbeghị anya
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# Lee ihe omume niile mepere emepe dị ka JSON raw
omi --json action-item list --open | jq '.'
```

> **Iwu syntax dị mkpa:**
> `--json` bụ **nhọrọ zuru ụwa ọnụ**, a ghaghị itinye ya **tupu** subcommand:
> * Ziri ezi: `omi --json memory list`
> * Ezighị ezi: `omi memory list --json`

### Nkewa ibe (Pagination)
Iwu `list` na-akwado `--limit` na `--offset`:

```bash
omi --json memory list --limit 50 --offset 50
```

### Ibupụ na faịlụ
Iji gbochie agba ANSI ma ọ bụ mkpụrụedemede njikwa imerụ faịlụ, duzie stdout ozugbo na shell:

```bash
# Bupụ ncheta ozugbo na faịlụ JSON dị ọcha
omi --json memory list > memories.json
```

---

## 5. Koodu ọpụpụ (Exit Codes Contract)

Maka njikwa njehie a pụrụ ịdabere na ya na CI/CD na script, `omi-cli` na-agbaso nkwekọrịta koodu ọpụpụ siri ike (lee `omi_cli/errors.py`):

| Koodu | Aha | Nkọwa na ihe atụ |
| :---: | :--- | :--- |
| `0` | **Ihe ịga nke ọma (`EXIT_OK`)** | Ọrụ ahụ mechara na-enweghị njehie. |
| `1` | **Njehie ojiji (`EXIT_USAGE`)** | Njehie nkwado nke omi-cli n'onwe ya: `--browser` na `--api-key` na-agaghị ejikọta, nhọrọ na-ezighị ezi na mbanye mmekọrịta, ntinye efu site na stdin, ma ọ bụ `omi auth refresh` na profaịlụ igodo API. |
| `2` | **Njehie nkwenye (`EXIT_AUTH`)** | Ihe nkwenye na-adịghị ma ọ bụ na-ezighị ezi, ma ọ bụ oge nnọkọ agwụla. Rịba ama: flag a na-amaghị ma ọ bụ argument na-adịghị bụkwa ihe Click n'onwe ya na-ajụ, ọ na-apụ na koodu `2`. |
| `3` | **Njehie sava (`EXIT_SERVER`)** | HTTP 5xx site na sava Omi ma ọ bụ nkwụsị netwọk. |
| `4` | **Mmachi ọnụọgụ (`EXIT_RATE_LIMITED`)** | HTTP 429 — arịrịọ dị ukwuu n'ime obere oge. |
| `5` | **Ahụghị ya (`EXIT_NOT_FOUND`)** | HTTP 404 — ihe a rịọrọ (ncheta, mkparịta ụka, ihe omume) adịghị. |

---

## 6. Ihe atụ maka shell dị iche iche

### Bash / Zsh (Linux / macOS)
```bash
# Tọọ igodo API maka nnọkọ a
export OMI_API_KEY="omi_dev_token_gị_n'ezie"

# Gbaa iwu ma lelee koodu ọpụpụ
omi --json memory list --limit 10
if [ $? -ne 0 ]; then
    echo "Njehie n'inweta ncheta site na Omi." >&2
fi
```

### PowerShell (Windows)
```powershell
# Kọwaa environment variable na PowerShell
$env:OMI_API_KEY = "omi_dev_token_gị_n'ezie"

# Gbanwee mmepụta JSON ozugbo ka ọ bụrụ PowerShell object
$memories = omi --json memory list | ConvertFrom-Json
$memories | Select-Object id, content, category

# Lelee njehie site na $LASTEXITCODE
if ($LASTEXITCODE -ne 0) {
    Write-Error "Iwu Omi dara site na koodu ọpụpụ $LASTEXITCODE."
}
```

---

## 7. Njikọ API Desktop mpaghara (Omi Desktop)

Mgbe Omi Desktop na-arụ ọrụ na igwe gị (port ndabara 47778), ị nwere ike iso ọnọdụ mpaghara rụọ ọrụ ozugbo na-agafeghị cloud:

```bash
# Hazie njikọ API mpaghara (jiri environment variable chebe token)
export OMI_LOCAL_API_URL="http://127.0.0.1:47778"
read -r -s -p "Tinye token Desktop: " OMI_LOCAL_TOKEN; echo
export OMI_LOCAL_TOKEN

# Gosi ọnọdụ njikọ mpaghara
omi --json local status

# Chọọ n'akụkọ ihuenyo mpaghara
omi --json local search-screen "Akụkọ nkeji anọ" --days 7 --app Safari
```

Kama environment variable, ị nwere ike chekwaa ntọala na profaịlụ: `omi local configure --url http://127.0.0.1:47778 --token ...`.

---

## 8. Ijikwa ọtụtụ profaịlụ (Profiles)

Jiri `--profile` gbanwee n'enweghị nsogbu n'etiti akaụntụ nkeonwe, profaịlụ ọrụ ma ọ bụ gburugburu nnwale. A na-echekwa ntọala na `~/.omi/config.toml`. Usoro mbụ: flag `--profile`, wee environment variable `OMI_PROFILE`, na n'ikpeazụ profaịlụ `default`.

```bash
# Mepụta ma banye na profaịlụ nkeonwe
omi --profile personal auth login

# Mepụta ma banye na profaịlụ ọrụ
omi --profile work auth login

# Gbaa iwu site na profaịlụ akọwapụtara
omi --profile work memory list

# Họrọ profaịlụ site na environment variable
export OMI_PROFILE=work
omi memory list

# Jiri endpoint ahaziri maka nnwale
omi --profile staging --api-base https://api.staging.omi.me memory list
```

---

## 9. Ntuziaka nchekwa na omume kacha mma

* **Edela igodo n'ime koodu:** Emela commit igodo API (`omi_dev_*`) na Git repository ma ọlị. Jiri faịlụ `.env` dị na `.gitignore` ma ọ bụ ndị njikwa ihe nzuzo dị nchebe.
* **Chebe akụkọ shell:** Na sava ndị a na-ekekọrịta, enyela igodo dị ka argument command-line n'ihu ọha; jiri mbanye mmekọrịta ma ọ bụ `OMI_API_KEY`.
* **Belata ikike folda:** Na Unix/macOS, hụ na folda nhazi nwere ikike amachibidoro:
  ```bash
  chmod 700 ~/.omi
  chmod 600 ~/.omi/config.toml 2>/dev/null || true
  ```
* **Nhicha nnọkọ:** Mgbe ị na-ewepụ gburugburu nwa oge, cheta iwepụ environment variable:
  ```bash
  unset OMI_API_KEY
  ```
