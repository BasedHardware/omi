# Eñepyrũ omi-cli ndive

Ko téra ohechauka umi ñepyrũha tembiapoukapy Avañe'ẽme. Umi tembiapoukapy réra ha apopyvusu marandu opyta Inglés-pe. Ko'ápe oñeme'ẽva techapyrã ndomoambulmo'ãi nde mandu'a, ñemongeta, tembiapo rysýi térã ne rembipota.

## Emohenda pe tembiporu

Oñeikotevẽva: Python 3.10 térã ipyahuvéva ha peteĩ Omi mba'ete.

> Jesarekorã: Pe paquete réra PyPI-pe ha'e **`omi-cli`**, ha katu pe tembiapoukapy oñembohapéva ñemohenda rire ha'e **`omi`**. Oĩ ambue paquete ojoaju'ỹva hérava `omi` PyPI-pe — ani emohenda upe paquete.

Oimérõ `pipx` oñemohendáma:

```sh
pipx install omi-cli
omi --help
```

Ambue hendáicha, peteĩ Python virtoal hekoveetéva ryepýpe:

```sh
python -m pip install omi-cli
omi --help
```

Pe terminal ndojohúirõ `omi`, ehecha ko virtoal oiko porãpa térã `pipx` rrenda oĩpa nde `PATH`-pe.

## Ejoaju nde mba'etére

Eñepyrũ pe pytyvõhára:

```sh
omi auth login
```

Eiporavo eike hag̃ua kundahára rupive, térã eiporavo emoĩ hag̃ua Omi mboguataha API ravichái. Ko tembiapo omokañy pe lavichái; ani ehaivai pe lavichái terminal rembiasakue ryepýpe.

Eike tee hag̃ua kundahára rupive:

```sh
omi auth login --browser
```

Ejapo ko jeike pe mohendaha oñemombyryhápe pe terminal, pe mboaje ojevy peteĩ kundaharapeguápe. Etegui umi mba'e oje'éva ta'ãngambyrýpe.

Upe rire, ehecha pe mohendapy ha API jeikeha:

```sh
omi auth status
omi auth whoami
```

`status` ohechauka mba'éichapa oĩ ha omokañy ñemigua, ha katu ndohechái pe servidor ndive. `whoami` omondo peteĩ jerure oñemboajéva; osẽ porãramo he'ise nde rechaukaha omba'apo porãha.

Mohendapy oñeñongatu jepiveguáicha `~/.omi/config.toml`-pe. Ani emoherakuã ko marandurenda oguerekógui nde mba'eteéva marandu.

## Ehecha nde mba'ekuaarã

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Peteĩ tysýi nandi ikatu he'ise ndaiporiha mba'eve ojoguáva nde jerurépe. Reikuaa hag̃ua tembiapoukapy mboguataha, ehecha pytyvõ:

```sh
omi memory list --help
omi action-item list --help
```

## Ehupyty JSON ha eho ambue kuatiarogue rupi

Emoĩ pe jeporavo guasu `--json` pe tembiapoukapy aty **mboyve**:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Peteĩha tembiapoukapy ojerure umi 25 kuatiahaipyre peteĩha; mokõiha katu ojerure umi 25 oúva. Upévare peteĩ kuatiarogue ndaha'éi pe ñongatuha hekopetéva. JSON osẽva oguereko umi mba'e hekopete, ha umi apyka ikatu omombyky.

Reñongatu hag̃ua peteĩ kuatiarogue marandurendápe:

```sh
omi --json memory list --limit 25 --offset 0 > mandu-kuatia-1.json
```

Ko jeykuaa omopu'ã térã omyengovia marandurenda tendaguáva. Reiporu mboyve, ehecha osẽ porãpa tembiapoukapy. Umi jejavy ojehai stderr-pe; marandurenda nandi ndaha'éi techaukaha ndaiporiha mba'ekuaarã. Eñangareko porã hese oguerekógui nde maranduete.

## Esẽ (Log out)

```sh
omi auth logout
```

Ko tembiapoukapy oipe'a umi rechaukaha tendaguáva. Embogue hag̃ua pe lavichái servidor-pe, eiporu mboguataha lavichái ñangareko nde mba'etépe.

Ambue tembiapoukapy ha jeporavópe g̃uarã, ehecha pe kuatiahaipyre tenondegua Inglés-pe:
[../README.md](../README.md) ha `omi --help`.
