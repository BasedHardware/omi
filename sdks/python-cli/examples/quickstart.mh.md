# Jintok kōn omi-cli

Bok in kam̧m̧an in ej kōmeļeļeik kōkaajiriddik ko jinointa kōn Kajin Majōl. Etan
kōkaajiriddik ko im naan in kōjjeļā ko an porokram̧ in rej pād wōt ilo Kajin Iniklis.
Waanjon̄ok ko ilo bok in reban ukōt kakeememej ko am̧, bwebwenato ko, jerbal ko, ak kōttōbar ko.

## Kakwōjjarjarik porokram̧ in

Men ko rej aikuji: Python 3.10 ak emāneļo̧k im juon akaun in Omi.

Eļan̄n̄e ewōr `pipx` ippam̧:

```sh
pipx install omi-cli
omi --help
```

Kwo maron̄ bar kakwōjjarjar ilo juon jikin kōm̧m̧an jerbal an Python (virtual environment):

```sh
python -m pip install omi-cli
omi --help
```

Eļan̄n̄e tōminal eo ejjab loe `omi`, lale bwe jikin eo en jerbal ak peba an `pipx` en pād ilo `PATH` am̧.

## Kōkeidodoik akaun eo am̧

Kajjutok ippān jibōk eo:

```sh
omi auth login
```

Kālet n̄an deļo̧n̄ kōn jikin kōm̧m̧an ilo burowja (browser) ak kakkōt kī in API an dri-kōm̧m̧an Omi.
Kōjerbal login eo ej nooj kī eo; jab je ilo kōkaajiriddik bwe en jab pād ilo bwebwenato an tōminal.

N̄an etal jim̧we n̄an burowja:

```sh
omi auth login --browser
```

Deļo̧n̄ ilo kōm̧piutōr eo wōt me tōminal eo ej jerbal ie. Ļoor kōmeļeļe ko ilo skriin eo.

Ālikin men in, etale kōm̧m̧an ko im jikin deļo̧n̄ an API:

```sh
omi auth status
omi auth whoami
```

`status` ej kōkkaalļo̧k jikin lōkōļ ak ejjab etale ilo jikin kōjparok eo (server).
`whoami` ej jilkinkwoļo̧k juon kajjitōk me ej kam̧ool bwe kī ko rej jerbal jim̧we.

Aolep men ko rej pād ilo `~/.omi/config.toml`. Jab ajeji peba in kōnke emaron̄ wōr kī ko ilo ie.

## Lale dāāta ko am̧

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Juon laajrak ejjeļo̧k kōmeļeļe ie emaron̄ meļeļein bwe ejjeļo̧k men ko rej ejaake kajjitōk eo.
Kōjerbal jiban̄ n̄an lale kōm̧m̧an ko:

```sh
omi memory list --help
omi action-item list --help
```

## Bōk JSON im kōm̧m̧an peij ko

Likūt kālet eo an aolep `--json` **im̧aan** kōkaajiriddik eo:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Kōkaajiriddik eo jinointa ej kajjitōk 25 kakeememej; eo kein karuo ej kajjitōk 25 ko tok ālik.
JSON ej kōjparok ID ko aolep.

N̄an kōjparok juon peij ilo peba:

```sh
omi --json memory list --limit 25 --offset 0 > kakeememej-peij-1.json
```

Lale bwe en jerbal jim̧we kōkaajiriddik eo mokta jān am̧ kōjerbal dāāta ko. Peba in emaron̄ wōr dāāta ko am̧: kōjparok ilo nooj.

## Diwōj (Logout)

```sh
omi auth logout
```

Men in ej jeorļo̧k kī ko ilo kōm̧piutōr eo. N̄an kōm̧m̧an am̧ kī en jab jerbal ilo jikin eo, kōjerbal jikin lale kī ilo akaun eo am̧.

N̄an kōkaajiriddik ko jet, lale
[bok eo kein kajjin Iniklis](../README.md) im `omi --help`.
