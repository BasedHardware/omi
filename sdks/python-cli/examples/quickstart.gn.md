# Ñepyrũ omi-cli ndive

Ko kuatia ombohechauka omi-cli rembiporu ñepyrũva avañe'ẽme. Ñe'ẽmandu'apy réra ha programa ñe'ẽmondo oĩ gueteri ingyaterrañe'ẽme. Ko kuatia mba'ekuéra ndoñemoambuei nde mandu'apy, nde ñomongeta, nde tembiapo térã nde jehupytyrã.

## Mohenda

Reikotevẽ Python 3.10 térã pyahuve, ha peteĩ Omi mba'éva.

Péina `pipx` oĩramo:

```sh
pipx install omi-cli
omi --help
```

Ambue mba'éramo, mohenda peteĩ Python ñe'ẽrenda oikóvape:

```sh
python -m pip install omi-cli
omi --help
```

Terminal ndojuhúiramo `omi`, ehecha ñe'ẽrenda oikópa térã pipx rupa oĩpa `$PATH`-pe.

## Embojuaju nde mba'éva

Eñepyrũ jeike pytyvõha:

```sh
omi auth login
```

Ikatu reike kundahára ndive térã emoĩ peteĩ Omi API ñe'ẽñemi. Jeike pytyvõ omokañy nde ñe'ẽñemi; eñangareko ani remoĩ nde terminal rembiasakuepe.

Reike hag̃ua kundahára ndive:

```sh
omi auth login --browser
```

Eike peteĩ kombutadórape terminal omba'apóva: jeike ñe'ẽpysyrõ oiporu peteĩ kundaharape oĩva. Eho kuatia ojehechaukáva rehe.

Ehecha ko'ág̃a ñemboheko ha API ñe'ẽñemi:

```sh
omi auth status
omi auth whoami
```

`status` ohechauka ñemboheko oĩva ha omokañy ñemiguáva, ndohechajéi servidórpe. `whoami` ojapo peteĩ jerure ñe'ẽpysyrõndi; oĩramo porã, omoañete nde ñe'ẽpysyrõ omba'apo, ndohechaukarõ gueteri nde réra.

Ñemboheko oĩ `~/.omi/config.toml`-pe. Ani remohera ko kuatia: ikatu oguereko jeike ñemigua.

## Ehesa'ỹijo mba'ekuéra

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Peteĩ tysýi nandi ikatu he'ise ndaipóri mba'e ojoguáva jerure rehe. Reikuaa hag̃ua peteĩteĩ ñe'ẽmandu'apy jejoko, ehecha pytyvõ:

```sh
omi memory list --help
omi action-item list --help
```

## JSON osẽha ha páhina

Emoĩ `--json` **tenondegua** ñe'ẽmandu'apy atýpe:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Peteĩha ñe'ẽmandu'apy ogueru 25 mandu'apy tenondegua; mokõiha ogueru 25 oúva. Peteĩ páhina ndaha'éi henyhẽmbáva. JSON osẽha omoĩ opaite identificadór, ha mesa ojehechaukáva omombykymbaite.

Ehai hag̃ua peteĩ páhina peteĩ kuatiape:

```sh
omi --json memory list --limit 25 --offset 0 > mandu'apy-páhina-1.json
```

Jehakuéra omoheñoĩ térã ohai peteĩ kuatia oĩva. Ehecha ñe'ẽmandu'apy oĩporãpa reiporu mboyve. Jejavy oho stderr-pe; peteĩ kuatia nandi ndohe'iséi ndaipóri mba'e. Kuatia osẽva ikatu oguereko marandu ñemigua: eñongatu porã.

## Sẽ

```sh
omi auth logout
```

Ko ñe'ẽmandu'apy omboyke ñe'ẽpysyrõ oñongatúva. Emboyke hag̃ua ñe'ẽñemi servidórpe, eiporu ñe'ẽñemi ñangareko nde mba'épe.

Ambue ñe'ẽmandu'apy ha jeporavo tuichavéva rehe, ehecha [Ingyaterrañe'ẽ kuatia guasu](../README.md) ha `omi --help`.
