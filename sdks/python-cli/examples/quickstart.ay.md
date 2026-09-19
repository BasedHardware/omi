# Nayrïr Jamuqanaka omi-cli ukampi

Aka yatichäwix nayrïr kamachinakxat Aymar arut qhanañchi. Kamachinakan sutipampi
programa tuqit yatiyawinakax Ingris arunw qhiparaski. Aka yant'äwinakax janiw
amtawinakam, aruskipäwinakam, lurañanakam, jan ukax amtäwinakam mayjt'aykiti.

## Programa uchantaña (Instalación)

Wakisiwa: Python 3.10 jan ukax machaqapampi, ukat mä Omi cuenta.

`pipx` utjsta ukhaxa:

```sh
pipx install omi-cli
omi --help
```

Ukatsti mä virtual environment Python ukanx uchantarakiñawa:

```sh
python -m pip install omi-cli
omi --help
```

## Cuentamamp chikt'ayaña

Login yanapir qalltañani:

```sh
omi auth login
```

Browser tuqi jan ukax Omi API key uchatasa mantasmawa.

Directo browser-ru sarañataki:

```sh
omi auth login --browser
```

Ukatsti, API apnaqaw uñakipma:

```sh
omi auth status
omi auth whoami
```

`~/.omi/config.toml` ukanx wakichäwix imataskiwa. Janiw khitis aka archivo churañati.

## Yatiyawinakam uñjaña

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

## JSON apsuña ukat laphanak uñjaña

`--json` ukax kamachi **nayraqat** uchaña:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Mä laph archivo-ru imañataki:

```sh
omi --json memory list --limit 25 --offset 0 > amtawi-lapha-1.json
```

## Mistuña (Logout)

```sh
omi auth logout
```

Juk'amp yatxatañatakix [Ingris yatichäwi](../README.md) uñxatt'ma.
