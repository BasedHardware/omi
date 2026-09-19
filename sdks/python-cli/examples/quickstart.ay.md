# omi-cli qalltaña

Aka yatichäwix Aymara arut nayrïr kamachinak uñacht'ayi. Kamachinakan sutinakapax ukat apanawix Inlis arunskaniwa. Aka uñt'ayatanakax janiw amtanakamx, aruskipäwinakamx, lurañanakamx jan ukax amtäwinakamx mayjt'aykaniti.

## Wakichäwi uñstayaña

Wakisi: Python 3.10 jan ukax machaq uñstata ukat Omi cuenta.

> Amuyt'añataki: PyPI ukan paqueten sutipax **`omi-cli`** ukhamawa, kamachix uñstayatampixa **`omi`** ukhamawa. PyPI ukanx yaqha jan uñt'at `omi` sutin paquetiw utji — janiw uk uñstayapxamti.

`pipx` uñstayatächi ukhaxa:

```sh
pipx install omi-cli
omi --help
```

Yaqha tuqitxa, mä irnaqir Python virtual environment taypinxa:

```sh
python -m pip install omi-cli
omi --help
```

Terminalax `omi` jan jikxatki ukhaxa, virtual environment irnaqaskatap ukat `pipx` directoriox `PATH` ukan utjatap uñjapxam.

## Cuentamat mayachthapiña

Qalltañataki yanapiri:

```sh
omi auth login
```

Navegador taypi mantañ ajllipxam, jan ukax Omi yatichirin API llavip ch'uqt'añ ajllipxam. Aka luräwix llav imiwa; janiw llav terminal nayra lurañanakapax qillqt'apxamti.

Navegador taypi chiqak mantañatakixa:

```sh
omi auth login --browser
```

Terminal irnaqki uka kikpa computadoran mantäw phuqhachapxam, chiqanchäwix aka chiqarux kutt'anitapatawa. Pantallan qillqatanakarjam lurapxam.

Ukatsti, configuracionampi ukat API mantäwimpi uñjapxam:

```sh
omi auth status
omi auth whoami
```

`status` chiqan askinjäwip uñacht'ayi ukat imatanak imiwa, ukampis janiw serverampix chiqanchkiti. `whoami` iyawsat mayïw apayi; askinjäwixa chimpunakamax sum irnaqatap uñacht'ayi.

Configuracionax `~/.omi/config.toml` ukan imataskiwa. Janiw aka archivox yaqhanakampi uñt'ayapxamti, juman ch'axwata chimpunakaniwa.

## Yatiyäwinakamat uñjaña

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Mä ch'usa lista uñstayatax janiw mayïwimarjam yatiyäwi utjatap sañ munkiti. Kamachin suyt'awinakap yatxatañatakixa, yanap uñjapxam:

```sh
omi memory list --help
omi action-item list --help
```

## JSON katuqaña ukat pankanaka uñjaña

Aka taqpach option `--json` kamachinak nayraqatar uskkapxam:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Nayrïr kamachix nayrïr 25 qillqatanak mayi; payïrix jutïr 25 mayi. Ukhamaxti mä pankax janiw taqpach copia kankiti. JSON mistuwix taqpach sutinak katuqi, ukampis tablas ukax jisk'aptayaspawa.

Mä panka archivon imañatakixa:

```sh
omi --json memory list --limit 25 --offset 0 > amtanaka-panka-1.json
```

Aka mayjt'ayäwix mä local archiv lurayasi jan ukax mayjt'ayi. Manqh uñnaqiripampi apnaqañ nayraqatax, kamachix sum mistutap uñjapxam. Pantjatanakax stderrukaruw qillqasi; mä ch'usa archivox janiw yatiyäwinakax jan utjatapatakikiti. Aka archivo sum imapxam, juman sutinakamaniwa.

## Mistsuñataki (Log out)

```sh
omi auth logout
```

Aka kamachix aka chiqan imat chimpunak qhollphi. Serveran mä llav apaqatäñapatakixa, cuentaman yatichirin llav apnaqiripampiw apnaqapxam.

Yaqha kamachinakatakixa ukat juk'amp askinak yatxatañatakixa, Inlis arut nayrïr yatichäwi uñjapxam:
[../README.md](../README.md) ukat `omi --help`.
