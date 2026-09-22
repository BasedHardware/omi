# Fes stef wetem omi-cli

Buk ya i eksplenem fes komand (commands) blong omi-cli long Bislama. Nem blong ol komand mo ol mesij blong program ya oli stap long Inglis. Ol eksampol blong lukaotem we oli soem long hia oli no jenisim ol memori (memories), ol storian (conversations), ol wok (action items) o ol aksen (goals) blong yu.

## Instolem

Samting we yu nidim: Python 3.10 o mo nyu, mo wan Omi akaont.

Sapos yu gat `pipx`:

```sh
pipx install omi-cli
omi --help
```

Yu save instolem long wan Python virtual environment tu:

```sh
python -m pip install omi-cli
omi --help
```

Sapos terminal i no faenem `omi`, mekem se virtual environment i wok o `pipx` folder i stap long `$PATH`.

## Konetem akaont blong yu

Statem asisten blong tok:

```sh
omi auth login
```

Yu save jusum blong go insaed long browser o blong pastem wan Omi developer API ki. Interaktiv input i haedem ki ya; no raetem ki ya long wan komand we bae i stap long histri blong terminal.

Blong go stret long browser:

```sh
omi auth login --browser
```

Go insaed long sem kompyuta olsem terminal: ansa blong autentikesen i go long lokal adres. Folem ol instruksen long skrin.

Biaen, sekem konfiguresen mo API akses:

```sh
omi auth status
omi auth whoami
```

`status` i soem lokal stet mo i haedem sekret, be i no sekem sapos i stret long server. `whoami` i mekem wan autentiket request; sapos i wok, i klia se ol kredensel oli wok, i no soem nem blong yu.

Konfiguresen i stap long `~/.omi/config.toml`. No seraonem fail ya: i save gat privat kredensel.

## Lukluk long data blong yu

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Wan empti list i minim se i no gat samting we i matj long lukaotem ya. Yusum help blong faenem ol filta blong evri komand:

```sh
omi memory list --help
omi action-item list --help
```

## JSON mo pej

Putum global opsen `--json` **bifo** komand grup:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Fes komand i askem fes 25 memori; namba tu i askem narafala 25. Wan pej nomo i no ful kopi. JSON i kipim ol ful namba, be ol tebol long skrin oli save sotem ol.

Blong sevem wan pej long wan fail:

```sh
omi --json memory list --limit 25 --offset 0 > memori-pej-1.json
```

Redireksen ya i mekem o i raetem antap long wan lokal fail. Mekem se komand i finis bifo yu yusum konten blong hem. Ol ero oli go long ero output (stderr); wan empti fail i no pruf se i no gat data. Wan fail we yu ekspotem i save gat personal infomesen: kipim hem privat.

## Kamaot

```sh
omi auth logout
```

Komand ya i raosem ol kredensel we oli stap long lokal. Blong mekem wan ki i no wok moa long server, yusum developer ki menesmen long akaont blong yu yet.

Blong moa komand mo opsen, luk long [bikfala gid long Inglis](../README.md) mo `omi --help`.
