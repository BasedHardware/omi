# Stat long omi-cli

Dispela gaid i stori long ol nambawan komand long Tok Pisin. Nem bilong ol komand
na tok save bilong program i stap yet long Tok Inglis. Ol dispela eksampel i no inap
senisim ol memori, toktok, wok o mak bilong yu.

## Instolim program

Ol samting yu nidim: Python 3.10 o nupela moa na wanpela Omi akaun.

Sapos yu gat `pipx`:

```sh
pipx install omi-cli
omi --help
```

Yu ken instolim tu insait long wanpela wok-ples bilong Python (virtual environment):

```sh
python -m pip install omi-cli
omi --help
```

Sapos terminal i no inap lukim `omi`, sekim sapos virtual environment i wok o `pipx` fail i stap insait long `$PATH` bilong yu.

## Pasim akaun bilong yu

Kirapim helpman bilong toktok:

```sh
omi auth login
```

Makim rot bilong go insait long brausa o pastim Omi divelopa API ki bilong yu.
Fasin bilong login long hia i haitim ki bilong yu; no ken raitim long komand we i ken stap long histeri bilong terminal.

Bilong go stret long brausa:

```sh
omi auth login --browser
```

Go insait long wankain kompiuta we terminal i wok long en. Bihainim ol tok save long skrin.

Bihain long dispela, sekim sevis na rot bilong go insait long API:

```sh
omi auth status
omi auth whoami
```

`status` i soim lukluk bilong masin na haitim sekret. `whoami` i salim askim bilong pruvim ki i wok gut.

Olgeta sait samting i stap long `~/.omi/config.toml`. No ken serim dispela fail bikos sekret ki i stap long en.

## Lukluk long ol data bilong yu

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Sapos em i stap emti, i no gat data i wankain long askim. Yusim help bilong lukim ol narapela rot:

```sh
omi memory list --help
omi action-item list --help
```

## Kisim JSON na lukim ol pes (Pagination)

Putim dispela bikpela `--json` **paslain** long grup bilong komand:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Nambawan komand i askim long 25 memori bilong pastaim; nambatu i askim long 25 i kam bihain. JSON i holim olgeta ID.

Bilong sevim wanpela pes long fail:

```sh
omi --json memory list --limit 25 --offset 0 > memori-pes-1.json
```

Dispela fail i ken gat ol personal tok save bilong yu: lukautim gut na haitim.

## Lusim akaun (Logout)

```sh
omi auth logout
```

Dispela komand i rausim ol login ki long dispela kompiuta tasol. Bilong pinisim tru ki long server, yusim divelopa ki sait insait long akaun bilong yu.

Bilong lukim ol narapela komand, lukim [bikpela gaid long Tok Inglis](../README.md) na `omi --help`.
