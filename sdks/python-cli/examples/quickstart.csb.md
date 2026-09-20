# Pierszé kroczi z omi-cli

Ten przewòdnik òpisëje pierszé rozkôzë z omi-cli w kaszëbsczim jãzëkù. Miona rozkôzów i kòmunikatë programë òstôwają w anielsczim jãzëkù. Przëmiarë w tim przewòdnikù nie zmieniają twòjich wspòminków (memories), rozgadënków (conversations), elementów dzejaniô (action items) ani célów (goals).

## Instalacëjô

Wëmôgania: Python 3.10 abò nowszi ë kònto Omi.

Jeżlë `pipx` je zainstalowóny:

```sh
pipx install omi-cli
omi --help
```

Alternatiwno, mòżesz to zainstalowac w aktiwnym wirtualnym òtoczeniu Pythona:

```sh
python -m pip install omi-cli
omi --help
```

Jeżlë terminal nie nalezô `omi`, sprôwdzë, czë wirtualné òtoczenié je aktiwné abò czë katalog pipx je w `$PATH`.

## Pòłączë swòje kònto

Zrëszë interaktiwnégò asystenta logòwaniô:

```sh
omi auth login
```

Wëbierz logòwanié przez przezérnik abò wlépienié API-klucza rozwijarza Omi. Interaktiwné logòwanié zatôjô twój klucz; nie òstôwiôj gò w historië terminala.

Aby logòwac sã bezpòstrzédno przez przezérnik:

```sh
omi auth login --browser
```

Logùjë sã na tim samym kòmpùtrze, na chtërnym dzejo terminal: òdpòwiesc autoryzacëji ùżiwô lokalnégò adresu. Pòstãpùj wedle pòùczków na ekranie.

Pòtim sprôwdzë kònfigùracëjã ë API-klucz:

```sh
omi auth status
omi auth whoami
```

`status` pòkôzëje lokalny stan ë zatôjô sekretë, ale nie sprôwdzô wôżnotë na serwerze. `whoami` wëkònëje òdpëtanié z pòùwierzëczenim; jeżlë sã to darzi, pòtwierdzô, że twòje pòùwierzëczenia dzejają, nie pòkôzëjąc twòjégò miona.

Kònfigùracëjô je zwëczajno zapisónô w `~/.omi/config.toml`. Nie pòdôwaj tegò lopka dali: mòże zamëkac w se sekretë logòwaniô.

## Òbzéranié pòdôwków

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Pùstô lësta mòże znacziwò blós to, że nie ma pòdôwków pasëjącëch do tegò òdpëtaniô. Aby pòznac przëstãpné filtry kòżdégò rozkôzu, wezdrzë w pòmòc:

```sh
omi memory list --help
omi action-item list --help
```

## Wëdôwk JSON ë stronicowanié

Pòstôw globalny `--json` òpcëjã **przed** grëpã rozkôzów:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Pierszi rozkôz pëtô ò pierszëch 25 wspòminków; drëdżi ò nôslédné 25. Jednô strona nie je fùlnym zapisã. Wëdôwk JSON zatrzëmëje wszëtczé identifikatorë, a tabele na ekranie mògą je skrodzëc dlô òbzéraniô.

Aby zapisac jednã stronã do lopka:

```sh
omi --json memory list --limit 25 --offset 0 > wspòmink-strona-1.json
```

To przeczerowanié stwôrzô abò nadpisëje lokalny lopf. Przed ùżëcém zamkłoscë sprôwdzë, czë rozkôz sã skùńczëł pòwòdzënim. Felë są zapisëwóné do stderr; pùstï lopf nie dôwô gwarancëji, że pòdôwków nie ma. Eksportowóné lopczi mògą zamëkac w se osoblëwé pòdôwczi: trzëmôj je w krëjamnoscë.

## Wëlogòwanié

```sh
omi auth logout
```

Ten rozkôz wëmazëje lokalno zatrzëmóné pòùwierzëczenia. Aby òdwòłac klucz na serwerze, ùżëj administracëji klucza rozwijarza w swòjim kònce.

Pò wiãcy rozkôzów ë rozszérzonëch òpcëjów zajrzë do [anielsczégò głównegò przewòdnika](../README.md) ë `omi --help`.
