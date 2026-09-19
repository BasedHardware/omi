# Mga Syahan nga Pagpitad gamit an omi-cli

Ginsasaysay hini nga giya an mga syahan nga sugo (commands) ha yinaknan nga Winaray (Waray-Waray). An mga ngaran han sugo ngan mga mensahe han programa nagpapabilin ha Iningles. An mga pananglitan han pagbiling (query) nga ginpapakita dinhi diri nagbabalyo han imo mga handumanan (memories), pakiistorya (conversations), buruhaton (action items), o mga panuyuan (goals).

## Pag-instalar han programa

Mga Kinahanglanon: Python 3.10 o mas bag-o nga bersyon ngan usa nga Omi account.

Kon may-ada ka `pipx` nga na-instalar:

```sh
pipx install omi-cli
omi --help
```

Puyde liwat ini i-instalar ha sulod hin aktibo nga Python virtual environment:

```sh
python -m pip install omi-cli
omi --help
```

Kon diri mabilngan han terminal an `omi`, siguroha nga aktibo an virtual environment o an direktoryo nga ginbubutangan han `pipx` hin mga executable files aada ha imo `$PATH`.

## Pagsumpay han imo account

Tikangi an interactive assistant:

```sh
omi auth login
```

Pamili ha butnga han pag-log in pinaagi han browser o an opsyon nga i-paste an usa nga Omi developer API key. Gintatago han interactive input an key; likyi an pagsurat hini ha usa nga sugo nga mahibibilin ha kaagi (history) han terminal.

Basi diritso nga kumadto ha browser:

```sh
omi auth login --browser
```

Mag-log in ha pareho nga kompyuter kun diin nadalagan an terminal: nagamit an baton han authentication hin usa nga lokal nga address. Sunda an mga sumbanan ha screen.

Kahuman hini, usisaha an configuration ngan pag-access ha API:

```sh
omi auth status
omi auth whoami
```

Ginpapakita han `status` an lokal nga kahimtang ngan gintatago an sekreto, pero diri ini nag-uusisa han validity didto ha server. An `whoami` naghihimo hin usa nga authenticated nga hangyo; kon madinaluson, ginkukompirmar hini nga nagios an mga kredensyal, nga diri nagkikinahanglan igpakita an imo ngaran.

Naka-save an configuration komo default ha `~/.omi/config.toml`. Ayaw igpaangbit ini nga file: bangin may sulod ini han imo kompidensyal nga mga kredensyal.

## Pag-usisa han imo data

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

An waray sulod nga listahan bangin nagpapasabot la nga waray mga butang nga naangay ha pamangkot. Gamita an bulig basi mahibaroan an mga filter han tagsa nga sugo:

```sh
omi memory list --help
omi action-item list --help
```

## Pagkuha hin JSON ngan pag-navigate ha mga pakli (Pagination)

Ibutang an kabug-osan nga opsyon nga `--json` **san-o** an grupo han sugo:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Ginhahangyo han syahan nga sugo an syahan nga 25 nga mga handumanan; an ikaduha, an masunod nga 25. An usa nga pakli diri usa nga bug-os nga backup. Ginhihipos han output han JSON an bug-os nga mga identifier, samtang puyde palip-uton han mga lamesa ha screen ini para ha pagpakita.

Basi mag-save hin usa nga pakli ngadto ha usa nga file:

```sh
omi --json memory list --limit 25 --offset 0 > mga-handumanan-pakli-1.json
```

Ini nga pag-redirect naghihimo o nagbabalyo han lokal nga file. Siguroha nga madinaluson nga nahuman an sugo san-o gamiton an sulod hini. An mga sayop (errors) iginsusurat ha error output (stderr); an waray sulod nga file diri garantiya nga waray data. An na-export nga file bangin may sulod hin personal nga impormasyon: hiposa ini nga pribado.

## Pag-log out ha account (Logout)

```sh
omi auth logout
```

Ginkuha hini nga sugo an mga kredensyal nga naka-save ha lokal nga paagi. Basi magpawaay-bili hin usa nga key ha server, gamita an pagdumara han developer key ha imo account.

Para ha iba pa nga mga sugo ngan mas abante nga mga opsyon, kitaa an [pangunahon nga giya ha Iningles](../README.md) ngan `omi --help`.
