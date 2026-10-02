# Első lépések az omi-cli használatával

Ez az útmutató az első parancsokat ismerteti magyar nyelven. A parancsok nevei
és a program üzenetei angol nyelvűek maradnak. Az itt bemutatott lekérdezési
példák nem módosítják az emlékeit, beszélgetéseit, feladatait vagy céljait.

## A program telepítése

Követelmények: Python 3.10 vagy újabb verzió és egy Omi-fiók.

Ha telepítve van a `pipx`:

```sh
pipx install omi-cli
omi --help
```

Alternatív megoldásként telepítheti egy aktivált virtuális Python-környezetbe
(virtual environment):

```sh
python -m pip install omi-cli
omi --help
```

Ha a terminál nem találja az `omi` parancsot, ellenőrizze, hogy a virtuális
környezet aktív-e, vagy hogy a könyvtár, ahová a `pipx` telepíti a futtatható
fájlokat, szerepel-e a `PATH` változóban.

## Fiók csatlakoztatása

Indítsa el az interaktív varázslót:

```sh
omi auth login
```

Válassza a böngészőn keresztüli bejelentkezést, vagy illesszen be egy Omi
fejlesztői API-kulcsot. Az interaktív bevitel elrejti a kulcsot; ne írja be olyan
parancsba, amely megmarad a terminál előzményeiben.

Közvetlenül a böngésző megnyitásához:

```sh
omi auth login --browser
```

Jelentkezzen be ugyanazon a számítógépen, amelyen a terminál fut: a hitelesítési
válasz helyi címet használ. Kövesse a képernyőn megjelenő utasításokat.

Ezután ellenőrizze a konfigurációt és az API-hozzáférést:

```sh
omi auth status
omi auth whoami
```

A `status` a helyi állapotot mutatja és elrejti a titkot, de nem ellenőrzi annak
érvényességét a szerveren. A `whoami` hitelesített kérést hajt végre; siker esetén
megerősíti a hitelesítő adatok működését anélkül, hogy feltétlenül megjelenítené a nevét.

A konfiguráció alapértelmezés szerint a `~/.omi/config.toml` fájlba kerül mentésre.
Ne ossza meg ezt a fájlt másokkal: bizalmas hitelesítési adatokat tartalmazhat.

## Az adatok megtekintése

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Az üres lista egyszerűen azt jelentheti, hogy nincsenek a lekérdezésnek megfelelő
elemek. Használja a súgót az egyes parancsok szűrőinek megismeréséhez:

```sh
omi memory list --help
omi action-item list --help
```

## JSON kimenet és lapozás az oldalak között

Helyezze a globális `--json` opciót a parancscsoport **elé**:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Az első parancs az első 25 emléket kéri le; a második a következő 25-öt. Egyetlen
oldal tehát nem jelent teljes biztonsági másolatot (backup). A JSON kimenet megőrzi
a teljes azonosítókat, míg a képernyőn látható táblázatok lerövidíthetik őket a megjelenítéshez.

Oldal mentése fájlba:

```sh
omi --json memory list --limit 25 --offset 0 > emlekek-oldal-1.json
```

Ez az átirányítás létrehozza vagy felülírja a helyi fájlt. Ellenőrizze, hogy a
parancs sikeresen lefutott-e a tartalom felhasználása előtt. A hibák a hibakimenetre
(stderr) íródnak; az üres fájl nem garantálja, hogy nincsenek adatok. Az exportált
fájl személyes adatokat tartalmazhat: tartsa bizalmasan.

## Kijelentkezés (Logout)

```sh
omi auth logout
```

Ez a parancs törli a helyileg tárolt hitelesítő adatokat. Egy kulcs szerveroldali
visszavonásához használja a fejlesztői kulcsok kezelését a fiókjában.

A többi parancsért és a speciális beállításokért tekintse meg az
[angol nyelvű fő útmutatót](../README.md) és futtassa az `omi --help` parancsot.
