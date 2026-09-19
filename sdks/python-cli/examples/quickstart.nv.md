# Áłtsé bee omi-cli

Díí naʼnitin éí omi-cli yee áłtsé bee óhooʼaah (commands) Diné bizaadjí. Command yee áhalneʼígíí éí Bilagáana kʼehjí. Áłtsé bee óhooʼaah doo łahgo ániidí: niééʼ (memories), saad (conversations), naanish (action items), índa bee haʼííná (goals).

## Bee yínííł

Yáʼátʼéehgo: Python 3.10 índa Omi akʼeʼelchí (account).

`pipx` bee:

```sh
pipx install omi-cli
omi --help
```

Tʼáá ałtsʼísígo Python virtual environment bee ałdóʼ:

```sh
python -m pip install omi-cli
omi --help
```

Tʼáá `omi` doo yitʼínígíí, virtual environment yáʼátʼéehii índa `pipx` folder `$PATH` biyiʼ.

## Akʼeʼelchí bee yah anáhootʼįį

Asistęnt yíníłtą́:

```sh
omi auth login
```

Browser bee yah anáhootʼįį doodaiiʼ Omi developer API key. Kʼad hashtʼeʼ key baa áhósin — doo terminal history biyiʼ ádíílííł da.

Browser tʼáá ákwííjí:

```sh
omi auth login --browser
```

Tʼáá terminal bíighahgi computer yah anáhootʼįį: authentication binaaltsoos local address. Naaltsoos bikáaʼgi yíhoołʼaah.

Kʼad konfiguration índa API:

```sh
omi auth status
omi auth whoami
```

`status` local bee haneʼ índa secret bee ádíílííł, ndi server bikáaʼgi doo yíłchʼįįł da. `whoami` authenticated request; yáʼátʼéehgo, credentials daatsʼí yáʼátʼéeh, doo shí éʼéʼáahjí.

Konfiguration `~/.omi/config.toml` biyiʼ. Tʼáadoo chʼééh ííshjání — private credentials hólǫ́.

## Niééʼ yíníłtsą́ą́ʼ

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Tʼáá hó ádin list — tʼáá ákwííjí. Help bee filter:

```sh
omi memory list --help
omi action-item list --help
```

## JSON índa naaltsoos

`--json` **áłtsé** command group:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Áłtsé command 25 memories; naaki góneʼ 25. Tʼááłáʼí page doo tʼáá ałtso da. JSON tʼáá ałtso numbers; table éí yázhí.

Page file biyiʼ:

```sh
omi --json memory list --limit 25 --offset 0 > memory-page-1.json
```

Áko file ániidí doodaiiʼ łahgo ályaa. Command tʼáá ałtso bikʼehgo. Errors stderr; tʼáá hó ádin file doo data ádin da. Personal information hólǫ́ — private.

## Yiigááł

```sh
omi auth logout
```

Local credentials niʼ. Server key bee ádíílííł — developer key management.

Tʼáá ałtso commands índa options: [Bilagáana naaltsoos](../README.md) índa `omi --help`.
