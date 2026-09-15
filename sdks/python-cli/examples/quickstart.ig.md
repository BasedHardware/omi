# omi-cli — Ntuziaka Mmalite Ngwa Ngwa n'asụsụ Igbo (Igbo Quickstart)

> Ntuziaka bara uru nke na-egosi otu ị ga-esi na-arụ ọrụ na Omi site na ọdụ njedebe (terminal). Emepere ya maka ndị mmepe na ndị odee AI (AI agents).

`omi-cli` bụ ngwa ahịa ahịa dị n'ahịrị iwu (CLI) nke gọọmentị maka API ndị mmepe nke [Omi](https://omi.me). Ọ na-enye gị ụzọ e si achịkwa na mee ka ọ na-aga n'ihu akụkụ anọ bụ isi: nchekwa (memories), mkparịta ụka (conversations), ihe ndị a chọrọ ime (action items), na ebumnuche (goals).

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Akwụkwọ ntuziaka gọọmentị:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Koodu isi mmalite:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Ịwụnye (Installation)

Ha na-atụ aro ka ị jiri `pipx` wụnye ya: ọ na-etinye ngwa ọrụ ahụ n'ọnọdụ dị iche (isolated environment) iji gbozie na ọ gaghị emebi ọrụ ndị ọzọ nke ọrụ gị:

```bash
# Ụzọ a na-atụ aro: ịwụnye ya na pipx
pipx install omi-cli

# Ma ọ bụ na pip nkịtị
pip install omi-cli
```

