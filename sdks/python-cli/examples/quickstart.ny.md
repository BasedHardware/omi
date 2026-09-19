# Kuyamba Mwachangu ndi omi-cli

Bukhuli likufotokoza malamulo oyambirira m'chinenero cha Chichewa (Nyanja). Mayina a malamulo ndi mauthenga ochokera ku pulogalamu amakhalabe mu Chingerezi. Zitsanzo za mafunso (query) zomwe zikuwonetsedwa pano sizisintha zokumbukira zanu (memories), zokambirana (conversations), zochita (action items), kapena zolinga zanu (goals).

## Kuyika pulogalamu (Installation)

Zofunika: Python 3.10 kapena mtundu watsopano pamodzi ndi akaunti ya Omi.

Ngati muli ndi `pipx` yoyikidwa kale:

```sh
pipx install omi-cli
omi --help
```

Mwanjira ina, mutha kuyika mkati mwa malo enieni a Python (virtual environment) omwe akugwira ntchito:

```sh
python -m pip install omi-cli
omi --help
```

Ngati terminal siyingapeze `omi`, onetsetsani kuti virtual environment ikugwira ntchito kapena foda yomwe `pipx` imayika mafayilo ake ogwiritsidwa ntchito ili mu `$PATH` yanu.

## Kulumikiza akaunti yanu (Authentication)

Yambitsani wothandizira wolankhula (interactive assistant):

```sh
omi auth login
```

Sankhani kulowa kudzera pa msakatuli (browser) kapena njira yomata kiyi ya developer API ya Omi. Kulowetsa kwapaintaneti kumateteza kiyi; pewani kulemba kiyi mu lamulo lomwe lingatsale mu mbiri ya terminal.

Kuti mupite molunjika ku msakatuli:

```sh
omi auth login --browser
```

Lowani pa kompyuta yomweyi yomwe terminal ikugwirira ntchito: yankho lachitsimikizo limagwiritsa ntchito adilesi yakomweko (local address). Tsatirani malangizo omwe ali pawindo.

Pambuyo pake, yang'anani masinthidwe ndi mwayi wofikira ku API:

```sh
omi auth status
omi auth whoami
```

`status` ikuwonetsa momwe zinthu zilili m'deralo ndipo imabisa zinsinsi, koma siitsimikizira kuvomerezeka pa seva. `whoami` imatumiza pempho lotsimikizika; ngati zayenda bwino, zikutsimikizira kuti zikalatazo zikugwira ntchito popanda chifukwa chosonyeza dzina lanu.

Masinthidwe amakhalapo nthawi zonse mu `~/.omi/config.toml`. Musagawane fayiloyi chifukwa ikhoza kukhala ndi zinsinsi zanu.

## Kuyang'ana deta yanu

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Mndandanda wopanda kanthu ungangotanthauza kuti palibe zinthu zofananira ndi zomwe mwafunsa. Gwiritsani ntchito chithandizo kuti mupeze zosefera pa lamulo lililonse:

```sh
omi memory list --help
omi action-item list --help
```

## Kupeza JSON ndi kusakatula masamba (Pagination)

Ikani njira yapadziko lonse `--json` **musanayambe** gulu la malamulo:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Lamulo loyamba limapempha zokumbukira 25 zoyambirira; lachiwiri, 25 zotsatira. Tsamba limodzi si chosungira chokwanira (backup). Zotsatira za JSON zimasunga zizindikiro zonse bwinobwino, pomwe matebulo apawindo amatha kuzifupikitsa kuti ziwoneke bwino.

Kuti musunge tsamba m'fayilo:

```sh
omi --json memory list --limit 25 --offset 0 > zokumbukira-tsamba-1.json
```

Kusintha uku kumapanga kapena kuloŵa m'malo mwa fayilo yakomweko. Onetsetsani kuti lamulo latha bwino musanagwiritse ntchito zomwe zili mkati mwake. Zolakwika zimalembedwa muzotsatira zolakwika (stderr); fayilo yopanda kanthu si umboni woti palibe deta. Fayilo yotumizidwa kunja ikhoza kukhala ndi zinsinsi zanu: isungeni motetezeka.

## Kutuluka mu akaunti (Logout)

```sh
omi auth logout
```

Lamuloli limachotsa zikalata zosungidwa pamakina anu. Kuti muletse kiyi pa seva, gwiritsani ntchito kasamalidwe ka kiyi ya opanga mu akaunti yanu.

Kuti mudziwe zambiri zamalamulo ndi zosankha zapamwamba, onani [buku lalikulu la Chingerezi](../README.md) ndi `omi --help`.
