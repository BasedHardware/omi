# Nai Matai ni iLakolako kei na omi-cli

Na ivola oqo e vukei iko mo tekivu vakayagataka na omi-cli, volai ena vosa vakaViti. Na yaca ni veiqaravi kei na veika e vakaraitaka na porokaramu era tiko ga ena vosa vakavalagi. Na ivakaraitaki ena ivola oqo e sega ni veisautaka na nomu veiika ni nanuma, veivosaki, veiqaravi se inaki.

## Na iVakadei

E gadrevi vei iko na Python 3.10 se na kena e cake, kei na dua na akaude ni Omi.

Kevaka sa tiko oti na `pipx`:

```sh
pipx install omi-cli
omi --help
```

Se, e rawa ni o vakadeia ena loma ni dua na tabanakau ni Python (virtual environment) e cakacaka:

```sh
python -m pip install omi-cli
omi --help
```

Kevaka e sega ni kunea na terminal na `omi`, taroga se e cakacaka na tabanakau se se tiko na vanua ni `pipx` ena `$PATH`.

## Na iCurucuru ki na nomu akaude

Tekivu na veiqaravi ni icurucuru:

```sh
omi auth login
```

E rawa ni o digitaka: curu mai ena barausa se piri e dua na kii ni API mai vei na dauveiqaravi ni Omi. Na icurucuru e vuni na kii; qarauna mo kua ni biuta ena itukutuku ni terminal.

Me curu sara ga mai ena barausa:

```sh
omi auth login --browser
```

Curuma mai na loma ni same machine kei na terminal: na isau ni veivakadonui e vakayagataka e dua na itikotiko. Muria na ivakavuvuli ena ile.

Taroga na iVakadidike kei na kii ni API:

```sh
omi auth status
omi auth whoami
```

`status` e vakaraitaka na ituvaki ni vanua ka vunia na vunitaki, ia e sega ni taroga na tavaya. `whoami` e tala e dua na kere vakadonui; kevaka e vinaka, o na kila ni nomu italitali e cakacaka, ia e sega ni vakaraitaka na yacamuni.

Na iVakadidike e tiko ena `~/.omi/config.toml`. Kua ni wasea na faili oqo: e rawa ni tiko kina na vunitaki ni icurucuru.

## Na iVakadidike ni itukutuku

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

E dua na lisi lekaleka e rawa ni kena ibalebale walega ni sega na itukutuku e tautauvata. Me o vulica na filters ni veiqaravi yadua, raica na veivuke:

```sh
omi memory list --help
omi action-item list --help
```

## Na kena vakaraitaki ena JSON kei na veivola

Vakadeitaka na ivakarau raraba `--json` **imuri ni** na iwasewase ni veiqaravi:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Na imatai ni veiqaravi e taura na 25 ni veiika ni nanuma; na kena e tarava e taura na 25 e tarava. E dua na tabana e sega ni sinai vakakina. Na vakaraitaki ni JSON e taura kece na id, ia na teveli ena ile e vakalekalekataka.

Me vola e dua na tabana ki na dua na faili:

```sh
omi --json memory list --limit 25 --offset 0 > veiika-ni-nanuma-tabana-1.json
```

Na kena vakayagataki na redirect e bulia se vola tale e dua na faili. Taroga se sa cakacaka vinaka na veiqaravi ni bera ni o vakayagataka na kena kau. Na cala era lako ki stderr; e dua na faili lekaleka e sega ni kena ibalebale ni sega na itukutuku. Na faili e kau ki tautuba e rawa ni tiko kina na vunitaki: maroroi ira vakadeitaki.

## Na kena curu yani

```sh
omi auth logout
```

Na veiqaravi oqo e kauta laivi na italitali e maroroi ena vanua. Me bokoca na kii mai na tavaya, vakayagataka na veiqaravi ni kii ni dauveiqaravi ena nomu akaude.

Me raica na [ivola levu ena vosa vakavalagi](../README.md) kei na `omi --help`.
