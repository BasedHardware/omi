# Pjyrwsze kroki z omi-cli

Ten poradnik ôpisuje pjyrwsze komendy z omi-cli po ślōnsku. Miana komendōw a komunikaty programu ôstowajōm po angelsku. Przikłady w tym poradniku niy zmieniajōm twojich spamiyntōw (memories), gōdek (conversations), pōnktōw roboty (action items) ani cōlōw (goals).

## Instalacyjo

Wymogania: Python 3.10 abo nowszy, a kōnto Omi.

Jeźli `pipx` je zainstalowany:

```sh
pipx install omi-cli
omi --help
```

Ôsobno, możesz to zainstalować we aktywnym wirtualnym ôtoczeniu Pythona:

```sh
python -m pip install omi-cli
omi --help
```

Jeźli terminal niy nojdzie `omi`, sprawdź, czy wirtualne ôtoczenie je aktywne abo czy katalog pipx je w `$PATH`.

## Podłōncz swoje kōnto

Sztartnij interaktywny kreatōr logowaniŏ:

```sh
omi auth login
```

Wybier logowanie bez przeglōndarka abo wklijajōnc klucz API dewelopera Omi. Interaktywne logowanie schrōniŏ twōj klucz; niy ôstawiej go w historyji terminala.

Aby logować sie direkt bez przeglōndarka:

```sh
omi auth login --browser
```

Loguj sie na tym samym kōmputrze, na kerym działo terminal: ôdpedź autoryzacyje używo lokalnego adresu. Podōnżōj za instrukcjami na ekranie.

Potym sprawdź kōnfiguracyjo a klucz API:

```sh
omi auth status
omi auth whoami
```

`status` pokazuje lokalny stan a schrōniŏ sekrety, ale niy sprawdzo wŏżności na serwerze. `whoami` robi żōndanie z autoryzacjōm; jeźli sie udŏ, potwiyrdzo, że twoje dane logowaniŏ działajōm, a niy pokazuje twojigo miana.

Kōnfiguracyjo je zwykle zapisano w `~/.omi/config.toml`. Niy podawaj tego pliku dalij: może zawiyrać sekrety logowaniŏ.

## Przejzdrz sie po danych

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Pusta lista może ôznaczać po prōstu, że niy ma danych pasujōncych do tego żōndaniŏ. Aby poznać dostympne filtry kożdyj komendy, łuknij w pōmoc:

```sh
omi memory list --help
omi action-item list --help
```

## Ôutput JSON a strōnicowanie

Postow globalny `--json` ôpcyjõ **przed** grupōm komend:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Pjyrwszo komenda pyto ô pjyrwsze 25 spamiyntōw; drugo ô nastympne 25. Jedna strōna niy je fōlnym backupym. Ôutput JSON zachowywŏ wszyske identyfikatory, a tabele na ekranie mogōm je skrōcać do ôglōndaniŏ.

Aby zapisać jedna strōna do pliku:

```sh
omi --json memory list --limit 25 --offset 0 > spamiynta-strōna-1.json
```

To przekerowanie tworzi abo nadpisuje lokalny plik. Przed użyciym zawartości sprawdź, czy komenda sie skōńczyła sukcesym. Felerki sōm zapisowane do stderr; pusty plik niy dowŏ gwarancyje, że danych niy ma. Eksportowane pliki mogōm zawiyrać ôsobiste dane: trzimaj je w tajemnicy.

## Wylogowanie

```sh
omi auth logout
```

Ta komenda kasuje lokalnie zapisane dane logowaniŏ. Aby cofnōńć klucz na serwerze, użyj zarzōndzaniŏ kluczōw dewelopera we swojim kōncie.

Po wiyncyj komendōw a rozszyrzōnych ôpcyji łuknij do [angelskigo głōwnego poradnika](../README.md) a `omi --help`.
