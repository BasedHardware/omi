# Tsumbandila ya u Țavhanya ya omi-cli

Tsumbandila iyi i ṱalutshedza ndaela dza u thoma nga Tshivenḓa (Venda) dza `omi-cli`. Madzina a ndaela na milaedza ya mbekanyamushumo zwi dzula zwi nga Luisimane. Tsumbo dza u lavhelesa dzo sumbedzwaho hafha a dzi shandukisi mihumbulo yavho (memories), nyambedzano (conversations), mishumo i re khagala (action items), kana zwipikwa zwavho (goals).

## U dzhenisa mbekanyamushumo (Installation)

Zwi ṱoḓeaho: Python 3.10 kana i re nṱha na akhaundi ya Omi.

Arali vha na `pipx` yo dzheniswaho:

```sh
pipx install omi-cli
omi --help
```

Vha nga dovha vha i dzhenisa ngomu ha mupo u shumaho wa Python (virtual environment):

```sh
python -m pip install omi-cli
omi --help
```

Arali ndaela ya `omi` i sa waniwe kha theminara, vha vhone uri virtual environment i khou shuma kana uri buḓo ḽa `pipx` ḽi ngomu ha `$PATH` yavho.

## U ṱumanya akhaundi yavho (Authentication)

Thomeni muthusi a re na vhudavhidzani:

```sh
omi auth login
```

Nangani u dzhena nga burawuza (browser) kana u dzhenisa Omi developer API key yavho. Ndila iyi i dzumba khii iyi; vha iledze u i ṅwala kha ndaela dzi no nga sala kha ḓivhazwakale ya theminara.

U ya tshiṱwaho kha burawuza:

```sh
omi auth login --browser
```

Dzhenani kha khomphyutha i fanaho ine theminara ya khou shuma khayo: phindulo ya u khwaṱhisedza i shumisa ḓiresi ya hayani. Tevhelani ndaela dzi re kha tshikirini.

Nga murahu ha zwenezwo, khwaṱhisedzani nzudzanyo na u swikelela API:

```sh
omi auth status
omi auth whoami
```

`status` i sumbedza tshiimo tsha henefho nahone i dzumba tshiphiri, fhedzi a i toli vhukoni hayo kha tshisevha (server). `whoami` i rumela khumbelo yo khwaṱhisedzwaho; arali zwo bvelela, i khwaṱhisa uri mbambedzo dzi khou shuma vha songo sumbedza dzina ḽavho.

Nzudzanyo kanzhi dzi vhulungwa kha `~/.omi/config.toml`. Vha songo kovhelana faela iyi na vhaṅwe: i nga vha i na mbambedzo dza tshiphiri.

## U tola zwi re ngomu (Inspection)

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Mutevhe u si na tshithu u nga amba fhedzi uri a hu na zwo linganaho na ndodisiso. Shumisani thusedzo u wana zwikhethwa kha ndaela iṅwe na iṅwe:

```sh
omi memory list --help
omi action-item list --help
```

## U wana JSON na u Kovha Masiaṱari (Pagination)

Vheani khetho ya ḽifhasi ya `--json` **phanda** ha tshigwada tsha ndaela:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Ndaela ya u thoma i humbela mihumbulo ya 25 ya u thoma; ya vhuvhili i humbela ya 25 i tevhelaho. Siaṱari ḽithihi a ḽi ngo lingana u vha khophi yo ṱanganelaho (backup). Zwi bviswaho zwa JSON zwi vhulunga zwitshimbidzi zwoṱhe, naho tafula ya tshikirini i tshi nga zwi fhungudza u itela u sumbedza zwavhuḓi.

U vhulunga siaṱari kha faela:

```sh
omi --json memory list --limit 25 --offset 0 > mihumbulo-siatari-1.json
```

Ndila iyi i vhumba kana i vusuludza faela ya henefho. Vhonani uri ndaela yo fhela zwavhuḓi vha sa athu shumisa zwi re ngomu. Zwonṱhe zwo khakheaho zwi ṅwalwa kha tshipiḓa tsha vhukhakhi (stderr); faela i si na tshithu a zwi ambi uri a hu na datha. Faela yo bviswaho i nga vha na zwiambaphiri zwavho: i vhulungeni zwavhuḓi.

## U bva kha akhaundi (Logout)

```sh
omi auth logout
```

Ndaela iyi i bvisa mbambedzo dzo vhulungwaho henefho hayani. U thutha khii kha tshisevha, shumisani ndaulo ya developer key kha akhaundi yavho.

U wana ndaela dziṅwe na zwikhethwa zwo engedzwaho, vhonani [tsumbandila khulwane ya Luisimane](../README.md) na `omi --help`.
