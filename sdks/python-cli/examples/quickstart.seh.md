# Kutoma na omi-cli

Bukhu iyi isasandikira mafala a kutoma mu Cisena. Madzina a mafala na mphangwa za
porogalama ziri mu Cizungu. Pire vitsanzo pino nkhabe kucinja ma memory, macedzo,
mabasa peno pyakufuna pyanu.

## Kuikhira Porogalama

Pinafunika: Python 3.10 peno yapamwamba na akawunti ya Omi.

Khombo muna `pipx`:

```sh
pipx install omi-cli
omi --help
```

Munakwanisa kukhazikisa pontho mu Python virtual environment yakufunika:

```sh
python -m pip install omi-cli
omi --help
```

Ngakhale terminal nkhabe kuona `omi`, yang'anani ngakhale mbuto ya `pipx` iri pa `$PATH`.

## Kulumikiza Akawunti Yanu

Yambisani cibverano:

```sh
omi auth login
```

Sankhani kupita na browser peno kuikha API key ya Omi.
Kupita na njira ineyi kubisa key; lekani kulemba mu fala inacita kukhala mu mbiri ya terminal.

Kuti muende mwacindunji ku browser:

```sh
omi auth login --browser
```

Pitani pa ntcini ubodzi-bodzi ule uli na terminal. Tobzerani pyakubveka pa skrini.

Pambuyo pace, yang'anani makhazikisikidwe na kupita ku API:

```sh
omi auth status
omi auth whoami
```

`status` isapangiza ciri pa ntcini. `whoami` isatsimikiza kuti key ikuphata basa mwadidi.

Pyonsene piri mu `~/.omi/config.toml`. Lekani kugawira fayelo ino thangwi iri na pyakubisika.

## Kuyang'ana Pidziwiso Pyanu

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Lisiti ya pezi isabveka nkhabe cinthu cidagwirizana. Phatisirani ciphedzo:

```sh
omi memory list --help
omi action-item list --help
```

## Kutapa JSON na Matsamba (Pagination)

Ikhani `--json` **patsogolo** pa fala:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Fala yakutoma isaphemba ma memory 25 akutoma; yaciwiri isaphemba 25 anabwera pambuyo. JSON isakoya ma ID onsene.

Kuti mukoye tsamba mu fayelo:

```sh
omi --json memory list --limit 25 --offset 0 > memory-tsamba-1.json
```

Fayelo ino inakwanisa kukhala na mphangwa za munthu mwini: koyani mwacibisobiso.

## Kubuda (Logout)

```sh
omi auth logout
```

Fala iyi isafuta key pa ntcini wanu. Kuti mufute key ku server, pitani pa gulu ya developer key mu akawunti yanu.

Kuti muone mafala anango, yang'anani [bukhu ya Cizungu](../README.md) na `omi --help`.
