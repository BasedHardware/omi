# omi-cli gyorstalpaló útmutató (Hungarian Quickstart)

> Gyakorlati útmutató az Omi közvetlen terminálos használatához — fejlesztőknek és autonóm MI-ágenseknek (AI agents) tervezve.

Az `omi-cli` a hivatalos parancssori felület az [Omi](https://omi.me) fejlesztői API-hoz. Lehetővé teszi a rendszer 4 alapvető erőforrásának strukturált és automatizálható kezelését: emlékek (memories), beszélgetések (conversations), teendők / feladatok (action items) és célok (goals).

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Hivatalos dokumentáció:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Forráskód:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Telepítés

A függőségi ütközések elkerülése és a CLI-eszköz elszigetelt futtatása érdekében a `pipx` használata ajánlott:

```bash
# Ajánlott: elszigetelt telepítés pipx segítségével
pipx install omi-cli

# Alternatív telepítés szabványos pip használatával (pl. virtuális környezetben)
pip install omi-cli
```

> **Fontos figyelemfelhívás: Csomagnév vs. Parancsnév**
> * A PyPI csomag hivatalos neve: **`omi-cli`** (az `omi` név egy másik, független csomaghoz tartozik).
> * A terminálban futtatandó parancs közvetlenül: **`omi`**.

Ellenőrizze a sikeres telepítést a verzió és a súgó megjelenítésével:

```bash
omi --version
omi --help
```

---

## 2. Hitelesítés (Authentication)

Az `omi-cli` két fő hitelesítési módszert támogat:

| Módszer | Felhasználási terület | Példa parancs |
| :--- | :--- | :--- |
| **Fejlesztői API-kulcs (`omi_dev_*`)** | Automatizálás, CI/CD, headless szerverek, MI-ágensek | `omi auth login --api-key ...` vagy `OMI_API_KEY` |
| **Böngészős OAuth (Google/Apple)** | Helyi munkaállomások és személyes fejlesztői környezet | `omi auth login --browser` (Google) / `--provider apple` |

### Interaktív bejelentkezés
Ha a parancsot kapcsolók nélkül futtatja, egy interaktív választómenü jelenik meg:

```bash
omi auth login
# 1) Browser — Google bejelentkezés böngészőn keresztül (Apple fiókhoz használja a `--provider apple` opciót)
# 2) API key — Az app.omi.me felületen létrehozott fejlesztői API-kulcs beillesztése
```

### Közvetlen böngészős bejelentkezés
```bash
# Alapértelmezett Google bejelentkezés
omi auth login --browser

# Alternatív Apple bejelentkezés
omi auth login --browser --provider apple
```

### Fejlesztői API-kulcs használata
Hozzon létre egy API-kulcsot az [app.omi.me](https://app.omi.me) vezérlőpult **Developer → API Keys** menüpontjában:

```bash
# Kulcs mentése a helyi profilba
omi auth login --api-key omi_dev_...

# Vagy környezeti változóként történő beállítás (ideális konténerekben és CI/CD-ben)
# Megjegyzés: Ha az aktív profilban már létezik mentett kulcs, előbb futtassa az `omi auth logout` parancsot.
export OMI_API_KEY="omi_dev_a_sajat_kulcsa_itt"
```

### Hitelesítési állapot ellenőrzése
* `omi auth status`: Megjeleníti az aktív profilt és a maszkolt azonosítót hálózati kérés nélkül (offline működik).
* `omi auth whoami`: Hitelesített kérést küld az Omi szerverének a hitelesítő adatok érvényességének ellenőrzésére (hálózati kapcsolatot igényel).

```bash
omi auth status
omi auth whoami
```

Kijelentkezés:
```bash
omi auth logout
# Amennyiben OMI_API_KEY környezeti változót használt, törölje azt a munkamenetből (Bash/Zsh: `unset OMI_API_KEY`).
```

---

## 3. Alapvető parancsok

### Emlékek (Memories)
Az Omi által rögzített kontextuális információk és megfigyelések:

```bash
# Mentett emlékek listázása
omi memory list

# Új emlék létrehozása
omi memory create "Technikai és tömör válaszokat részesít előnyben Python példákkal" --category work

# Egy adott emlék részleteinek lekérése
omi memory get <MEMORY_ID>
```

### Beszélgetések (Conversations)
Az Omi eszközök által rögzített beszélgetések és átiratok:

```bash
# Az 5 legutóbbi beszélgetés listázása
omi conversation list --limit 5

# Beszélgetés részleteinek és teljes átiratának lekérése
omi conversation get <CONVERSATION_ID> --include-transcript
```

### Teendők és feladatok (Action Items)
A beszélgetésekből automatikusan felismert és kinyert feladatok:

```bash
# Nyitott feladatok listázása
omi action-item list --open

# Egy feladat elvégzettnek jelölése
omi action-item complete <ACTION_ITEM_ID>
```

### Célok (Goals)
Hosszú távú célkitűzések és haladási mutatók:

```bash
# Aktív célok listázása
omi goal list

# Új numerikus cél létrehozása
omi goal create "Igyál meg napi 2 liter vizet" --type numeric --target 2 --unit liters
```

---

## 4. Strukturált automatizálás és JSON kimenet (`--json`)

Az `omi-cli` teljes támogatást nyújt a szkriptelt automatizáláshoz. A globális `--json` kapcsoló érvényes JSON formátumban jeleníti meg az adatokat:

```bash
# Emlékek lekérése JSON-ben és mezők szűrése jq eszközzel
omi --json memory list | jq '.[] | {id, content, category}'

# A legutóbbi beszélgetések címeinek kinyerése
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# Nyitott feladatok megtekintése nyers JSON formátumban
omi --json action-item list --open | jq '.'
```

> **Fontos szintaktikai szabály:**
> A `--json` kapcsoló **globális opció**, ezért az alparancs **előtt** kell szerepelnie:
> * Helyes: `omi --json memory list`
> * Helytelen: `omi memory list --json`

### Lapozás és fájlba exportálás
Használja a `--limit` és `--offset` opciókat nagyméretű adatállományok lapozásához:

```bash
# Eredmények lapozása
omi --json memory list --limit 25 --offset 0 > emlekek-1-oldal.json
omi --json memory list --limit 25 --offset 25 > emlekek-2-oldal.json
```

A fájlba irányítás létrehozza vagy felülírja a helyi fájlt. Mindig ellenőrizze a parancs sikeres lefutását a kilépési kód segítségével. A hibák a szabványos hibakimenetre (stderr) érkeznek, így egy üres fájl nem garantálja az adatok hiányát. Az exportált fájlok személyes információkat tartalmazhatnak — tárolja őket biztonságosan.

---

## 5. Kilépési kódok (Exit Codes)

Megbízható hibakezelés parancssori szkriptekben és CI/CD folyamatokban:

| Kód | Jelentés | Magyarázat |
| :---: | :--- | :--- |
| `0` | **Sikeres (Success)** | A művelet hibátlanul befejeződött. |
| `1` | **Használati / Validációs hiba** | Érvénytelen adatértékek vagy alkalmazásszintű érvényesítési hiba. |
| `2` | **Hitelesítési / Szintaktikai hiba** | Hiányzó azonosító, lejárt kulcs vagy ismeretlen Click parancssori opciók. |
| `3` | **Szerver- vagy hálózati hiba** | HTTP 5xx válasz, időtúllépés vagy kapcsolódási hiba a szerverhez. |
| `4` | **Kérésszám-korlátozás (Rate Limited)** | HTTP 429 válasz — túl sok kérés rövid időn belül. |
| `5` | **Nem található (Not Found)** | HTTP 404 válasz — a kért erőforrás nem létezik. |

---

## 6. Példák különböző parancssori környezetekhez

### Bash / Zsh (Linux / macOS)
```bash
export OMI_API_KEY="omi_dev_a_sajat_kulcsa_itt"

# Parancs futtatása és kilépési kód ellenőrzése
omi --json memory list --limit 10
if [ $? -ne 0 ]; then
    echo "Hiba történt az emlékek lekérése során." >&2
fi
```

### PowerShell (Windows)
```powershell
$env:OMI_API_KEY = "omi_dev_a_sajat_kulcsa_itt"

# JSON kimenet konvertálása közvetlenül PowerShell objektummá
$memories = omi --json memory list | ConvertFrom-Json
$memories | Select-Object id, content, category

# Hibakezelés a $LASTEXITCODE változóval
if ($LASTEXITCODE -ne 0) {
    Write-Error "Az Omi parancs meghiúsult a következő kóddal: $LASTEXITCODE."
}
```

---

## 7. Helyi asztali alkalmazás API integráció (Local Desktop API)

Ha az Omi Desktop alkalmazás fut a számítógépén, a helyi képernyő- és kontextustörténetet felhős hívások nélkül is lekérdezheti:

```bash
# Helyi végpont konfigurálása és token beállítása
export OMI_LOCAL_API_URL="http://127.0.0.1:47778"
read -r -s -p "Desktop token: " OMI_LOCAL_TOKEN; echo
export OMI_LOCAL_TOKEN

# Helyi szolgáltatás állapotának ellenőrzése
omi --json local status

# Keresés a legutóbbi vizuális idővonalon
omi --json local search-screen "Negyedéves jelentés" --days 7 --app Safari
```

---

## 8. Több profil kezelése (Profiles)

A `--profile` kapcsolóval elkülönítheti személyes fiókjait, munkahelyi környezetét vagy tesztelési végpontjait. A beállítások a `~/.omi/config.toml` fájlban tárolódnak:

```bash
# Személyes profil létrehozása és bejelentkezés
omi --profile personal auth login

# Munkahelyi profil létrehozása és bejelentkezés
omi --profile work auth login

# Parancsok futtatása adott profillal
omi --profile work memory list

# Egyedi tesztkörnyezet használata (staging)
omi --profile staging --api-base https://api.staging.omi.me memory list
```

---

## 9. Biztonság és bevált gyakorlatok

* **Soha ne mentse a kulcsokat Gitbe:** Ne töltsön fel API-kulcsokat nyilvános adattárakba; használjon titokkezelőt vagy `.gitignore` által védett környezeti fájlokat.
* **Parancselőzmények védelme:** Nyilvános vagy megosztott gépeken kerülje a kulcsok közvetlen argumentumként való átadását; használja az interaktív bevitelt vagy az `OMI_API_KEY` környezeti változót.
* **Könyvtár jogosultságok:** Unix-alapú rendszereken korlátozza a `~/.omi/` konfigurációs mappa hozzáférési jogosultságait (`chmod 700 ~/.omi`).
