# Camau Cyntaf gydag omi-cli

Mae'r canllaw hwn yn esbonio'r gorchmynion cyntaf yn y Gymraeg. Mae enwau'r
gorchmynion a negeseuon y rhaglen yn aros yn Saesneg. Nid yw'r enghreifftiau
ymholiad a ddangosir yma yn newid eich atgofion, eich sgyrsiau, eich tasgau
nac eich nodau.

## Gosod y rhaglen

Gofynion: Python 3.10 neu fersiwn fwy diweddar a chyfrif Omi.

Os oes gennych `pipx` wedi'i osod:

```sh
pipx install omi-cli
omi --help
```

Fel arall, gallwch ei osod o fewn amgylchedd rhithwir Python gweithredol:

```sh
python -m pip install omi-cli
omi --help
```

Os nad yw'r derfynell (terminal) yn canfod `omi`, gwnewch yn siŵr bod yr
amgylchedd rhithwir wedi'i weithredu neu fod y cyfeiriadur lle mae `pipx`
yn gosod ei ffeiliau gweithredadwy yn eich `PATH`.

## Cysylltu eich cyfrif

Dechreuwch y cynorthwyydd rhyngweithiol:

```sh
omi auth login
```

Dewiswch fewngofnodi yn y porwr neu'r opsiwn i ludo allwedd API datblygwr Omi.
Mae'r mewnbwn rhyngweithiol yn cuddio'r allwedd; osgowch ei hysgrifennu mewn
gorchymyn a fydd yn aros yn hanes y derfynell.

I fynd yn uniongyrchol i'r porwr:

```sh
omi auth login --browser
```

Mewngofnodwch ar yr un cyfrifiadur â'r derfynell: mae'r ymateb dilysu yn
defnyddio cyfeiriad lleol. Dilynwch y cyfarwyddiadau ar y sgrin.

Wedi hynny, gwiriwch y ffurfweddiad a'r mynediad i'r API:

```sh
omi auth status
omi auth whoami
```

Mae `status` yn dangos y cyflwr lleol ac yn cuddio'r gyfrinach, ond nid yw'n
gwirio dilysrwydd ar y gweinydd. Mae `whoami` yn gwneud cais wedi'i ddilysu;
os yw'n llwyddiannus, mae'n cadarnhau bod y manylion adnabod yn gweithio,
heb orfod dangos eich enw o reidrwydd.

Caiff y ffurfweddiad ei gadw yn `~/.omi/config.toml` yn ddiofyn. Peidiwch â
rhannu'r ffeil hon: gall gynnwys eich manylion mewngofnodi cyfrinachol.

## Ymgynghori â'ch data

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Gall rhestr wag olygu'n syml nad oes unrhyw eitemau sy'n cyfateb i'r ymholiad.
Defnyddiwch gymorth i ddarganfod hidlwyr pob gorchymyn:

```sh
omi memory list --help
omi action-item list --help
```

## Cael JSON a llywio trwy dudalennau

Rhowch yr opsiwn byd-eang `--json` **cyn** y grŵp gorchmynion:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Mae'r gorchymyn cyntaf yn gofyn am y 25 atgof cyntaf; yr ail, y 25 nesaf.
Felly nid yw un dudalen yn gopi wrth gefn cyflawn. Mae'r allbwn JSON yn cadw
dynodwyr llawn, tra gall tablau eu byrhau ar gyfer eu harddangos.

I gadw tudalen mewn ffeil:

```sh
omi --json memory list --limit 25 --offset 0 > atgofion-tudalen-1.json
```

Mae'r ailgyfeiriad hwn yn creu neu'n disodli'r ffeil leol. Gwiriwch fod y
gorchymyn wedi gorffen yn llwyddiannus cyn defnyddio ei gynnwys. Caiff gwallau
eu hysgrifennu i'r allbwn gwallau (stderr); nid yw ffeil wag yn gwarantu nad
oes data. Gall y ffeil a allforir gynnwys gwybodaeth bersonol: cadwch hi'n breifat.

## Allgofnodi (Logout)

```sh
omi auth logout
```

Mae'r gorchymyn hwn yn dileu'r manylion mewngofnodi sydd wedi'u cadw'n lleol.
I ddirymu allwedd ar y gweinydd, defnyddiwch reolaeth allweddi datblygwr yn eich cyfrif.

Am weddill y gorchmynion ac opsiynau uwch, edrychwch ar y
[prif ganllaw yn Saesneg](../README.md) ac `omi --help`.
