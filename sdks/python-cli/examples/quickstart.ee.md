# Mɔfiame Kpuie na omi-cli

Mɔfiame sia ɖe sedede gbãtɔwo me le Eʋegbe me na `omi-cli`. Sedede ƒe ŋkɔwo kple dɔwɔƒu ƒe gbedeasiwo anɔ Yevugbe me. Kpɔɖeŋu siwo wofia le afi sia matrɔ wò ŋkuɖodzinyawo (memories), dzeɖoɖowo (conversations), dɔwɔwɔwo (action items), alo taɖodzinuwo (goals) o.

## Dɔwɔƒu la ƒe ɖoɖo (Installation)

Nusiwo hia: Python 3.10 alo esi yɔ fiawu kple Omi akɔnta.

Ne `pipx` le asiwò xoxo:

```sh
pipx install omi-cli
omi --help
```

Àte ŋu aɖoe ɖe Python ƒe virtual environment si le dɔwɔm me hã:

```sh
python -m pip install omi-cli
omi --help
```

Ne terminal la mekpɔ sedede `omi` o, kpɔ egbɔ be virtual environment la le dɔwɔm alo be afisi `pipx` le la le wò `$PATH` me.

## Wò akɔnta kadodo (Authentication)

Dze kpekpeɖeŋunala dɔwɔƒe la gɔme:

```sh
omi auth login
```

Tia be yeato browser me alo azã Omi developer API key. Dɔwɔƒe sia aɣla wò safui la; mègawɔe ɖe sedede me be wòatsi terminal ŋutinya me o.

Ne èdi be yeawoe tẽe le browser me:

```sh
omi auth login --browser
```

Ge ɖe kɔmpiuta ɖeka ma si dzi terminal la le dɔwɔm le la dzi: kadodo ƒe ŋuɖoɖo zãa du sia du ƒe adrɛs. Wɔ nusiwo katã dze le kɔmpiuta ƒe mo dzi la dzi.

Le ema megbe la, kpɔ ɖoɖowo kple API ƒe mɔnukpɔkpɔ gbɔ:

```sh
omi auth status
omi auth whoami
```

`status` fiana afisi nɔnɔmea le le wò afi eye wòɣlaa nya ɣaɣlawo, gake meɖoa kpe edzi tso server la gbɔ o. `whoami` ɖoa biabia si me mɔɖeɖe le la ɖa; ne edze edzi la, eɖoa kpe edzi be wò safuiwo le dɔwɔm nyuie evɔ mefia wò ŋkɔ o.

Wodzraa ɖoɖowo ɖo zi geɖe ɖe `~/.omi/config.toml` me. Mègana agbalẽ sia amewo o: nya ɣaɣlawo ate ŋu anɔ eme.

## Wò nyawo me dzodzro (Inspection)

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Kplɔ̃ ƒuƒlu ate ŋu afia ko be nane aɖeke medze le didi la me o. Zã kpekpeɖeŋununya be nàkpɔ tiatiawo le sedede ɖesiaɖe me:

```sh
omi memory list --help
omi action-item list --help
```

## JSON ƒe xɔxɔ kple Axawo ƒe mɔzɔzɔ (Pagination)

Da tiatia `--json` sia **do ŋgɔ** na sedede ƒe ƒuƒoƒo la:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Sedede gbãtɔ biaa ŋkuɖodzinya 25 gbãtɔwo; evelia biaa 25 siwo kplɔe ɖo. Axa ɖeka menye nyawo katã ƒe dzadzraɖo o. JSON nyawo léa ŋkɔ bliboawo ɖe te, togbɔ be kɔmpiuta ƒe tebluwo ate ŋu aɖe wo dzi akpɔtɔ hã.

Ne èdi be yeatsɔ axa aɖe aɖo agbalẽ me:

```sh
omi --json memory list --limit 25 --offset 0 > nkuɖodzinyawo-axa-1.json
```

Mɔ sia tua agbalẽ yeye alo trɔa esi le afima xoxo. Kpɔ egbɔ be sedede la wu enu nyuie hafi nàzã nya siwo le eme. Vodadawo dzena le vodedenuŋɔŋlɔ me (stderr); agbalẽ ƒuƒlu mefia be naneke mele teƒe o. Agbalẽ si nèxɔ la ate ŋu anye wò ŋutɔ wò nya ɣaɣlawo: dzrae ɖo nyuie.

## Akɔnta me dodo (Logout)

```sh
omi auth logout
```

Sedede sia ɖea safui siwo wodzra ɖo le wò afi la ɖa. Ne èdi be yeaɖe safui aɖe ɖa le server la dzi la, zã developer key dzikpɔƒe le wò akɔnta me.

Na sedede bubuwo kple tiatia geɖewo la, kpɔ [Yevugbe me mɔfiame vevi la](../README.md) kple `omi --help`.
