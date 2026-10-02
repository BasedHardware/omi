# Ñepyrũha omi-cli ndive

Ko kua'e ohechauka umi ñe'ẽpy (commands) tenondegua omi-cli-gui avañe'ẽme. Umi téra ñe'ẽpy ha umi ñe'ẽmondo programagui ojeheja karaiñe'ẽme. Umi techaukaha jeporeka ojehechaukáva ko'ápe ndoñemoambuei nde mandu'áre (memories), nde ñe'ẽnguérape (conversations), nde tembiapo (action items) térã nde jehupytyrã (goals).

## Ñemohenda

Oikotevẽ: Python 3.10 térã pyahuve, ha peteĩ Omi mba'érapa.

Reĩramo `pipx`:

```sh
pipx install omi-cli
omi --help
```

Ikatu avei reñemohenda peteĩ Python ta'ãnga mba'apohápe oikóvape:

```sh
python -m pip install omi-cli
omi --help
```

Ndorohecháiramo pe terminal `omi`, ehechajey oĩpa pe ta'ãnga mba'apoha oikóva térã oĩpa `pipx` róga `$PATH`-pe.

## Nde mba'érapa ñembojoaju

Eñepyrũ pe pytyvõhára oñe'ẽva ndive:

```sh
omi auth login
```

Eiporavo reike hag̃ua kundahára rupive térã reipyso peteĩ API chavi Omi mboguatahára pegua. Pe jehai oñe'ẽva oñomi pe chavi; eñeñangare ani rehai pe chavi peteĩ ñe'ẽpýpe oñeñongatuva terminal rembiasakuepe.

Reho hag̃ua tenonde kundahárape:

```sh
omi auth login --browser
```

Eike peteĩ kombutadórpe oĩva terminal ndive: pe ñembohovái jehechaukaha oho pe kundaharape rogaguápe. Eipyguara umi ñemboheraguapy pe kuatia'atãnguérape.

Upéi, ehecha porã pe ñemohenda ha API jeike:

```sh
omi auth status
omi auth whoami
```

`status` ohechauka pe tekoha rogaguápe ha oñomi pe ñemi, hákatu ndohechaporãi pe tekoañetete ñemboharúpe. `whoami` ojapo peteĩ jerure oñemboheraguapýva; osẽporãramo, hesakã umi mba'ehechauka oikoha, ndohechaukáiramo nde réra.

Pe ñemohenda oñeñongatu ijeheguiete `~/.omi/config.toml`-pe. Ani embohasa ko kuatia: ikatu oreko mba'ehechauka ñemíme.

## Nde mba'ekuaa rechaukaha

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Peteĩ tysýi nandi ohechauka jepi ndaipóriha mba'e ojoguáva pe jeporekápe. Eiporu pe pytyvõ rehecha hag̃ua umi mbogua pepa Ñe'ẽpy:

```sh
omi memory list --help
omi action-item list --help
```

## JSON ha kuatiarogue

Emoĩ pe jeporavora guasu `--json` **tenondegua** pe ñe'ẽpy atýpe:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Pe ñe'ẽpy tenondegua ojeporeka umi 25 mandu'a tenondegua; pe mokõiha umi 25 oúva. Peteĩ kuatiarogue año ndaha'éi peteĩ mbyatyjey oĩmbáva. Pe JSON osẽva oñongatu umi papaha oĩmbáva, jepémo umi kuatia'atãngue ohechaukáva ikatu omombykymi.

Reñongatu hag̃ua peteĩ kuatiarogue peteĩ kuatiañe'ẽme:

```sh
omi --json memory list --limit 25 --offset 0 > mandu'a-kuatiarogue-1.json
```

Ko ñembohasa ojapo térã ojehai peteĩ kuatiañe'ẽ rogagua. Ehechajey opa mboyve pe ñe'ẽpy reheiporu mboyve pe mba'erepy. Umi jejavy ojehai pe jejavy osẽvape (stderr); peteĩ kuatiañe'ẽ nandi ndaha'éi peteĩ techaukaha ndaipóriha mba'ekuaa. Peteĩ kuatiañe'ẽ osẽva ikatu oreko marandu teete: eñongatu ñemíme.

## Ñesẽ

```sh
omi auth logout
```

Ko ñe'ẽpy ombogue umi mba'ehechauka oñeñongatúva rogaguápe. Emboguete hag̃ua peteĩ chavi ñemboharúpe, eiporu pe chavi mboguatahára ñangarekoha nde mba'érapaite.

Rehecha hag̃ua ambue ñe'ẽpy ha jeporavora, ehecha pe [ñe'ẽpy guasu karaiñe'ẽme](../README.md) ha `omi --help`.
