# Siaki muamua mo omi-cli

Ko e tohi fakahinohino ko ʻení ʻokú ne fakamatalaʻi ʻa e ngaahi fekau ʻuluakí ʻi he lea fakatonga.
Ko e ngaahi hingoa ʻo e fekaú mo e ngaahi popoaki ʻa e polokalamá ʻoku kei ʻi he lea fakapālangí pē.
Ko e ngaahi sīpinga fehuʻi hení ʻoku ʻikai ke ne liliu hoʻo ngaahi manatu, pōtalanoa, ngāue, pe taumuʻa.

## Fokotuʻu ʻo e polokalamá

Ngaahi fiemaʻu: Python 3.10 pe foʻou ange mo ha ʻakauni Omi.

Kapau kuo fokotuʻu hoʻo `pipx`:

```sh
pipx install omi-cli
omi --help
```

ʻE lava foki ke fokotuʻu ia ʻi ha ʻātakai fakakomipiuta (virtual environment) ʻi he Python:

```sh
python -m pip install omi-cli
omi --help
```

Kapau ʻoku ʻikai ke ʻilo ʻe he teminolo (terminal) ʻa e `omi`, fakapapauʻi ʻoku ngāue
ʻa e ʻātakai fakakomipiutá pe ʻoku ʻi hoʻo meʻa fakafeʻauaki `PATH` ʻa e faile ʻa e `pipx`.

## Fakafehokotaki hoʻo ʻakauní

Kamata ʻa e tokoni fetuʻutakí:

```sh
omi auth login
```

Fili ke hū ʻi he meʻa fakakomipiuta (browser) pe fakapipiki ha kī API fakatupulekina Omi.
ʻOku fufū ʻe he meʻa hū fakahangatonú ʻa e kií; fakaʻehiʻehi mei hono taipeʻi ia ʻi ha
fekau ʻe lava ke toe ʻi he hisitōlia ʻo e teminoló.

Ke ʻalu hangatonu ki he meʻa kumi ʻi he initanetí:

```sh
omi auth login --browser
```

Hū ʻi he komipiuta tatau pē ʻoku lele ai ʻa e teminoló: ʻoku ngāueʻaki ʻe he tali fakapapauʻí
ha tuʻasila fakalotofonua. Muimui ki he ngaahi fakahinohino ʻi he laú.

Hili iá, fakapapauʻi ʻa e fokotuʻutuʻú mo e hū ki he API:

```sh
omi auth status
omi auth whoami
```

ʻOku fakahā ʻe he `status` ʻa e tuʻunga fakalotofonuá pea fufū ʻa e meʻa liló, ka ʻoku
ʻikai ke ne siviʻi ʻa e totonú ʻi he sevá. ʻOku ʻave ʻe he `whoami` ha kole fakapapauʻi;
kapau ʻe lavameʻa, ʻokú ne fakapapauʻi ʻoku ngāue ʻa e tohi fakamoʻoní taʻe fiemaʻu ke fakahā ho hingoá.

ʻOku faʻa tauhi maʻu pē ʻa e fokotuʻutuʻú ʻi he `~/.omi/config.toml`. ʻOua te ke vahevahe
ʻa e faile ko ʻení: ʻe lava ke ʻi ai hoʻo ngaahi fakamatala fufū.

## Kumi hoʻo ngaahi fakamatalá

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Ko ha lisi mahafo e lava pe ke ʻuhinga ia ʻoku ʻikai ha ngaahi meʻa ʻoku feʻunga mo e fehuʻí.
Ngāueʻaki ʻa e tokoní ke sio ki he ngaahi meʻa sivi ki he fekau kotoa pē:

```sh
omi memory list --help
omi action-item list --help
```

## Maʻu ʻa e JSON mo e kumi peesi

Fokotuʻu ʻa e fili fakalūkufua `--json` **ʻi muʻa** ʻi he kulupu fekaú:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

ʻOku kole ʻe he fekau ʻuluakí ʻa e ʻuluaki manatu ʻe 25; ko e uá ki he 25 hoko maí.
Ko ia ai, ko ha peesi ʻe taha ʻoku ʻikai ko ha tatau fakahaofi kakato ia (backup). ʻOku
tauhi maʻu ʻe he JSON ʻa e ngaahi ID kakató, ka e lava ke fakasiʻisiʻi ia ʻe he ngaahi tēpilé.

Ke tauhi ha peesi ʻi ha faile:

```sh
omi --json memory list --limit 25 --offset 0 > manatu-peesi-1.json
```

ʻOku fakatupu pe toe tohi ʻe he liliu ko ʻení ʻa e faile fakalotofonuá. Fakapapauʻi naʻe
ʻosi lelei ʻa e fekaú taʻe ʻi ai ha fehalaʻaki kimuʻa pea ngāueʻaki ʻa e meʻa ʻi lotó.
ʻOku tohi ʻa e ngaahi fehalaʻakí ki he halanga fehalaʻaki (stderr); ʻoku ʻikai fakapapauʻi
ʻe ha faile mahafo ʻoku ʻikai ha fakamatala. ʻE lava ke kau ʻi he faile kuo ʻavé ha ngaahi
fakamatala fakafoʻituitui: tauhi fufū ia.

## Hū ki tuʻa (Logout)

```sh
omi auth logout
```

ʻOku toʻo ʻe he fekau ko ʻení ʻa e ngaahi tohi fakamoʻoni naʻe tauhi fakalotofonuá. Ke
fakangata ha kī ʻi he sevá, ngāueʻaki ʻa e puleʻi ʻo e ngaahi kī fakatupulekiná ʻi hoʻo ʻakauní.

Ki he ngaahi fekau kehé mo ha ngaahi fili lahi ange, vakai ki
[he tohi fakahinohino tefito ʻi he lea fakapālangí](../README.md) mo e `omi --help`.
