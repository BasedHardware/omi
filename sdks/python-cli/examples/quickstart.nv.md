# Áłtsé bee omi-cli

Díí naʼnitin éí omi-cli yee áłtsé bee naʼanishígíí Diné bizaadjí bee haneʼ. Command bee yízhí dóó program bee íhalneʼígíí éí Bilagáana kʼehjí. Kweʼé bee íhooʼaahígíí éí tʼáá yíníłtsą́ą́ʼ tʼéiyá — ni niééʼ (memories), saad (conversations), naanish (action items) dóó bee haʼííná (goals) doo łahgo ádeileʼ da.

## Bee áłtsé iiníłʼįįh

Tʼáá íídą́ą́ʼ: Python 3.10 doodaiiʼ ániidíbiláah, dóó Omi akʼeʼelchí (account).

`pipx` bee hólǫ́ǫgo:

```sh
pipx install omi-cli
omi --help
```

Doodaiiʼ Python virtual environment biyiʼ ádíílííł:

```sh
python -m pip install omi-cli
omi --help
```

Tʼáá terminal éí `omi` doo yitʼįįh da łeh — tʼáá áko virtual environment hólǫ́ǫgíí índa `pipx` folder `$PATH` biyiʼ hólǫ́ǫgíí nídííłtsą́ą́ʼ.

## Yah anááhootʼįįh

Yah anááhootʼįįhí bee hashtʼe:

```sh
omi auth login
```

Browser doodaiiʼ Omi developer API key bee yah anááhootʼįįh. Key éí naʼásdlįį — tʼáadoo terminal history biyiʼ yííʼáah.

Browser bee tʼáá ákwii jįʼ yah anááhootʼįįh:

```sh
omi auth login --browser
```

Tʼáá terminal bee naʼanishígíí bikʼi computer ánítʼįįh: authorization éí local address choyoołʼįįh. Screen bikáaʼgi naaltsoosígíí yikʼehgo ííłʼįįh.

Kʼad configuration dóó API key nídííłtsą́ą́ʼ:

```sh
omi auth status
omi auth whoami
```

`status` éí local bee haneʼ chʼééh yiłtsą́ dóó secrets naʼásdlįį, ndi server bikáaʼgi doo néidiłkid da. `whoami` éí authenticated request ádíílííł; yáʼátʼééhgo, credentials naʼanishígíí tʼáá ákogo nidził, doo niyízhí baa hóółtą́ą da.

Configuration éí `~/.omi/config.toml` biyiʼ naazįį. Díí file tʼáadoo chʼééh ííshjání — key secrets biyiʼ hólǫ́.

## Niééʼ dóó saad yíníłtsą́ą́ʼ

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Hó ádin list éí bee nídíłkidígíí doo hólǫ́ǫ da tʼéiyá. Tʼáá command bee filters hólǫ́ǫgíí nídííłtsą́ą́ʼ:

```sh
omi memory list --help
omi action-item list --help
```

## JSON dóó naaltsoos

Global `--json` option éí command group **áłtsé** hashtʼe:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Áłtsé command éí 25 niééʼ áłtséjįʼ nídíídíłkid; naaki góneʼígíí éí keedaʼ 25. Tʼááłáʼí saife éí tʼáá ałtso backup doo yee ádin da. JSON éí tʼáá ałtso identifier yee hólǫ́, ndi table éí yázhíigo ádíílííł łeh.

Saife biyiʼ yóóʼaah:

```sh
omi --json memory list --limit 25 --offset 0 > niééʼ-naaltsoos-1.json
```

Díí redirect éí local file ániidí ádíílííł doodaiiʼ bikááʼ ádíílííł. Content tʼáadoo chʼééh ííshjání, áłtsé command yíníłtsą́ą́ʼ. Errors éí stderr biyiʼ naaghá; hó ádin file éí data ádin, yee doo ádin da. Export file éí personal info hólǫ́ǫ doo — tʼáadoo chʼééh ííshjání.

## Yiigááł (Logout)

```sh
omi auth logout
```

Local credentials éí díí command bee yóóʼiidįįh. Server bikáaʼgi key bee ádíílííłígíí éí developer key management (`account` biyiʼ) choyoołʼįįh.

Ałdóʼ command dóó option hólǫ́ǫgíí: [Bilagáana kʼehjí naaltsoos](../README.md) dóó `omi --help`.
