# Jalqaba Ariifachiisaa omi-cli wajjin

Qajeelfamni kun ajajoota jalqabaa Afaan Oromootiin ibsa. Maqaan ajajootaa fi ergaawwan sagantichaa Afaan Ingiliffaatiin hafu. Fakkeenyonni gaaffii (query) asitti agarsiifaman yaadannoo keessan (memories), haasaawwan (conversations), gochoota raawwataman (action items), yookiin galmoota (goals) hin jijjiiran.

## Saganticha fe'uu (Installation)

Ulaagaalee: Python 3.10 yookiin haarawaa fi herrega (account) Omi.

Yoo `pipx` duraan feetanii qabaattan:

```sh
pipx install omi-cli
omi --help
```

Akka filannoo biraatti, naannoo moluu Python (virtual environment) hojjetaa jiru keessatti fe'uu dandeessu:

```sh
python -m pip install omi-cli
omi --help
```

Yoo tarminaalichi `omi` argachuu baate, virtual environment hojjetaa jiraachuu yookiin kuusaan galmee `pipx` fayyadamu `$PATH` keessan keessa jiraachuu mirkaneeffadhaa.

## Herrega keessan walitti hidhuu (Authentication)

Gargaaraa waliin haasa'u (interactive assistant) eegalaa:

```sh
omi auth login
```

Brawzariidhaan seenuu yookiin furtuu Omi developer API maxxansuu filadhaa. Galchi kun furticha ni dhoksa; ajaja seenaa tarminaala keessatti hafu keessatti furtuu barreessuu irraa of qusadhaa.

Kallattiin gara brawzariitti deemuuf:

```sh
omi auth login --browser
```

Kompitaruma tarminaalli irratti hojjetaa jiru irraa seenaa: deebiin mirkaneessaa teessoo naannoo (local address) fayyadama. Qajeelfama iskiriinii irratti mul'atu hordofaa.

Sana booda, qindaa'ina fi eeyyama API mirkaneeffadhaa:

```sh
omi auth status
omi auth whoami
```

`status` haala naannoo agarsiisa akkasumas iccitii ni dhoksa, garuu seervarii irratti mirkanaa'uu isaa hin qoratu. `whoami` gaaffii mirkanaa'e erga; yoo milkaa'e, ragaan kun maqaa keessan osoo hin beeksisin hojjechaa jiraachuu mirkaneessa.

Qindaa'inni akkuma barametti `~/.omi/config.toml` keessatti olkawwama. Galmee kana namoota biraatiif hin qoodinaa sababiin isaas ragaalee iccitii keessan of keessaa qabaachuu danda'a.

## Daataa keessan sakatta'uu

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Tarreen duwwaa ta'e wanti gaaffichaan walsimu dhabamuu qofa agarsiisuu danda'a. Ajaja tokkoon tokkoo irratti calaltuuwwan argachuuf gargaarsa fayyadamaa:

```sh
omi memory list --help
omi action-item list --help
```

## JSON argachuu fi fuulawwan irra deemuu (Pagination)

Filannoo addunyaa `--json` jedhu garee ajajichaa **dura** kaa'aa:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Ajajni jalqabaa yaadannoo 25 duraa gaafata; inni lammaffaan, 25 itti aanu. Fuulli tokko kuusaa guutuu (backup) miti. Argansi JSON adda baastota guutuu ni tursa, gabateewwan iskiriinii garuu akka bareedutti mul'ataniif gabaabsuu danda'u.

Fuula tokko galmee keessatti olkaawuuf:

```sh
omi --json memory list --limit 25 --offset 0 > yaadannoo-fuula-1.json
```

Qajeelfamni kun galmee naannoo uuma yookiin bakka buusa. Qabiyyee isaa fayyadamuu dura ajajichi milkaa'inaan xumuramuusaa mirkaneeffadhaa. Dogoggorri galmee dogoggoraa (stderr) irratti barreeffama; galmeen duwwaan daataan hin jiru jechuu miti. Galmeen baafame odeeffannoo dhuunfaa of keessaa qabaachuu danda'a: eegumsaan olkaayaa.

## Herrega keessaa bahuu (Logout)

```sh
omi auth logout
```

Ajajni kun ragaalee naannotti olkaa'aman ni haqa. Furticha seervarii irratti haquuf, bulchiinsa furtuu oomishtootaa herrega keessan keessatti argamu fayyadamaa.

Ajajoota biraa fi filannoowwan bal'aaf, [qajeelfama guddaa Afaan Ingiliffaa](../README.md) fi `omi --help` ilaalaa.
