# omi-cli — gid demaraj rapid an kreyòl ayisyen

> Gid pratik pou travay avèk Omi depi nan tèminal ou. Apwopriye pou devlopè imen ak ajan entèlijans atifisyèl (AI).

`omi-cli` se kliyan liy kòmand ofisyèl pou API devlopè [Omi](https://omi.me).
Li ba ou aksè rapid ak fasil pou ekri script pou kat resous prensipal Omi yo:
souvni (memories), konvèsasyon (conversations), aksyon pou fè (action items), ak objektif (goals).

* **PyPI :** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Dokimantasyon :** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Kòd sous :** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Enstalasyon

Metòd nou rekòmande a se `pipx` : li enstale zouti a nan yon anviwònman izole,
pou depandans li yo pa antre an konfli ak lòt pwojè Python sou machin ou.

```bash
# rekòmande : enstalasyon ak pipx
pipx install omi-cli

# oswa avèk pip nòmal
pip install omi-cli
```

> **Enpòtan : non pakè a ak non kòmand lan diferan.**
> * Pakè w ap enstale a rele **`omi-cli`** (pakè `omi` a se yon lòt pwojè diferan).
> * Apre enstalasyon an, kòmand ou egzekite nan tèminal la se **`omi`**.

Verifye tout bagay ap mache byen :

```bash
omi --version
omi --help
```

---

## 2. Otantifikasyon

`omi-cli` sipòte de fason pou konekte.

| Metòd | Pi bon pou | Kòmand |
| :--- | :--- | :--- |
| **Kle Devlopè (`omi_dev_*`)** | CI/CD, script otomatik, ajan AI | `omi auth login --api-key ...` oswa varyab anviwònman |
| **Koneksyon Navigatè (Google/Apple)** | Lè w ap travay sou pwòp òdinatè w | `omi auth login --browser` |

### Koneksyon entèaktif

Si w pa mete okenn opsyon, kòmand lan ap mande w ki metòd ou vle chwazi :

```bash
omi auth login
# 1) Browser — koneksyon ak Google oswa Apple (fasil pou moun)
# 2) API key — kole kle devlopè ou pran sou app.omi.me (ideyal pou ajan ak script)
```

Si w chwazi kle API a, tèks w ap tape a ap kache pou kle a pa rete nan istwa tèminal la.

### Dirèkteman nan navigatè

```bash
omi auth login --browser
```

### Avèk yon kle devlopè

Ou ka jwenn kle devlopè w sou [app.omi.me](https://app.omi.me) nan seksyon **Developer → API Keys**.

```bash
# anrejistre kle a nan konfigirasyon lokal la
omi auth login --api-key omi_dev_...

# oswa pase li kòm varyab anviwònman — pi bon pou CI/CD ak Docker/kontenè
export OMI_API_KEY=omi_dev_...
```

Lè varyab anviwònman `OMI_API_KEY` la defini, li pèmèt ou itilize CLI a san ou pa bezwen ekri anyen sou disk la.
Si gen yon kle ki deja anrejistre nan pwofil la, li gen priyorite sou varyab anviwònman an.

### Verifye koneksyon an

Gen de kòmand diferan pou enspekte idantite w :

* `omi auth status` — montre sa ki anrejistre **lokalman** : pwofil aktif, kle maske, ak dat ekspirasyon. Li mache menm si w pa gen entènèt.
* `omi auth whoami` — fè yon apèl **sou sèvè Omi a** pou verifye si kle a valab toutbon. Li mande koneksyon entènèt.

```bash
omi auth status    # enspeksyon lokal, san entènèt
omi auth whoami    # verifikasyon an dirèk sou sèvè a
```

---

## 3. Kat Resous Prensipal yo

Chak resous gen kòmand estanda pou lis, kreye, gade, ak efase.

### Souvni (Memories)

Souvni yo se nòt ak enfòmasyon Omi kaptire pou ou.

```bash
# afiche dènye souvni yo
omi memory list

# limite kantite rezilta yo
omi memory list --limit 5

# kreye yon nouvo souvni manyèlman
omi memory create "Mwen gen yon reyinyon enpòtan lendi a 10è nan maten."

# filtre souvni w yo avèk jq
omi --json memory list | jq '.[] | select(.content | contains("reyinyon"))'

# gade detay yon souvni espesifik
omi memory get <memory_id>

# efase yon souvni
omi memory delete <memory_id>
```

### Konvèsasyon (Conversations)

Konvèsasyon yo genyen transkripsyon odyo ak rezime estriktire.

```bash
# afiche lis konvèsasyon yo
omi conversation list

# afiche lis konvèsasyon ak tout transkripsyon an
omi conversation list --include-transcript

# gade yon konvèsasyon an detay
omi conversation get <conversation_id>
```

### Aksyon pou fè (Action Items)

Tache ak devwa ki soti nan konvèsasyon w yo.

```bash
# afiche aksyon ki poko fèt yo sèlman
omi action-item list --open

# afiche aksyon ki fini deja yo
omi action-item list --completed

# kreye yon nouvo aksyon
omi action-item create "Voye imèl rapò finansye a bay ekip la"

# make yon aksyon kòm fini
omi action-item complete <item_id>

# efase yon aksyon
omi action-item delete <item_id>
```

### Objektif (Goals)

Objektif pèsonèl oswa pwofesyonèl ou swiv ak Omi.

```bash
# afiche lis objektif ou yo
omi goal list

# kreye yon nouvo objektif
omi goal create "Fè egzèsis fizik 3 fwa pa semèn"

# gade detay yon objektif
omi goal get <goal_id>
```

---

## 4. Travay ak JSON ak `jq`

Pou entegrasyon nan script, zouti CI/CD, oswa ajan AI, mete drapo `--json` anvan kòmand lan pou resevwa rezilta nan fòma JSON pwòp :

```bash
# sonje mete --json anvan resous la
omi --json memory list | jq '.[].content'

# filtre aksyon ki poko fèt yo
omi --json action-item list | jq '.[] | select(.completed == false) | .description'

# ekstrè id dènye konvèsasyon an
LAST_CONV_ID=$(omi --json conversation list --limit 1 | jq -r '.[0].id')
echo "Dènye konvèsasyon: $LAST_CONV_ID"
```

---

## 5. Tablo Kòd Sòti (Exit Codes)

Lè w ap ekri script, kòd sòti a pèmèt ou konnen egzakteman si kòmand lan reyisi oswa poukisa li echwe :

| Kòd | Siyifikasyon | Deskripsyon |
| :--- | :--- | :--- |
| `0` | **Siksè** | Kòmand lan egzekite san okenn pwoblèm. |
| `1` | **Erè Itilizasyon** | Validasyon omi-cli (egzanp: agiman manke, opsyon envalid, stdin vid). |
| `2` | **Erè Otantifikasyon** | Kle API manke, pa valab, oswa sesyon an ekspire. |
| `3` | **Erè Sèvè / Rezo** | Repons 5xx, koneksyon koupe, oswa tan delè (`timeout`). |
| `4` | **Twòp Rekèt** | 429 Too Many Requests (depase limit vitès). |
| `5` | **Resous Pa Jwenn** | 404 Not Found, idantifyan an pa egziste nan sistèm nan. |

---

## 6. Egzanp Script

### Bash / Zsh (Linux & macOS)

```bash
#!/usr/bin/env bash
set -euo pipefail

echo "=== Verifikasyon Otantifikasyon Omi ==="
if ! omi auth whoami > /dev/null 2>&1; then
    echo "Erè: Ou bezwen konekte anvan. Kouri 'omi auth login'." >&2
    exit 2
fi

echo "Koneksyon reyisi!"
echo "Ap chèche aksyon ki poko fèt..."

TASKS=$(omi --json action-item list)
COUNT=$(echo "$TASKS" | jq 'length')

echo "Ou genyen $COUNT aksyon aktif."
```

### PowerShell (Windows)

```powershell
$ErrorActionPreference = "Stop"

Write-Host "=== Verifikasyon Omi CLI ==="
omi auth whoami | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Error "Erè otantifikasyon: Tanpri konekte avèk 'omi auth login'."
    exit $LASTEXITCODE
}

$rawJson = omi --json memory list --limit 3
$memories = $rawJson | ConvertFrom-Json

foreach ($mem in $memories) {
    Write-Host "• $($mem.content)"
}
```

---

## 7. Entegrasyon ak Desktop API Lokal

Si w gen aplikasyon Omi Desktop ki louvri sou òdinatè w, li bay yon API lokal sou pòt `47778` :

```bash
# konfigire adrès ak siy lokal la
omi local configure --url http://127.0.0.1:47778 --token SIY_LOKAL_OU_A

# verifye si aplikasyon an ap reponn
omi --json local status

# lis zouti lokal ki disponib yo
omi --json local tools
```

---

## 8. Jesyon Pwofil ak Sekirite

Ou ka separe konfigirasyon travay ak pèsonèl avèk pwofil :

```bash
# kreye oswa itilize yon pwofil espesifik
omi config profile use travay
omi auth login --api-key omi_dev_travay...

# kouri yon kòmand sou yon lòt pwofil san chanje pwofil aktif la
omi --profile pesonel memory list
```

### Sekirite Konfigirasyon

Fichye konfigirasyon lokal la gen kle sekrè w yo nan `~/.omi/config.toml`. Asire w ke lòt itilizatè sou sistèm nan pa ka li l :

```bash
chmod 700 ~/.omi
chmod 600 ~/.omi/config.toml
```
