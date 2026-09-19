# Qalltawi omi-cli tuqita

Aka yatichawixa nayrïr kamachinakwa Aymar aruta qhanañchi. Kamachinakan sutinakapasa
ukatxa yatiyawinakapasa Inlis arunskakiwa. Aka yant'awinakaxa janiw amtanakama,
aruskipäwinakama, lurañanakama, jan ukax amtäwinakama mayjt'aykiti.

## Wakichäwi uskuña (Instalar)

Muntanaka: Python 3.10 jan ukax machaqapampi ukat Omi akauntu.

Sitis `pipx` utjtam:

```sh
pipx install omi-cli
omi --help
```

Ukhamaraki mä kikiptata pachanxa (virtual environment) uskusispawa:

```sh
python -m pip install omi-cli
omi --help
```

Sitis terminalaxa `omi` jan jikxatkchixa, qhawqhatï `PATH` ukanx `pipx` jan ukax virtual environment ch'amanchataxiti uka uñjam.

## Akauntumaru chint'aña

Mä aruskipiri yanapirampi qalltaña:

```sh
omi auth login
```

Browser tuqit mantäwix jan ukax Omi lurt'iripan API llavepampi uskuntäwi ajllim.
Aka mantäwixa llavima imantapxiwa; janiw kamachinakat qillqañakiti terminal nayra qillqatanakapar qhipartañapataki.

Browser tuqiru chiqak sarañataki:

```sh
omi auth login --browser
```

Kawkïr computadortï terminal luraski ukar mantam. Screen ukan yatiyawinakaparu arkam.

Ukatsti, askichäwinaka ukat API mantäwi uñakipam:

```sh
omi auth status
omi auth whoami
```

`status` uñacht'ayiwa uka chiqan kamachitapa ukat imantatanaksa imiwa. `whoami` llavenakax askit irnaqaskatap uñanchayi.

Askichäwinakax `~/.omi/config.toml` ukan imatawa. Jan khitirus aka archivo churamti, imantat llavenakaniwa.

## Datam uñakipaña

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Ch'usa listax janiw kuns jikxatkiti sañ muniwa. Yanapa apnaqam yaqha uñakipäwinak yatxatañataki:

```sh
omi memory list --help
omi action-item list --help
```

## JSON apsuña ukat laphanaka saraña (Pagination)

Taqpacha `--json` churäwi **nayraqataru** uskuntam kamachi tantachäwita:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Nayrïr kamachixa 25 amtanakawa mayi; payïrix jutïr 25 mayi. JSON taqpach ID imi.

Mä lapha archivoru imañataki:

```sh
omi --json memory list --limit 25 --offset 0 > amtanaka-lapha-1.json
```

Aka archivox qullqi/ch'ikhi juman datanakaniñaspawa: sum imantata apnaqam.

## Mistsuña (Logout)

```sh
omi auth logout
```

Aka kamachixa computadorman imat llavenakwa chhaqtayi. Server tuqita llav chhaqtayañatakixa, akauntumana lurt'iri llavenaka uñakipäwir mantam.

Yaqha kamachinakataki, [Inlis arun jach'a yatichawi](../README.md) ukat `omi --help` uñjam.
