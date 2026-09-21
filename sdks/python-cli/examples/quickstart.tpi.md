# Ol fes stap wantaim omi-cli

Dispela buk i soim ol fes stap bilong omi-cli long Tok Pisin. Nem bilong ol command na tok bilong program i stap long Tok Inglis. Ol eksampel long dispela buk i no senisim ol tingting, ol toktok, ol wok na ol mak bilong yu.

## Insatim

Yu nid long Python 3.10 o antap, na wanpela Omi akaun.

Sapos `pipx` i stap pinis:

```sh
pipx install omi-cli
omi --help
```

O yu ken putim long wanpela Python virtual environment:

```sh
python -m pip install omi-cli
omi --help
```

Sapos terminal i no painim `omi`, sekim sapos virtual environment i wok o sapos folder bilong `pipx` i stap long `$PATH`.

## Joinim akaun bilong yu

Statim i interactive login wizard:

```sh
omi auth login
```

Yu ken makim: join long browser o pastim wanpela Omi developer API key. Samting yu putim i haitim key; lukaut, no larim em i stap long terminal history.

Bilong join stret long browser:

```sh
omi auth login --browser
```

Join long sem komputa we terminal i stap: tok i go bek long wanpela lokal adres. Biainim ol tok i kamap long skrin.

Nau sekim konfigaresen na API key:

```sh
omi auth status
omi auth whoami
```

`status` i soim dispela lokal sait nomo, na i haitim ol sekret, tasol i no sekim long server. `whoami` i salim wanpela authorised request; sapos i go gut, i minim ol kredensel bilong yu i wok, tasol i no soim nem bilong yu.

Konfigaresen i stap long `~/.omi/config.toml`. No serem dispela fail: ol sekret i ken stap insait.

## Lukim ol data

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Sapos list i emti, em i ken minim i no gat data i bihainim dispela askim. Bilong lain long ol filta bilong olgeta command, lukim help:

```sh
omi memory list --help
omi action-item list --help
```

## JSON na ol pes

Putim global option `--json` **pastaim** long grup bilong command:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Fes command i bringim i kam fes 25 tingting; namba tu i bringim narapela 25. Wanpela pes i no pulap olgeta taim. JSON i soim olgeta id, tasol tebol long skrin i save sotim ol.

Bilong raitim wanpela pes long fail:

```sh
omi --json memory list --limit 25 --offset 0 > tingting-pes-1.json
```

Redirect i wokim nupela fail o i raitim antap long wanpela fail i stap. Sekim sapos command i go gut pastaim, orait yusim. Ol eror i go long stderr; emti fail i no minim i no gat data. Exportim fail i ken holim ol sekret: kipim gut.

## Lausim

```sh
omi auth logout
```

Dispela command i rausim ol kredensel i stap long komputa. Bilong katim key long server, yusim developer key management long akaun bilong yu.

Bilong ol narapela command na ol antap option, lukim [Inglis gutbuk](../README.md) na `omi --help`.
