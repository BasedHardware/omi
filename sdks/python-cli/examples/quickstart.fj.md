# Na istepu taumada kei omi-cli

E vakaraitaka na ivolaqatiqati qo na istepu taumada (commands) ni omi-cli ena vosa vakaViti. Na yaca ni veiqaravi kei na itukutuku ni porokaramu era tiko ena vosa vakavalagi. Na ivakaraitaki ni vaqaqa e vakaraitaki eke ena sega ni veisautaki na nomu nanuma (memories), na nomu veivosaki (conversations), na nomu itavi (action items) se na nomu inaki (goals).

## Vakadidike

Na ka e gadrevi: Python 3.10 se e dua na ka vou, kei na dua na akaude Omi.

Kevaka e tiko na `pipx`:

```sh
pipx install omi-cli
omi --help
```

E rawa talega ni vakadidike ena dua na virtual environment ni Python:

```sh
python -m pip install omi-cli
omi --help
```

Kevaka e sega ni kune na terminal na `omi`, vakadeitaka ni sa cakacaka na virtual environment se ni tiko na `pipx` ena `$PATH`.

## Veisemati ki na nomu akaude

Tekivu na veivuke:

```sh
omi auth login
```

Digia mo curu ena browser se mo vakaduria na Omi developer API key. Na ivakaraitaki ni curu e vunitaka na key; kakua ni vola na key ena dua na veiqaravi ena maroroi ena terminal history.

Me laki sara ki na browser:

```sh
omi auth login --browser
```

Curu ena kompiuta vata kei na terminal: na isau ni autentikesen e laki ki na local address. Muria na ivakasala ena sikirini.

Oti qori, vakadeitaka na konfiguresen kei na API access:

```sh
omi auth status
omi auth whoami
```

`status` e vakaraitaka na ituvaki ni vanua ka vunitaka na ka vuni, ia e sega ni vakadeitaka na kena yaga ena server. `whoami` e cakava na kerekere vakadeitaki; kevaka e yaco vinaka, e matata ni cakacaka na kredensiel, ka sega ni vakaraitaki na yacamuni.

Na konfiguresen e maroroi ena `~/.omi/config.toml`. Kakua ni wasea na faili qo: e rawa ni tiko kina na kredensiel vuni.

## Raica na nomu itukutuku

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Na lisi lala e kena ibalebale ga ni sega na ka e veisemati kei na vaqaqa. Vakayagataka na veivuke me kune na filters ni veiqaravi yadua:

```sh
omi memory list --help
omi action-item list --help
```

## JSON kei na tabana

Vakatikora na digidigi raraba `--json` **eliu** ni tabana ni veiqaravi:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Na imatai ni veiqaravi e kerea na imatai ni 25 na nanuma; na ikarua e kerea na 25 e tarava. E dua na tabana e sega ni dua na ikopi taucoko. Na JSON e maroroya na naba taucoko, ia na teveli ena sikirini e rawa ni vakalekalekataka.

Me maroroi e dua na tabana ena dua na faili:

```sh
omi --json memory list --limit 25 --offset 0 > nanuma-tabana-1.json
```

E bulia se volai tale na faili qo na vanua. Vakadeitaka ni sa oti na veiqaravi eliu ni vakayagataki na kena lewena. Na cala e volai ki na cala ni kaukauwa (stderr); na faili lala e sega ni ivakadinadina ni sega na itukutuku. Na faili e kau ki tautuba e rawa ni tiko kina na itukutuku vakatamata: maroroya vuni.

## Kurekure

```sh
omi auth logout
```

Na veiqaravi qo e bokoca na kredensiel e maroroi ena vanua. Me vakayagataki na key ena server, vakayagataka na lewai ni developer key ena nomu akaude.

Me baleta na veiqaravi kei na digidigi tale e so, raica na [ivola levu ena vosa vakavalagi](../README.md) kei na `omi --help`.
