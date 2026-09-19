# omi-cli Bee Haʼalzhish Biyáazh Naaltsoos

Díí naaltsoos éí Diné bizaad bee omi-cli bee haʼalzhish yaa halneʼ. Commands dóó messages éí Bilagáana bizaad bee baa nidahwiilʼįįh dooleeł. Kweʼé naaltsoos bikáaʼgi éí ni-memories, conversaciones, action items, doodaiiʼ goals doo łahgo áńdoolníił da.

## Program biih yilʼaah

Bíkáʼátʼé: Python 3.10 doodaiiʼ biláahdi, dóó Omi account.

`pipx` bee hólǫ́ǫgo:

```sh
pipx install omi-cli
omi --help
```

Doodaiiʼ Python virtual environment biyiʼdi:

```sh
python -m pip install omi-cli
omi --help
```

## Ni-account bee ałhééhoolzheeh

Interactive assistant bee haʼalzhish:

```sh
omi auth login
```

Browser doodaiiʼ Omi developer API key bee yókeedgo átʼé.

Browser tʼáá ákótʼéego:

```sh
omi auth login --browser
```

Ákóneʼ API bídéetʼíinii bináʼádoolkid:

```sh
omi auth status
omi auth whoami
```

`status` éí kótʼéego ałhééhoolzheeh yaa halneʼ, áko `whoami` éí credentials yáʼátʼéehii yaa halneʼ.

## Níká bídéetʼíinii bináʼádoolkid

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Bíká adoolwołígíí:

```sh
omi memory list --help
omi action-item list --help
```

## JSON dóó Naaltsoos Naanééł Pagination

Global option `--json` tʼáá biláahdi biih yiyíłtsóós:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Naaltsoos biyiʼ biih yiłtsós:

```sh
omi --json memory list --limit 25 --offset 0 > memories-page-1.json
```

## Chʼéghááh dóó ałtso

```sh
omi auth logout
```

Díí éí credentials nahjįʼ kóyiilaa.

Tʼáá íiyisíí [Bilagáana bizaad naaltsoos](../README.md) dóó `omi --help` bił bééhózin.
