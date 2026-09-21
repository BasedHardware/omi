# Kuyambirira ndi omi-cli

Buku iyi ikuthandiza kuyambirira ndi omi-cli mu chiyankhulo cha Chisena. Mayina a ma command ndi mauthenga a pulogalamu akhalabe mu Chingerezi. Zitsanzo za mu buku iyi sizisintha zokumbukira, makambiridwe, ntchito kapena zolinga zanu.

## Kukhazikitsa

Mukufuna Python 3.10 kapena pamwamba, ndi akaunti ya Omi.

Ngati `pipx` ili kale:

```sh
pipx install omi-cli
omi --help
```

Kapena mutha kuyiika mu Python virtual environment yogwira:

```sh
python -m pip install omi-cli
omi --help
```

Ngati terminal siipeza `omi`, onani ngati virtual environment ikugwira kapena ngati folda ya `pipx` ili mu `$PATH`.

## Kulumikiza akaunti yanu

Yambani wizard ya login:

```sh
omi auth login
```

Mutha kusankha kulowa ndi browser kapena kuyika API key ya developer wa Omi. Zomwe mumalowetsa zimabisala key; samalani kuti musaisiye mu mbiri ya terminal.

Kulowa mwachindunji ndi browser:

```sh
omi auth login --browser
```

Lowani pa kompyuta yomweyo pamene terminal ikugwira: yankho la chilolezo limagwiritsa ntchito adilesi ya kompyuta. Tsatirani malangizo pa sikirini.

Tsopano onani kasinthidwe ndi API key:

```sh
omi auth status
omi auth whoami
```

`status` imasonyeza momwe zili muno ndipo imabisala zinsinsi, koma siyiyesa pa seva. `whoami` imapanga pempho lololedwa; ngati lipambana, zikutanthauza kuti chilolezo chanu chikugwira, koma simasonyeza dzina lanu.

Kasinthidwe kasungidwa mu `~/.omi/config.toml`. Musagawane fayilo iyi: ikhoza kukhala ndi zinsinsi za kulowa.

## Kuwona deta

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Mndandanda wopanda kanthu ukhoza kungotanthauza kuti palibe deta yofanana ndi funso. Kuti mudziwe kugwiritsa ntchito command iliyonse, onani chithandizo:

```sh
omi memory list --help
omi action-item list --help
```

## JSON ndi masamba

Ikani option ya `--json` **patsogolo** pa gulu la command:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Command yoyamba ibweretsa zokumbukira 25 zoyambirira; yachiwiri ibweretsa zina 25. Tsamba limodzi silikhala lathunthu nthawi zambiri. JSON imasonyeza zizindikilo zonse, koma matebulo a pa sikirini nthawi zambiri amazifupikitsa.

Kulemba tsamba mu fayilo:

```sh
omi --json memory list --limit 25 --offset 0 > zokumbukira-tsamba-1.json
```

Redirect imapanga fayilo ya muno kapena imalemba m'mwamba mwake. Onetsetsani kuti command yapambana musanagwiritse ntchito zomwe zili. Zolakwika zimapita ku stderr; fayilo lopanda kanthu sikutanthauza kuti palibe deta. Mafayilo otulutsidwa akhoza kukhala ndi zinsinsi: wasunge bwino.

## Kutuluka

```sh
omi auth logout
```

Command iyi imachotsa chilolezo chosungidwa mu muno. Kuti muthetse key pa seva, gwiritsani ntchito kasamalidwe ka developer key pa akaunti yanu.

Kwa ma command ena ndi ma option apamwamba, onani [malangizo akulu a Chingerezi](../README.md) ndi `omi --help`.
