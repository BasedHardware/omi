# Bdu zzerḥ s omi-cli

Amnir-a yesseǧhed isallen n tzemt di teqbaylit. Isemawen n tzemt d iznan n
program ttwassnen di Taglizit. Tzemt n tneɣrit ddaw-a ur ttbeddilenɣu
tismektiwin-ik, umyalɣan, imanen n ttɣal, neɣ iswi-ik.

## Seḥbes program

Iḥwaǧen: Python 3.10 neɣ amaynut d amiḍan Omi.

Ma yella `pipx` yettuseḥbes:

```sh
pipx install omi-cli
omi --help
```

Neɣ seḥbes-t deg environment virtual yettuscuddun n Python:

```sh
python -m pip install omi-cli
omi --help
```

Ma ur yufi terminal `omi`, wali ma yella environment virtual yettuscuddun neɣ
ma yella directory ideg `pipx` isseḥbes executables yella deg `PATH`.

## Qqen amiḍan-ik

Selkem amnir interactive:

```sh
omi auth login
```

Fren tuqqna s browser neɣ senṭeḍ API key n uneflay Omi. Anekcum interactive
yeffer key; ur ttaru deg tzemt i yekklen deg umazray n terminal.

I useqdec n browser srid:

```sh
omi auth login --browser
```

Qqen ɣef usinɣer yerna d terminal acku tuqqna tesseqdec tansa callback tuntanit.
Ḍfer isallen i d-yettbanen ɣef ugdil.

Selik tuqqna, senṭeḍ configuration d anekcum API:

```sh
omi auth status
omi auth whoami
```

`status` yeskan addad adigan yerna yeffer tisura, maca ur iḥesseqed ma ttwakksen
deg aqeddac. `whoami` yesselkem asuter yettuwaqna; ma yedda, credentials-k
tteddun war ma iskan isem-ik.

Configuration yettwašȟeb deg `~/.omi/config.toml` s wudem amezwar. Ur ttebɣiḍ
afaylu-a acku yezmer ad yegber credentials.

## Γer isallen-ik

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Tabdart tilemt tezmer ad tsemmaɣ ulac aɣewar i yesmeṛṛun filtr-a. Wali tixtarin
n yal tazemt deg tallalt:

```sh
omi memory list --help
omi action-item list --help
```

## Awi JSON ɣer wuraren

Sers axtar amatutlay `--json` **uqbel** agraw n tzemt:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Tazemt tamenzut tesseqda 25 n tismektiwin timenḍan; tis snat tesseqda 25 i
ddren. Yiwet tasebta mačči d aseklilek umḍin. Tuffɣa JSON teǧǧa IDs iččuren,
ambeɣer tarrayt tezmer ad tṣiɣ IDs i uskan.

I usekliles n tasebta deg afaylu:

```sh
omi --json memory list --limit 25 --offset 0 > memory-asebta-1.json
```

Redirect yesseqlec afaylu adigan neɣ yettaru ɣef wayen yellan. Qbel useqdec n
udem, ttekki tazemt tedda akken ilaq. Tuccḍiwin ttaru ɣer stderr; afaylu ilem
ur yestehder belli ulac isallen. Afaylu n usufɣeɣ yezmer ad yegber talɣut
tusligt — eǧǧ-it i ufraḍ.

## Seqdec imaɣen

Addad yettwašȟeb deg `~/.omi/config.toml` (yettuẓay s `$OMI_CONFIG`). Yal
amɣar yesɛa tarrayt-ines n tuqqna d tansa API. Səddis amɣar s `--profile`:

```sh
omi config profile use axeddim
omi auth login
omi --profile usliɣ memory list
```

Tazemt n configuration i yettwassnen:

```sh
omi config show
omi config path
omi config profile list
```

## Tingalin n tuffɣa

Tingalin-a stables sɣur scripts neɣ agents:

| Tingalt | Azal | Amedya n waddad |
| ---: | --- | --- |
| 0 | nzedmer | Tazemt yekfa |
| 1 | tuccḍa n useqdec | flag mačči ḥeṣṣa, argument ixes neɣ validation ur teddi |
| 2 | tuccḍa n tuqqna | credentials ulac, token immut neɣ tisirag ixes |
| 3 | tuccḍa n uqeddac | aqeddac 5xx neɣ tuqqna ur teddi |
| 4 | yettwaḥedded | aqeddac yerra HTTP 429 |
| 5 | ur yettwaf | aqeddac yerra HTTP 404 |

## Ffeɣ

```sh
omi auth logout
```

Yekkes credentials yettwašȟebn adigan. I usewṭer n key ɣef uqeddac, seqdec
adfer n developer key deg amiḍan-ik.

I ugar n tzemt d ixtiḍan, wali [README amenzu di Taglizit](../README.md) ɣer
`omi --help`.
