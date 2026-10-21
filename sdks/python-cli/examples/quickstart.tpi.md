# Fas sted wantaim omi-cli

Dispela gaid i soim ol fas sted (commands) bilong omi-cli long Tok Pisin. Ol nem bilong ol command na ol mesij bilong program i stap yet long Tok Inglis. Ol eksampel bilong painim samting i stap hia i no senisim ol memori (memories), ol storitok (conversations), ol wok (action items) o ol mak (goals) bilong yu.

## Installim

Samting i mas i stap: Python 3.10 o nupela moa, na wanpela Omi akaun.

Sapos yu gat `pipx`:

```sh
pipx install omi-cli
omi --help
```

Yu inap installim long wanpela Python virtual environment tu:

```sh
python -m pip install omi-cli
omi --help
```

Sapos terminal i no lukim `omi`, sekurim olsem virtual environment i wok o olsem `pipx` folda i stap long `$PATH`.

## Konectim akaun bilong yu

Statim asisten bilong toktok:

```sh
omi auth login
```

Pilim long go insait long browser o peisim wanpela Omi developer API ki. Interaktiv input i haitim ki; abrusim long raitim ki long wanpela command i bai stap long terminal history.

Long go stret long browser:

```sh
omi auth login --browser
```

Go insait long sem komputa olsem terminal: autentikesen bekim i go long lokal adres. Biainim ol tok i stap long skrin.

Bihain, sekim konfigeresen na API akses:

```sh
omi auth status
omi auth whoami
```

`status` i soim lokal pasin na haitim sekret, tasol i no sekim sapos i stret long server. `whoami` i mekim autentiketit rikwest; sapos i go gut, i klia olsem ol kredensel i wok, i no soim nem bilong yu.

Konfigeresen i stap long `~/.omi/config.toml`. No seraunim dispela fail: inap gat privat kredensel long en.

## Lukim data bilong yu

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Wanpela lista i no gat samting long en i min olsem i no gat samting i bihainim painim. Yusim help long painim ol filta bilong wanwan command:

```sh
omi memory list --help
omi action-item list --help
```

## JSON na pes

Putim global opsen `--json` **bipo** long command grup:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Fas command i askim fas 25 memori; namba tu i askim narapela 25. Wanpela pes i no ful kopi. JSON i seivim ol namba olgeta, tasol ol tebol long skrin inap sotim ol.

Long seivim wanpela pes long wanpela fail:

```sh
omi --json memory list --limit 25 --offset 0 > memori-pes-1.json
```

Dispela redirect i mekim o raitim antap long wanpela lokal fail. Sekurim olsem command i pinis bipo long yusim konten. Ol ero i go long ero output (stderr); wanpela fail i no gat samting long en i no pruv olsem i no gat data. Wanpela fail i bin ekspot inap gat personal infomesen: seivim em i privat.

## Lusim

```sh
omi auth logout
```

Dispela command i rausim ol kredensel i stap long lokal. Long mekim wanpela ki i no wok long server, yusim developer ki menesmen long akaun bilong yu yet.

Long moa command na opsen, lukim [bikpela gaid long Tok Inglis](../README.md) na `omi --help`.