> **Uche: Aha ngwugwu na aha iwu adịghị ebe.**
> * Aha ngwugwu dị na PyPI bụ **`omi-cli`** (aha `omi` n'onwe ya bụ ọrụ ọzọ na-enweghị njikọ na nke a).
> * Mgbe ịwụnyechara ya, ihe ị na-akpọ na ọdụ njedebe bụ **`omi`**.

Jide na ọ rụrụ ọrụ nke ọma site na ịlele ụdị na menu enyemaka:

```bash
omi --version
omi --help
```

---

## 2. Njirimara (Authentication)

`omi-cli` na-akwado ụzọ abụọ bụ isi iji banye:

| Ụzọ | Oge kachasị mma | Iwu |
| :--- | :--- | :--- |
| **Ego API onye mmepe (`omi_dev_*`)** | Mmepụta oge ochie (automations), CI/CD, sava na-enweghị onyonyo, ndị odee AI | `omi auth login --api-key ...` ma ọ bụ mgbanwe gburugburu (environment variable) |
| **Browser OAuth (Google/Apple)** | Kọmputa onye na-arụ ọrụ na ndị mmepe n'ọnọdụ mpaghara | `omi auth login --browser` (Google) / `--provider apple` |

### Nbanye nke na-ajụ gị (Interactive login)

Ọ bụrụ na ị na-agba ya na-enweghị ihe ọ bụla ọzọ, ọ ga-agwa gị ka ị họrọ ụzọ:

```bash
omi auth login
# 1) Browser — banye site na Google (ma ọ bụ akaụntụ Apple: --provider apple)
# 2) API key —Tinye ego API ị mepere na app.omi.me
```

### Nbanye site na browser kpọmkwem

```bash
# Nbanye Google na-ebu ụzọ
omi auth login --browser

# Ma ọ bụ site na Apple
omi auth login --browser --provider apple
```

### Iji ego API onye mmepe banye

Mepere ego gị na paneli [app.omi.me](https://app.omi.me) n'okpuru **Developer → API Keys**:

```bash
# Debe ego na profaịlụ mpaghara site na iwu
omi auth login --api-key omi_dev_...

# Ma ọ bụ tinye ya dị ka mgbanwe gburugburu (ihe kachasị mma maka konteineri na CI/CD)
# Uche: Ọ bụrụ na etinyela ego na profaịlụ na-arụ ọrụ, gbazie `omi auth logout` mbụ.
export OMI_API_KEY="omi_dev_your_actual_key_here"
```

### Ilele ọnọdụ njirimara

Iwu abụọ a na-enye ozi dị iche iche, ma ekwesịghị ịhazikọta ha:

* `omi auth status` — ọ na-egosi ihe dị **n'ime kọmputa gị (na-enweghị netwọk)**: profaịlụ na-arụ ọrụ, ego ezoro ihe (masked), na oge ị ga-apụ. Ọ anaghị achọ intanet.
* `omi auth whoami` — ọ na-ekwu okwu na **sava Omi**: ọ na-emechi na ego gị rụrụ ọrụ n'ezie. Ọ chọrọ intanet.

```bash
omi auth status
omi auth whoami
```

Iji pụọ n'ọrụ:

```bash
omi auth logout
# Ọ bụrụ na OMI_API_KEY nọ n'ọnọdụ gburugburu, wepụkwa ya ebe ahụ (Bash/Zsh: `unset OMI_API_KEY`).
```

---

## 3. Iwu ndị bụ isi (Basic Commands)

### Nchekwa (Memories)

Ozi ndị dị mkpụmkpụ Omi dere ma chekwaa:

```bash
# Depụta nchekwa echekwara
omi memory list

# Mepere nchekwa ọhụrụ
omi memory create "M na-amasị azịza teknụzụ nkenke nke nwere ihe atụ Python" --category work

# Weta nkọwa zuru oke nke nchekwa a kapịrị ọnụ
omi memory get <MEMORY_ID>
```

### Mkparịta ụka (Conversations)

Ndekọ okwu na mkparịta ụka sitere na ngwaọrụ Omi:

```bash
# Depụta mkparịta ụka kachasị ọhụrụ 5
omi conversation list --limit 5

# Weta nkọwa na ederede zuru ezu nke mkparịta ụka
omi conversation get <CONVERSATION_ID> --include-transcript
```

### Ihe ndị a chọrọ ime (Action Items)

Ọrụ ndị a na-ewepụta na-akpaghị aka site na mkparịta ụka:

```bash
# Depụta ọrụ ndị meghere
omi action-item list --open

# Gụchie ọrụ ọnụ
omi action-item complete <ACTION_ITEM_ID>
```

### Ebumnuche (Goals)

Ọganihu na ebumnuche ogologo oge:

```bash
# Depụta ebumnuche ndị na-arụ ọrụ
omi goal list

# Mepere ebumnuche ọnụọgụ ọhụrụ
omi goal create "Ṅụṍọ mmiri 2L kwa ụbọchị" --type numeric --target 2 --unit liters
```

---

## 4. Ndozigharị na mmepụta JSON (`--json`)

`omi-cli` nwere nkwado dị mma maka ahịrị mmepụta oge ochie (automation pipelines). Tinyere ọkọlọtọ izugbe `--json`, mmepụta na-apụta na ụdị JSON ziri ezi:

```bash
# Depụta nchekwa dị ka JSON ma jiri jq wepu mpaghara
omi --json memory list | jq '.[] | {id, content, category}'

# Weta isi okwu nke mkparịta ụka kachasị ọhụrụ
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# Gosi ihe ndị a chọrọ ime dị ka JSON dị mkpụmkpụ
omi --json action-item list --open | jq '.'
```

> **Iwu dị mkpa:** Ọkọlọtọ `--json` bụ **nhọrọ izugbe** ma ga-esorosị iwu ahụ tupu iwu nta:
> * Ziri ezi: `omi --json memory list`
> * Ezighi ezi: `omi memory list --json`

---

## 5. Koodu ọpụpụ (Exit Codes)

Maka nlele njehie nke ntụkwasị obi na mkparị ụtọ shell na ọrụ CI/CD:

| Koodu Ọpụpụ | Ọ pụtara gịnị | Nkọwa |
| :---: | :--- | :--- |
| `0` | **Ihe ịga nke ọma** | Ọrụ ahụ gwụchara na-enweghị njehie. |
| `1` | **Njehie ojiji (Njehie nyocha)** | Uru ezighi ezi ma ọ bụ njehie nyocha ngwa; njehie mkparị ụtọ Click na-agba koodu `2`. |
| `2` | **Njehie njirimara / mkparị ụtọ CLI** | Anaghị ekenye njirimara, ego ejikọtala, ma ọ bụ nhọrọ Click amabeghị. |
| `3` | **Njehie sava / netwọk** | Nzaghachi HTTP 5xx, nkwụsị oge (timeout), ma ọ bụ enweghị ike iru sava. |
| `4` | **Ọsọ ọnụego gafere (Rate Limited)** | HTTP 429 — arịrịọ ahụ gafere oke ọsọ ọnụego. |
| `5` | **Ọ dịghị (Not Found)** | HTTP 404 — ihe a chọrọ adịghị. |

---

## 6. Nlereanya site na gburugburu shell (Shell Examples)

### Bash / Zsh (Linux / macOS)

```bash
# Kọwaa ego API maka nnọkọ a
export OMI_API_KEY="omi_dev_your_actual_key_here"

# Gbaa iwu ma lee koodu ọpụpụ anya
omi --json memory list --limit 10
if [ $? -ne 0 ]; then
    echo "Enweghị ike ịjụ nchekwa onye ọrụ." >&2
fi
```

### PowerShell (Windows)

```powershell
# Kọwaa mgbanwe gburugburu ego API
$env:OMI_API_KEY = "omi_dev_your_actual_key_here"

# Gbanwee mmepụta JSON ka ọ bụrụ ihe PowerShel nke ọma
$memories = omi --json memory list | ConvertFrom-Json

# Jiri $LASTEXITCODE lele njehie
if ($LASTEXITCODE -ne 0) {
    Write-Error "Iwu omi dara site na koodu $LASTEXITCODE."
}
```

---

## 7. Njikọ API Desktop Obodo (Local Desktop API)

Mgbe ngwa Omi Desktop na-arụ ọrụ na kọmputa gị, ị nwere ike jụọ ntinye na ihe ọmụma mpaghara na-enweghị igwu ojii (cloud):

```bash
# Hazie njedebe mpaghara (jiri mgbanwe gburugburu chebe ego)
export OMI_LOCAL_API_URL="http://127.0.0.1:47778"
read -r -s -p "Desktop token: " OMI_LOCAL_TOKEN; echo
export OMI_LOCAL_TOKEN

# Lele ọnọdụ njikọ mpaghara
omi --json local status

# Chọọ na oge ntule ihuenyo kachasị ọhụrụ
omi --json local search-screen "Akụkọ ọnwa" --days 7 --app Safari
```

---

## 8. Nchịkwa ọtụtụ profaịlụ (Profiles)

Gbanwee n'etiti akaụntụ onwe na ọrụ, ma ọ bụ gburugburu nyocha, site na `--profile`. Ntọala na-anọgidere na `~/.omi/config.toml`:

```bash
# Mepere profaịlụ onwe ma banye
omi --profile personal auth login

# Profịlụ ọrụ
omi --profile work auth login

# Gbaa iwu n'okpuru profaịlụ kapịrị ọnụ
omi --profile work memory list

# Profi nyocha na njedebe API ọzọ
omi --profile staging --api-base https://api-staging.omi.me memory list
```

---

## 9. Nchekwa na Omume Kachasị Mma (Security Best Practices)

* **Elaela itinye ego API n'ime ebe nchekwa koodu (git repo):** jiri ndị njikwa nzuzo ma ọ bụ faịlụ `.env` nke `.gitignore` kpuchiri.
* **Akụkọ ihe mere eme shell:** n'ime kọmputa ndị a na-ekerịta, elaa ịnye ego ozugbo dị ka arụmụka ahịrị iwu; jiri nbanye mmekọrịta ma ọ bụ `OMI_API_KEY`.
* **Ikike nke ndekọ:** gbochie ikike nke ndekọ nhazi `~/.omi/` na sistemụ Unix (`chmod 700 ~/.omi`).
