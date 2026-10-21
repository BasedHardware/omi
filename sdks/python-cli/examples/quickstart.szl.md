# Pjyrsze kroki z omi-cli

Ten przewodnik ôpisoje pjyrsze kōmanda (commands) ôd omi-cli we ślōnskij gŏdce. Mjany kōmand i wiadōmości programu ôstŏwajōm we angelskij gŏdce. Przikłady szukaniŏ pokŏzane sam niy zmieniajōm twojich spōmniyń (memories), rozmōw (conversations), robotōw (action items) ani cōlōw (goals).

## Instalacyjŏ

Trzeba: Python 3.10 abo nowszy, i kōnto Omi.

Jak mŏsz `pipx`:

```sh
pipx install omi-cli
omi --help
```

Mōżesz tyż zainstalować we aktywnym Python-wirtualnym ôtoczyniu:

```sh
python -m pip install omi-cli
omi --help
```

Jak terminal niy nolezie `omi`, upewnij sie, że wirtualne ôtoczynie dŏwŏ robota abo że katalog `pipx` je w `$PATH`.

## Podłōnczynie kōnta

Zacznij interaktywny asystynt:

```sh
omi auth login
```

Wybjer wlogowanie bez browser abo wklajynie klucza Omi developer API. Interaktywny przikłŏd kryje klucz; niy pisz go we kōmandzie, kery ôstanie w historyji terminala.

Coby iś prosto do browsera:

```sh
omi auth login --browser
```

Wloguj sie na tym samym kōmputrze co terminal: ôdpowiydź autyntykacyje idzie do lokalnego adresu. Idź za wskazōwkami na ekranie.

Potym sprawdź kōnfiguracyjŏ i dostymp API:

```sh
omi auth status
omi auth whoami
```

`status` pokazuje lokalny stan i kryje sekret, ale niy sprawdzŏ ważności na serwerze. `whoami` robi autyntyfikowane żōndanie; jak sie podarzi, je jasne, że potrzebne dane dŏwajōm robota, bez pokazowaniŏ miana.

Kōnfiguracyjŏ je zapisowanŏ domyślnie we `~/.omi/config.toml`. Niy dziel sie tym plikiem: może mieć prywatne dane.

## Ôglōndanie swoich danych

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Pustŏ lista nojczyńścij znaczë ino to, że nic niy pasuje do szukaniŏ. Użyj pōmocy, coby noleźć filtry kożdyj kōmandy:

```sh
omi memory list --help
omi action-item list --help
```

## JSON i strony

Połóż globalnõ ôpcyjõ `--json` **przed** grupōm kōmand:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Pjyrszŏ kōmanda żōndŏ pjyrszych 25 spōmniyń; drugŏ żōndŏ nastympne 25. Jednŏ strona to niy pełnŏ kōpijŏ. JSON zachowuje cołe numery, a tablice na ekranie mogōm je skrōcić.

Coby zapisać strona do pliku:

```sh
omi --json memory list --limit 25 --offset 0 > spōmniynie-strona-1.json
```

To przekerowanie tworzi abo nadpisuje lokalny plik. Upewnij sie, że kōmanda je skōńczōnŏ przed użyciym treści. Feler je zapisowany do felerowego wyjściŏ (stderr); pusty plik niy je dowodym, że niy ma danych. Eksportowany plik może mieć prywatne informacyje: trzymej go w tajle.

## Wylogowanie

```sh
omi auth logout
```

Ta kōmanda rymie lokalnie zapisane dane. Coby zniweczyć klucz na serwerze, użyj zarzōndzaniŏ developer-kluczami we swojim kōncie.

Po wiyncyj kōmand i ôpcyji ôbŏcz [przodni przewodnik we angelskij gŏdce](../README.md) i `omi --help`.
