# Kony Mapiyo mar omi-cli

Kony mar Dholuo (Luo) ma lero chik ma nyaka ichak godo mar `omi-cli`. Nying chike gi ote mag program biro siko e Dho-Ngere. Ranyisi mag nono ma oyier ka ok bi loko paro magi (memories), mbaka (conversations), tije ma onego itim (action items), kata dwaro magi (goals).

## Keto program e kompyuta (Installation)

Gik ma dwarore: Python 3.10 kata manyien moloyo kaachiel gi akaunt mar Omi.

Ka koro iseketo `pipx`:

```sh
pipx install omi-cli
omi --help
```

Inyalo keto bende e alwora ma tiyo mar Python (virtual environment):

```sh
python -m pip install omi-cli
omi --help
```

Ka chik mar `omi` ok oyudore e terminal, tem nono kabe virtual environment tiyo kata ka yo mar `pipx` nitie e `$PATH` mari.

## Tudruok gi akaunt mari (Authentication)

Chak jakony ma iwuoyo kode:

```sh
omi auth login
```

Yier donjo kokalo kuom browser kata keto Omi developer API key mari. Yo ma lero chik pando kaye; kik indik kaye e chike ma nyalo siko e sigana mar terminal.

Mondo idhi e browser achiel kachiel:

```sh
omi auth login --browser
```

Donj e kompyuta ma terminal tiye: dwoko mar ratiro tiyo gi keyo mar giko. Luw chike ma oyier e skrin.

Bang' mano, non ratiro gi dhi e API:

```sh
omi auth status
omi auth whoami
```

`status` nyiso chal mar giko kendo pando gik ma kondo, to ok onon kabe otiyo maber e seba (server). `whoami` oro kwayo ma oratiro; ka odhi maber, osingo ni gik moko tiyo maber ma ok ochuno nyiso nyingi.

Polo mar ratiro koro okan e `~/.omi/config.toml`. Kik ipog fayilni gi jomoko: onyalo bedo gi ratiro ma opondo.

## Nono gik magi (Inspection)

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Chenro ma onge gimoro nyalo nyiso mana ni onge gima oyudore koting'o gima idwaro. Tiy gi kony mondo iyud chike mong'ith e chik ka chik:

```sh
omi memory list --help
omi action-item list --help
```

## Yudo JSON gi Pogo Oboke (Pagination)

Ket chik mar piny ngima `--json` **e nyim** chike mag kanyakla:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Chik mokwongo kwayo paro 25 mokwongo; mar ariyo kwayo 25 ma luwo. Oboke achiel ok en kano gik moko duto (backup). Dwoko mar JSON kano rang'iny mag nyinge duto, kata obedo ni mbesa mag skrin nyalo tin-yo mondo onere maber.

Mondo ikan oboke e fayil:

```sh
omi --json memory list --limit 25 --offset 0 > paro-oboke-1.json
```

Yoni loso kata loko fayil mar giko. Ne ni chik otiek maber kapok itiyo gi gik ma nitie iye. Ketho ondik e alwora mar ketho (stderr); fayil ma onge gimoro ok nyis ni onge weche. Fayil ma ogol nyalo bedo gi weche magi iwuon: riting'e maber.

## Wuok e akaunt (Logout)

```sh
omi auth logout
```

Chikni golo ratiro ma okan e giko. Mondo igol ratiro e seba, ti gi ratiro mar developer key e akaunt mari.

Ne chike mamoko gi yiero mamoko, ne [kony maduong' mar Dho-Ngere](../README.md) gi `omi --help`.
