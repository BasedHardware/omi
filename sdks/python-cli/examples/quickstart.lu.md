# Kutangila kabipi ne omi-cli

Eyilondolola lyena bapangishi bensoni mu Kiluba. Maina a bapangishi ne binyumelo
bya programu bikangana mu Kingereza. Bapangishi bensoni abo awabingisha kaya
kupusha makumbusho anyu, misambwidio, bintu bya bya kubanga, pano malimo anyu.

## Kubika programu

Bulenga: Python 3.10 pano mpya ne account wa Omi.

Nga `pipx` waishibikwa:

```sh
pipx install omi-cli
omi --help
```

Pano bikibika mu Python virtual environment eyaishibikwa:

```sh
python -m pip install omi-cli
omi --help
```

Nga terminal taitabula `omi`, mona neba virtual environment ikilimine pano
directory omo `pipx` ibikila executables ili mu `PATH`.

## Kusabukilisha account yenu

Tangisha guide wa kubungangana:

```sh
omi auth login
```

Sala kulangana ne browser pano kubikisha API key ya developer ya Omi. Kubikisha
kubungangana kufisa key; musuleka kuibika mu bapangishi abobikilwe mu mbiro
ya terminal.

Pogupesha browser ne kalolo:

```sh
omi auth login --browser
```

Langana pamshini umo-mo ne terminal kabanshi kubikisho kabikisha anwani ya
callback ya ndani. Landisha makanda omoneshe pamata.

Pashita kulangana, langa configuration ne API access:

```sh
omi auth status
omi auth whoami
```

`status` ibonesha bintu bya ndani ne kufisa mafiso, neboi taikona kuziba ku
server. `whoami` ilombola demmande eyakabikwe; nga iyamana, credentials anyu
bafwana, neba bataila izina lyenu.

Configuration ibikilwa mu `~/.omi/config.toml` ne default. Musubatileni ile
faili — ilenga kubika credentials.

## Kubalenga data yenu

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

List ya bwanga ilenga kuba neba kakaba kantu kashibikisha filter. Mona
options bya cila capangishi mu help:

```sh
omi memory list --help
omi action-item list --help
```

## Kupoka JSON ne kubalenga mapape

Bika option ya `--json` **tanga** bapangishi group:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Capangishi ca kumbele cilombola makumbusho 25 a kumbele; ca bubidi cilombola
25 alombelo. Papa umo tabuli backup ya mujima. JSON output ibikila ID mujima,
neboi table ilenga kufupisha ID kuboneka.

Pobikila papa umo mu faili:

```sh
omi --json memory list --limit 25 --offset 0 > memory-papa-1.json
```

Redirect ibika pano ipusula faili ya ndani. Mona neba capangishi cayamanine
kaleba bangebikisha muntu. Erreur ibikilwe mu stderr; faili ya bwanga
taitabula neba data kayaba. Faili ya export ilenga kubika makanda ya muntu —
ibikila private.

## Kubikisha profiles

State ibikilwa mu `~/.omi/config.toml` (ilenga kupusulwa ne `$OMI_CONFIG`).
Cila profile ikwete nzila yakabika yakabika ne anwani ya API. Pusula profile
ne `--profile`:

```sh
omi config profile use mulimo
omi auth login
omi --profile private memory list
```

Bapangishi ba configuration ba kanshi:

```sh
omi config show
omi config path
omi config profile list
```

## Exit codes

Exit codes eyi ba stable ne baifa ku scripts pano agents:

| Code | Musaba | Exemple |
| ---: | --- | --- |
| 0 | yamana | Capangishi caimana |
| 1 | bulenbo bwa kubikisha | flag ya bubi, argument ikabuli, pano validation tayamani |
| 2 | bulenbo bwa kubika | credentials kayaba, token yipina pano permission ikabuli |
| 3 | bulenbo bwa server | server 5xx pano connection tayamani |
| 4 | kaba rate | server ipele HTTP 429 |
| 5 | taishibiki | server ipele HTTP 404 |

## Kupwangela

```sh
omi auth logout
```

Ikusula credentials ibikilwe ndani. Pokupusula key ku server, bikisha
gouvernement ya developer key mu account yenu.

Po bapangishi ne options bingi, mona [main README ya Kingereza](../README.md)
ne tangisha `omi --help`.
