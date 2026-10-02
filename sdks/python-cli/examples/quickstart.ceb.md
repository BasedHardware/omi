# Mga Unang Lakang gamit ang omi-cli

Gipasabot niini nga giya ang mga unang mando (commands) sa pinulongang Sinugboanon (Cebuano / Bisaya). Ang mga ngalan sa mando ug mga mensahe sa programa magpabiling Iningles. Ang mga pananglitan sa query nga gipakita dinhi dili makausab sa imong mga handumanan (memories), panag-istoryahanay (conversations), buluhaton (action items), o mga tumong (goals).

## Pag-instalar sa programa

Mga Kinahanglanon: Python 3.10 o mas bag-ong bersyon ug usa ka Omi account.

Kung duna kay `pipx` nga na-instalar:

```sh
pipx install omi-cli
omi --help
```

Ingon nga alternatibo, mahimo nimo kining i-instalar sulod sa usa ka aktibong Python virtual environment:

```sh
python -m pip install omi-cli
omi --help
```

Kung dili makit-an sa terminal ang `omi`, siguroha nga aktibo ang virtual environment o ang direktoryo diin nag-instalar ang `pipx` anaa sa imong `$PATH`.

## Pagkonektar sa imong account

Sugdi ang interactive assistant:

```sh
omi auth login
```

Pagpili tali sa pag-log in pinaagi sa browser o ang opsyon nga i-paste ang usa ka Omi developer API key. Gitago sa interactive input ang key; likayi ang pagsulat niini sa usa ka mando nga magpabilin sa kasaysayan sa terminal.

Aron direktang moadto sa browser:

```sh
omi auth login --browser
```

Mag-log in sa parehong kompyuter diin nagdagan ang terminal: naggamit ang tubag sa authentication og usa ka lokal nga address. Sunda ang mga panudlo sa screen.

Human niana, susiha ang configuration ug access sa API:

```sh
omi auth status
omi auth whoami
```

Gipakita sa `status` ang lokal nga kahimtang ug gitago ang sekreto, apan dili kini mosusi sa validity didto sa server. Ang `whoami` naghimo og usa ka authenticated nga hangyo; kung malampuson, gikompirmar niini nga naglihok ang mga kredensyal, nga dili kinahanglan ipakita ang imong ngalan.

Naka-save ang configuration isip default sa `~/.omi/config.toml`. Ayaw ipaambit kini nga file: mahimo kining magsulod sa imong kompidensyal nga mga kredensyal.

## Pagsusi sa imong data

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Ang usa ka walay sulod nga listahan mahimong nagpasabot lang nga walay mga item nga motakdo sa query. Gamita ang tabang aron madiskobrehan ang mga filter sa matag mando:

```sh
omi memory list --help
omi action-item list --help
```

## Pagkuha og JSON ug pag-navigate sa mga panid (Pagination)

Ibutang ang tibuok-kalibotan nga opsyon nga `--json` **sa wala pa** ang grupo sa mando:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Gihangyo sa unang mando ang unang 25 ka handumanan; ang ikaduha, ang sunod nga 25. Ang usa ka panid dili usa ka kompleto nga backup. Gipreserbar sa output sa JSON ang tibuok nga mga identifier, samtang mahimong pamub-on sa mga lamesa sa screen kini alang sa pagpakita.

Aron mag-save og usa ka panid ngadto sa usa ka file:

```sh
omi --json memory list --limit 25 --offset 0 > mga-handumanan-panid-1.json
```

Kini nga pag-redirect naghimo o nag-ilis sa lokal nga file. Siguroha nga malampusong nahuman ang mando sa dili pa gamiton ang sulod niini. Ang mga sayop (errors) isulat sa error output (stderr); ang usa ka walay sulod nga file dili garantiya nga walay data. Ang na-export nga file mahimong magsulod og personal nga impormasyon: tipigi kini nga pribado.

## Pag-log out sa account (Logout)

```sh
omi auth logout
```

Gikuha niini nga mando ang mga kredensyal nga naka-save sa lokal nga paagi. Aron magpawalay-bili sa usa ka key sa server, gamita ang pagdumala sa developer key sa imong account.

Alang sa uban pang mga mando ug advanced options, tan-awa ang [pangunang giya sa Iningles](../README.md) ug `omi --help`.
