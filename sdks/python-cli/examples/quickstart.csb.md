# Pierszé kroczi z omi-cli

Ten przewodnik wëjasniwô pierszé pòlécania (commands) omi-cli w kaszëbsczim jãzëkù. Miona pòléceń i wiadła programù òstôwają w anielsczim jãzëkù. Przëmiarë szëkbë ùkôzóné tu nie zmieniają twòjich wspòminków (memories), rozgòdów (conversations), robòtów (action items) ani célów (goals).

## Instalacjô

Wòlné: Python 3.10 abò nowszi, i kònto Omi.

Jeżlë môsz `pipx`:

```sh
pipx install omi-cli
omi --help
```

Mòżesz téż zainstalowac w aktiwnym Python-wirtualnym òkòlim:

```sh
python -m pip install omi-cli
omi --help
```

Jeżlë terminal nie nalezô `omi`, sparłãczë sã, że wirtualné òkòlim dzejô abò że katalog `pipx` je w `$PATH`.

## Sparłãczenié kònta

Zaczni interaktiwnégò pòmòcnika:

```sh
omi auth login
```

Wëbierzë wlogòwanié przez browser abò wlëczenié klucza Omi developer API. Interaktiwny wród krije klucz; nie pisë gò w pòlécenim, chtërne òstônie w historiie terminala.

Bë jic prosto do browsera:

```sh
omi auth login --browser
```

Wlogùjë sã na tim samym kòmputerze co terminal: òdpòwiesc autentikacëji jidze do lokalnégò adresu. Sodzë za pòuczënkama na ekranie.

Pò tim sprôwdzë kònfigùracëjã i dostãp API:

```sh
omi auth status
omi auth whoami
```

`status` pòkazëje lokalny stón i krije sekret, ale nie sprôwdzô wôżnotë na serwerze. `whoami` robi autentifikòwóné żãdanié; jeżlë sã sparłãczi, je jasné, że pòtrzébné datë dzejają, bez pòkazywaniégò miona.

Kònfigùracëjô je domëslno zapisónô w `~/.omi/config.toml`. Nie dzélë tegò lopka: mòże zamëkac w se priwatné datë.

## Òbzéranié swòjich datów

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Pùstô lësta nôczãsci znôczë le to, że nick nie pasëje do szëkbë. Ùżëj pòmòcë, bë nalezc filtre kòżdégò pòléceniégò:

```sh
omi memory list --help
omi action-item list --help
```

## JSON i stronë

Pòstaw globalną òpcyjã `--json` **przed** grëpą pòléceń:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Pierszé pòlécenié żãdô pierszich 25 wspòminków; drëdżé żãdô nôstãpné 25. Jedna strona to nie fùl kòpijô. JSON zachòwëwô całowné numerë, a tabelë na ekranie mògą je skrodzëc.

Bë zapisac stronã do lopka:

```sh
omi --json memory list --limit 25 --offset 0 > wspòmink-strong-1.json
```

To przekerowanié tworzi abò nadpisëje lokalny lopk. Sparłãczë sã, że pòlécenié je skùńczoné przed ùżëcym zamkłoscë. Felë są zapisowóné do felowégò wëgónu (stderr); pùstë lopk nie je dowòdã, że nie ma datów. Ekspòrtowóny lopk mòże zamëkac priwatné wiadła: trzëmôj gò w krëjamnoce.

## Wëlogòwanié

```sh
omi auth logout
```

To pòlécenié rëmô lokalno zapisóné datë. Bë zniwòwac klucz na serwerze, ùżëj zarządzaniô developer-kluczama w swòjim kònce.

Dla wicy pòléceń i òpcyjów òbaczë [przédny przewódnik w anielsczim](../README.md) i `omi --help`.
