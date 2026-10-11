# Nayrïr saräwinaka omi-cli-mpi

Aka uñstawi omi-cli-n nayrïr saräwinakapa (commands) aymar arupi qhanañchi. Commandanakana sutipa ukhamarak programa chimpunakapa inklisi arupin qhiparaki. Akan uñacht'ayata thaqhañ uñacht'awinakaxa janwa memoriyanakama (memories), parlasinakama (conversations), lurañanakama (action items) jan ukax amtanakama (goals) turkaykiti.

## Uñstayaña

Muntañanaka: Python 3.10 jan ukax juk'ampi machaqa, ukhamarak mä Omi akawnta.

`pipx` utjki ukhaxa:

```sh
pipx install omi-cli
omi --help
```

Ukhamaraki Python virtual environmentan uñstayasma:

```sh
python -m pip install omi-cli
omi --help
```

Terminalax `omi` jikxhati ukhaxa, virtual environmentax irnaqaskpacha jan ukax `pipx` uñt'awipax `$PATH`-na utjkipacha qhanancht'ama.

## Akawntama jaljaña

Kikpaq yanapiriru qalltama:

```sh
omi auth login
```

Browser tuqina mant'aña jan ukax Omi developer API llawinta churaña ajllima. Kikpaq mant'awix llawina imanti; terminal sarnaqawina qhiparaq llawina qillqañax jan walt'añama.

Browser sarantañataki:

```sh
omi auth login --browser
```

Terminalampi kikpaq computadorana mant'ama: autentikasiya jaysawix chiqan adresaru sari. Skrinana uñacht'awinakaru arknaqama.

Ukhamata, uñakipama configuración ukhamarak API sarantaña:

```sh
omi auth status
omi auth whoami
```

`status` chiqan estadu uñacht'ayi ukhamarak secret imanti, ukampis serverana chiqpachapxäti uka jan uñakipkiti. `whoami` autentikata wakisi; phuqtki ukhaxa, credencialanakax irnaqaski, sutima jan uñacht'ayasa.

Configuraciónax `~/.omi/config.toml`-na default ukhama imatawa. Aka qillqata jan yatiyäma: privado credencialanakaniñax inakiwa.

## Datama uñjaña

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Ch'usa lista ukax janiw kunsa thaqhawimpi kikipkiti ukwa qhanañchi. Yanapt'aña apnaqama sapa commandana filtronakapa jikxhañataki:

```sh
omi memory list --help
omi action-item list --help
```

## JSON ukhamarak paninaka

Globala ajlliña `--json` **nayraqata** commanda tantachäwina uchaña:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Nayrïr commandax nayrïr 25 memorianaka mayi; payïrix juk'ampi 25. Mä panixa janiw phuqhata kupyäkiti. JSONax phuqhata jakhunakwa imanti, ukampis skrinana tablanakax jisk'achasma.

Mä pana mä qillqataru imañataki:

```sh
omi --json memory list --limit 25 --offset 0 > memori-pana-1.json
```

Aka redirectax chiqan qillqata lurañ jan ukax mayjt'ayi. Commandax tukuski uka qhanancht'ama, jan ukax uñstawipa apnaqkasaxa. Pantjasinakax error output (stderr)-ru qillqantawa; ch'usa qillqatax janiw data utjki uk qhanañchirikiti. Eksportata qillqatax jaqin yatiyawinakaniñax inakiwa: privado ukhama imama.

## Mistuña

```sh
omi auth logout
```

Aka commandax chiqan imata credencialanakwa apaqi. Serverana mä llawi jani irnaqkaspa, akawntamana developer llawi apnaqaña apnaqama.

Juk'ampi commandanakataki ukhamarak ajlliñanakataki, [inklisi qhananchiri](../README.md) ukhamarak `omi --help` uñjaña.
