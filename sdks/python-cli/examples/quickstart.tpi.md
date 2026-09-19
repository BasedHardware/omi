# Namba Wan Stiat wantaim omi-cli

Dispela buk i tok klia long ol nambawan komon long Tok Pisin. Ol nem bilong komon
na toksave bilong program i stap long Tok Inglis tasol. Ol eksampel long hia i no
ken senisim ol tingting, toktok, wok, o mak bilong yu.

## Putim program (Install)

Ol samting yu mas gat: Python 3.10 o nupela moa na wanpela akaun long Omi.

Sapos yu gat `pipx`:

```sh
pipx install omi-cli
omi --help
```

Yu ken putim tu long wanpela virtual environment long Python:

```sh
python -m pip install omi-cli
omi --help
```

## Pasim akaun bilong yu

Statim wok bilong login:

```sh
omi auth login
```

Makim long go long browser o putim API ki bilong Omi.

Go stret long browser:

```sh
omi auth login --browser
```

Bihain, sekim wok bilong API:

```sh
omi auth status
omi auth whoami
```

Dispela i save stap long `~/.omi/config.toml`. No ken givim long narapela man.

## Lukim ol data bilong yu

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

## Kisim JSON na lukim ol pes

Putim `--json` paslain long komon:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Sevim wanpela pes long fail:

```sh
omi --json memory list --limit 25 --offset 0 > memory-pes-1.json
```

## Lusim (Logout)

```sh
omi auth logout
```

Lukim moa toksave long [bikpela buk long Tok Inglis](../README.md) na `omi --help`.
