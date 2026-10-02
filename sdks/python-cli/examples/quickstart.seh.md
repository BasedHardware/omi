# Mapito oyambirira na omi-cli

Buku iyi inalongana mapito oyambirira (commands) a omi-cli mu chisena. Mayina a mapito na mauta a pulogaramu anakhala mu chingerezi. Zitsanzo za kufufuza zosonyezedwa pano sizisintha makumbukidwe anu (memories), zokambirana zanu (conversations), ntchito zanu (action items) kapena zolinga zanu (goals).

## Kukhazikitsa

Zofunika: Python 3.10 kapena wapamwamba, ndi akaunti ya Omi.

Ngati muli ndi `pipx`:

```sh
pipx install omi-cli
omi --help
```

Mutha kuyikanso mu malo a Python ogwira ntchito (virtual environment):

```sh
python -m pip install omi-cli
omi --help
```

Ngati terminal sipeza `omi`, onetsetsani kuti malo ogwira ntchito akugwira kapena kuti folda ya `pipx` ili mu `$PATH`.

## Kulumikiza akaunti yanu

Yambani wothandizira wokambirana:

```sh
omi auth login
```

Sankhani kulowa kupyolera mu browser kapena kumata kiyi ya API ya Omi developer. Kulowa kwa kukambirana kumabisa kiyi; pewani kuyilemba mu lamulo lomwe lingasungidwe mu mbiri ya terminal.

Kupita mwachindunji ku browser:

```sh
omi auth login --browser
```

Lowani pa kompyuta imodzi ndi terminal: yankho la kutsimikizira limapita ku adilesi yakomweko. Tsatirani malangizo pa sikirini.

Pambuyo pake, onetsetsani kasinthidwe ndi mwayi wa API:

```sh
omi auth status
omi auth whoami
```

`status` imasonyeza mkhalidwe wakomweko ndi kubisa chinsinsi, koma siyenera kutsimikizira kuvomerezeka pa seva. `whoami` imapanga pempho lotsimikizika; ngati lipambana, zikuoneka kuti zizindikiro zikugwira ntchito, popanda kusonyeza dzina lanu.

Kasinthidwe amasungidwa mwachizolowezi mu `~/.omi/config.toml`. Musagawane fayilo iyi: ikhoza kukhala ndi zizindikiro zachinsinsi.

## Kufufuza deta yanu

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Mndandanda wopanda kanthu nthawi zambiri umatanthauza kuti palibe chomwe chikugwirizana ndi kufufuza. Gwiritsani ntchito chithandizo kuti mupeze zosefera za lamulo lililonse:

```sh
omi memory list --help
omi action-item list --help
```

## JSON na mapeji

Ikani chosankha chapadziko lonse `--json` **patatsala** gulu la malamulo:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Lamulo loyamba limapempha makumbukidwe 25 oyambirira; lachiwiri limapempha 25 otsatira. Peji imodzi si kope lathunthu. JSON imasunga manambala athunthu, koma matebulo pa sikirini amatha kuwafupikitsa.

Kusunga peji mu fayilo:

```sh
omi --json memory list --limit 25 --offset 0 > makumbukidwe-peji-1.json
```

Kutumiza uku kumapanga kapena kulemba m'mwamba fayilo yakomweko. Onetsetsani kuti lamulo latha musanagwiritse ntchito zomwe zili mkati. Zolakwika zimalembedwa ku kutulutsa zolakwika (stderr); fayilo yopanda kanthu si umboni kuti palibe deta. Fayilo yotumizidwa kunja ikhoza kukhala ndi zambiri zaumwini: isungeni mwachinsinsi.

## Kutuluka

```sh
omi auth logout
```

Lamulo ili limachotsa zizindikiro zosungidwa pakomweko. Kuti muchepetse kiyi pa seva, gwiritsani ntchito kasamalidwe ka kiyi ya developer pa akaunti yanu.

Kuti mupeze malamulo ndi zosankha zina, onani [buku lalikulu mu chingerezi](../README.md) ndi `omi --help`.
