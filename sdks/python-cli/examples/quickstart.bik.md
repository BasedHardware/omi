# Mga Enot na Lakdang gamit an omi-cli

Ipinapaliwanag kaining giya an mga enot na pagboot (commands) sa tataramon na Bikol Sentral (Bikol). An mga ngaran kan pagboot asin mga mensahe kan programa nagdadanay sa Ingles. An mga halimbawa nin paghapot (query) na ipinapahiling digdi dai nagbabago kan saimong mga giromdom (memories), orolay (conversations), gigibohon (action items), o mga katuyohan (goals).

## Pag-instalar kan programa

Mga Kaipuhan: Python 3.10 o mas bagong bersyon asin sarong Omi account.

Kun igwa ka nin `pipx` na naka-instalar:

```sh
pipx install omi-cli
omi --help
```

Bilang alternatibo, pwede mo ini i-instalar sa laog nin sarong aktibong Python virtual environment:

```sh
python -m pip install omi-cli
omi --help
```

Kun dai mahanap kan terminal an `omi`, siguraduhon na aktibo an virtual environment o an direktoryo na pigbubugtakan kan `pipx` nin mga executable files yaon sa saimong `$PATH`.

## Pagkonektar kan saimong account

Poonan an interactive assistant:

```sh
omi auth login
```

Magpili sa tahaw kan pag-log in gamit an browser o an opsyon na i-paste an sarong Omi developer API key. Pigtatago kan interactive input an key; likayan an pagsurat kaini sa sarong pagboot na mawawalat sa kasaysayan (history) kan terminal.

Tanganing direktang magduman sa browser:

```sh
omi auth login --browser
```

Mag-log in sa parehong kompyuter kun saen nagdadalagan an terminal: naggagamit an simbag kan authentication nin sarong lokal na address. Sunodon an mga panugon sa screen.

Pagkatapos kaini, siyasaton an configuration asin pag-access sa API:

```sh
omi auth status
omi auth whoami
```

Ipinapahiling kan `status` an lokal na kamugtakan asin pigtatago an hilom, alagad dai kaini sinisiyasat an validity sa server. An `whoami` naggigibo nin sarong authenticated na kahagadan; kun mapanggana, pigpapatotoohan kaini na nagpupunsyonar an mga kredensyal, na dai kaipuhan ipahiling an saimong ngaran.

Naka-save an configuration bilang default sa `~/.omi/config.toml`. Dai pag-ipanao o pag-ihiras an file na ini: pwede ining magkaigwa kan saimong kompidensyal na mga kredensyal.

## Pagsiyasat kan saimong data

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

An sarong daing laog na listahan pwedeng nangangahulugan sana na mayong mga bagay na kapareho kan hapot. Gamiton an tabang tanganing maaraman an mga filter kan lambang pagboot:

```sh
omi memory list --help
omi action-item list --help
```

## Pagkua nin JSON asin pag-navigate sa mga pahina (Pagination)

Ikaag an pangkagabsan na opsyon na `--json` **bago** an grupo kan pagboot:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Pighahagad kan enot na pagboot an enot na 25 na mga giromdom; an ikaduwa, an masunod na 25. An sarong pahina bakong sarong bilog na backup. Pigtitipig kan output kan JSON an bilog na mga identifier, mantang pwedeng palip-oton kan mga lamesa sa screen ini para sa pagpahiling.

Tanganing mag-save nin sarong pahina paduman sa sarong file:

```sh
omi --json memory list --limit 25 --offset 0 > mga-giromdom-pahina-1.json
```

Ining pag-redirect naggigibo o nagsasalida kan lokal na file. Siguraduhon na mapangganang natapos an pagboot bago gamiton an laog kaini. An mga sala (errors) pigsusurat sa error output (stderr); an daing laog na file bakong garantiya na mayong data. An na-export na file pwedeng may laog nin personal na impormasyon: tipigan ini nin pribado.

## Pag-log out sa account (Logout)

```sh
omi auth logout
```

Pighahale kaining pagboot an mga kredensyal na nakasaray sa lokal na paagi. Tanganing magpawaing-bisa nin sarong key sa server, gamiton an pagpadalagan kan developer key sa saimong account.

Para sa iba pang mga pagboot asin mas hararom na mga opsyon, hilingon an [pangenot na giya sa Ingles](../README.md) asin `omi --help`.
