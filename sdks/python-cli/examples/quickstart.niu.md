# Tau hala fakamua mo omi-cli

Tohi nei e fakamaama e tau hala fakamua (commands) he omi-cli he vagahau Niue. Ko e tau hingoa he tau command mo e tau fekau he polokalama ka nofo he vagahau Peretania. Ko e tau fakatai he kumi e fakaaoga henei nakai fakaheke haau a tau manatu (memories), tau tutala (conversations), tau gahua (action items) mo e tau kupu (goals).

## Fakatuu

Mena e manako: Python 3.10 pe mua atu, mo e taha akaute Omi.

Ka e ha haau a `pipx`:

```sh
pipx install omi-cli
omi --help
```

Ka e mafai foki ke fakatuu he Python virtual environment:

```sh
python -m pip install omi-cli
omi --help
```

Ka nakai kitia e terminal a `omi`, fakamautu ka e gahua e virtual environment pe ko e `pipx` folda e nofo he `$PATH`.

## Fekau ki haau akaute

Kamata e lagomatai:

```sh
omi auth login
```

Filih ke hū atu he browser pe ke fakapiki e Omi developer API key. Ko e hū atu e fufu e key; nākai tohi e key he command ka nofo he terminal history. Hū atu hako he browser:

```sh
omi auth login --browser
```

Hū atu he komipiuta taha mo e terminal: ko e authentication ka o ki te local address. Mumu ki e tau fakatonu he lau.

Hili, sivi e configuration mo e API:

```sh
omi auth status
omi auth whoami
```

`status` e fakakite e tuaga he loto mo e fufu e secret, ka e nakai sivi e server. `whoami` e ta e authenticated request; ka e manuia, e maama e gahua e credentials. Ko e configuration e nofo he `~/.omi/config.toml`. Nākai tufa: private credentials.

## Kitekite haau data

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Ko e lisi gaogao e fakakite nakai ha mena. Fakaaoga e lagomatai ki e tau filter:

```sh
omi memory list --help
omi action-item list --help
```

## JSON mo e tau laupepa

Tuu e `--json` **he mua** he command group:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Ko e command fakamua e ole ki e 25; ko e ua e ole ki e 25 ka e sosoo. Ko e laupepa taha nakai ko e kopi katoa. JSON e taupau e tau numela katoa; tau laulau he lau ka fakapuupuu.

Ki ha faila:

```sh
omi --json memory list --limit 25 --offset 0 > memories-laupepa-1.json
```

Ko e command kua oti. Errors he stderr; faila gaogao nakai data. Private.

## Fakaoti

```sh
omi auth logout
```

Local credentials. Developer key.

[Peretania](../README.md) mo `omi --help`.
