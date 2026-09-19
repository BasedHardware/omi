# Fiantombohana Haingana miaraka amin'ny omi-cli

Ity torolalana ity dia manazava ireo baiko voalohany amin'ny teny Malagasy (Fiteny Malagasy). Ny anaran'ny baiko sy ny hafatra avy amin'ny fandaharana dia mitoetra amin'ny teny Anglisy. Ireo ohatra fakana am-bavany (query) aseho eto dia tsy manova ny fahatsiarovanao (memories), ny resakao (conversations), ny zavatra tokony hatao (action items), na ny tanjonao (goals).

## Fametrahana ny fandaharana

Fepetra takiana: Python 3.10 na dikan-teny vaovao kokoa miaraka amin'ny kaonty Omi.

Raha efa nametraka `pipx` ianao:

```sh
pipx install omi-cli
omi --help
```

Azonao atao koa ny mametraka azy ao anatin'ny tontolo virtoaly Python efa velona (activated virtual environment):

```sh
python -m pip install omi-cli
omi --help
```

Raha tsy mahita ny `omi` ny terminal, ataovy azo antoka fa mandeha tsara ny tontolo virtoaly na ny lahatahiry ametrahan'ny `pipx` ireo rakitra azo tanterahina dia tafiditra ao anatin'ny `$PATH`-nao.

## Fampifandraisana ny kaontinao

Atomboy ny mpanampy ifandrimbonana (interactive assistant):

```sh
omi auth login
```

Safidio ny fidirana amin'ny alàlan'ny navigateur (browser) na ny safidy hametaka fanalahidy API developer Omi. Manafina ny fanalahidy ny fampidirana ifandrimbonana; aza soratana amin'ny baiko izay mety hitoetra ao amin'ny tantaran'ny terminal ny fanalahidy.

Raha te handeha mivantana any amin'ny navigateur:

```sh
omi auth login --browser
```

Midira amin'ny solosaina mitovy amin'ny fandehanan'ny terminal: mampiasa adiresy eo an-toerana (local address) ny valin'ny fanamarinana. Araho ny toromarika miseho eo amin'ny efijery.

Aorian'izay, hamarino ny fikirakirana sy ny fidirana amin'ny API:

```sh
omi auth status
omi auth whoami
```

Ny `status` dia mampiseho ny toetry ny toerana misy anao ary manafina ny zava-miafina, saingy tsy manamarina ny maha-marina azy any amin'ny mpizara (server). Ny `whoami` dia manao fangatahana efa voamarina; raha mahomby izany, manaporofo fa miasa ny fahazoan-dàlana nefa tsy mila mampiseho ny anaranao akory.

Voatahiry ao amin'ny `~/.omi/config.toml` ny fikirakirana amin'ny ankapobeny. Aza zaraina ity rakitra ity satria mety misy ny fahazoan-dàlana miafinao.

## Fizahana ny angon-drakitrao

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Ny lisitra tsy misy na inona na inona dia mety midika fotsiny fa tsy misy zavatra mifanaraka amin'ny sivana. Ampiasao ny fanampiana hahitana ireo sivana isaky ny baiko:

```sh
omi memory list --help
omi action-item list --help
```

## Fakana JSON sy fitetezana pejy (Pagination)

Apetraho eo **alohan'ny** vondron'ny baiko ny safidy maneran-tany `--json`:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Ny baiko voalohany dia mangataka ireo fahatsiarovana 25 voalohany; ny faharoa, ireo 25 manaraka. Ny pejy iray dia tsy tahiry feno akory. Ny vokatra JSON dia mitazona ireo famantarana feno, fa ny tabilao kosa dia mety hanafohy azy ireo mba ho tsara jerena.

Raha te hitahiry pejy iray anaty rakitra:

```sh
omi --json memory list --limit 25 --offset 0 > fahatsiarovana-pejy-1.json
```

Ity fanovàna lalana ity dia mamorona na manolo ny rakitra eo an-toerana. Ataovy azo antoka fa vita soa aman-tsara ny baiko alohan'ny hampiasana ny ao anatiny. Ny lesoka dia voasoratra ao amin'ny fivoahana lesoka (stderr); ny rakitra foana dia tsy antoka fa tsy misy angon-drakitra. Ny rakitra naondrana dia mety misy fampahalalana manokana: tehirizo tsara izany.

## Fivoahana amin'ny kaonty (Logout)

```sh
omi auth logout
```

Ity baiko ity dia manaisotra ireo fahazoan-dàlana voatahiry eo an-toerana. Raha hanafoana fanalahidy any amin'ny mpizara, ampiasao ny fitantanana fanalahidin'ny developer ao amin'ny kaontinao.

Raha mila baiko hafa sy safidy mandroso kokoa, jereo ny [torolalana lehibe amin'ny teny Anglisy](../README.md) sy ny `omi --help`.
