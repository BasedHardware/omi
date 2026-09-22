# Kusokela na omi-cli

Mukanda ewu uleja ba commandes ba kusokela ba omi-cli mu Kiluba. Majina a ba commandes ne milejelo ya programme bikwikala mu Anglais. Ba exemples badi pano kabiisaulula memories, conversations, action items, toba goals yobe.

## Kuteka

Udi mukwete: Python 3.10 toba udi mupitu, ne compte ya Omi.

Pambadilu pipx itekele:

```sh
pipx install omi-cli
omi --help
```

Toba mu Python virtual environment udi muactiveshanga:

```sh
python -m pip install omi-cli
omi --help
```

Tambuisha: commande `omi` ifimba kusangana pa PATH kabedi — langulula ne virtual environment idi active toba direktili ya pipx idi mu `$PATH`.

## Kwingija

Kwingija kumpala:

```sh
omi auth login
```

Udi mulongesha kwingija ne navigateur toba ne clé ya API ya Omi developer. Tapila clé — kayiinjile mu historique ya terminal.

Kwingija ne navigateur pa ordinatère ewu:

```sh
omi auth login --browser
```

Pa ba machines badi ne terminal bua: autorisation ikaluka pa adresse locale. Konda milongeselo idi pa ecran.

Langulula configuration ne clé API ya nomba:

```sh
omi auth status
omi auth whoami
```

`status` ileja bualu bwa locale, ifisa ba secrets, kayiikongolease serveur. `whoami` ituma demande ya authentification; pambadilu ikalakila, ikaleja ne credentials yobe ikela bimpe.

Configuration ikasungwa mu `~/.omi/config.toml`. Kansokolole afayilo ewu ne maboko — ba secrets ba clé bala muinene.

## Balelo ba memories ne conversations

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Pambadilu liste idi vide, ikaleja bua ne kakudi bualu. Kulangulula ba filtres ba commande yonso:

```sh
omi memory list --help
omi action-item list --help
```

## JSON ne ba exports

Option globale `--json` ifiketeba kubala KUMPAALA kwa groupe ya ba commandes:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Commande ya kumpala ikabalwa ba memories balumi bambidi ne butanu ba kumpala; ya bubidi ikabalwa ba bakwabo balumi bambidi ne butanu. JSON output ikwatsha ba identifiers ba nshimba, kadi tableau ikakonda bupi.

Kusungisha mu afayilo:

```sh
omi --json memory list --limit 25 --offset 0 > memories-lukasa-1.json
```

Redirect ewu ikasumba afayilo ya locale ya mipia toba ikaijula ya kale. Tangila bualu bwa commande kumpala. Ba erreurs baluka mu stderr; afayilo vide kayileja ne bualu kabudia. Ba fichiers ya export balongesha kukwatsha informations personnelles — ubasungile bimpe.

## Kufuma

```sh
omi auth logout
```

Commande ewu ikafumisha ba credentials ya locale. Ba clés bakelwe pa serveur bala pansi pa gestion ya ba clés ya developer.

Bya bungi: [ba docs ya Anglais](../README.md) ne `omi --help`.
