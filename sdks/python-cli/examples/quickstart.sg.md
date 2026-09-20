# Akpengba kete mbeti ti omi-cli

Kete mbeti so afa akpengba kete kamba na Sängö (Sango). Airi ti akomande na atënë ti porogaramu angbâ na Anglais. Atapande ti gingo nda ye so ayeke ge achangé pëpe amémire ti mo (memories), alisoro ti mo (conversations), aye ti sarango ni (action items), wala aye so mo zia na gbele mo (goals).

## Lekengo ni (Installation)

Aye so a hunda: Python 3.10 wala mbeni fini version ti nduzoni, na mbeni konti ti Omi.

Tongana mo zia `pipx` awe na ndö ti masini ti mo:

```sh
pipx install omi-cli
omi --help
```

Mo lingbi nga ti zia ni na yâ ti mbeni virtual environment ti Python so ayeke sara kua:

```sh
python -m pip install omi-cli
omi --help
```

Tongana terminâli abâ `omi` pëpe, bâ wala virtual environment ayeke sara kua nzoni wala lêge ti `pipx` ayeke na yâ ti `$PATH` ti mo.

## Gbungo kamba na konti ti mo (Connecting your account)

To nda ti kamba ti lungo na yâ ni:

```sh
omi auth login
```

Soro ti lï na lege ti browser wala ti zia klê ti API ti Omi ti wandara (developer API key). Lêge ti hunda tënë so ahonde klê ni; aye so akanga lêge ti sungo klê ni na yâ ti mbaï ti akomande ti terminâli.

Ti lï fade fade na lege ti browser:

```sh
omi auth login --browser
```

Lï na ndö ti oko ordinatëre so mo yeke sara kua na terminâli dä: kamba ti authorization asara kua na adrêsi ti ndo ni (local address). Mû peko ti afango ye so asigi na lê ti ecran.

Na pekoni, bâ lege ti lekengo ye na lege ti API:

```sh
omi auth status
omi auth whoami
```

`status` afa ye ti ndo ni na ahonde asekre, me akiri pëpe na tënë na ndö ti server. `whoami` asara mbeni kamba ti yingo ti biani; tongana ague nzoni, afa biani so aye ti hingango mo asara kua, sân ti tene afa iri ti mo na gigi.

Lekengo ye ni ayeke bata na yâ ti `~/.omi/config.toml`. Kangbi fichier so na mbeni zo pëpe: ayeke na asekre ti lïngö na yâ ni.

## Gingo nda ti adonné (Data exploration)

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Mbeni liste so ayeke senge alingbi ti fa gi so mbeni tënë so ague oko na ye so mo gi asigi ade pëpe. Sara kua na aide ti bâ afiltre so ayeke dä ndali ti komande oko oko:

```sh
omi memory list --help
omi action-item list --help
```

## Asongo ti JSON na kangbingo apaje (Pagination)

Zia option ti `--json` **kozo** na groupe ti akomande:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Kozo komande ahunda amémire 25 ti kozoni; use ni amû 25 so aga na peko ni. Paje oko ayeke pëpe backup ti kue. Asongo ti JSON abata a-ID kue nzoni, me atable ti ecran alingbi ti kaï yâ ni kete ti tene abâ ni nzoni.

Ti bata mbeni paje na yâ ti mbeni fichier:

```sh
omi --json memory list --limit 25 --offset 0 > amemire-paje-1.json
```

Kamba ti kiringo ye so acréé wala asuku ndö ti fichier ti ndo ni. Bâ nzoni si komande ni asara kua nzoni kozo ti sara kua na aye so ayeke na yâ ni. Afaute ayeke sungo na yâ ti stderr; fichier so ayeke senge afa pëpe so tënë oko ayeke dä pëpe. Fichier so amozi alingbi ti yeke na atënë ti mo mveni: kpe ti kangbi ni na ambeni zo.

## Sigingo na yâ ni (Logout)

```sh
omi auth logout
```

Komande so azi aye ti hingango mo so abata na ndö ti masini ti mo. Ti lungula mbeni klê na ndö ti server, sara kua na paje ti aklê ti awandara na yâ ti konti ti mo.

Ndali ti ambeni komande na a-option ti nduzoni, bâ [kota mbeti ti Anglais](../README.md) na `omi --help`.
