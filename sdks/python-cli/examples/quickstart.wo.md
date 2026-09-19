# Tambali ci Gaaw ak omi-cli

Téere biy tegtal dafay leeral ndigal yi njëkk ci lamiñu Wolof. Turi ndigal yi ak bataaxal yi bawoo ci tëriin bi dañuy des ci làkku Tubab (Anglais). Misaali laaj (query) yi nu fi wone dunu soppi say fàttaliku (memories), say waxtaan (conversations), say jëf yees wara def (action items), mbaa say yitte (goals).

## Samp tëriin bi (Installation)

Laaj yi: Python 3.10 mbaa sumb bu gën a yees ak sàqum Omi.

Su fekkee danga sampoon `pipx`:

```sh
pipx install omi-cli
omi --help
```

Ci geneen anam, mën nga ko samp ci biir ab barabu liggeeyu Python (virtual environment) buy dox:

```sh
python -m pip install omi-cli
omi --help
```

Su fekkee terminal bi gisul `omi`, wóorlu te xool ndax virtual environment bi mi ngi dox mbaa wayndareem (directory) bi `pipx` di tëral xibaar yi am na ci sa `$PATH`.

## Lëkkale sa sàqu (Authentication)

Tambalil ndimbal li lay seet (interactive assistant):

```sh
omi auth login
```

Tànnal dugge ci joowkat bi (browser) mbaa nga yeb caabi API bu tabaxkatu Omi. Doxaliin wii dafay làqu caabi bi; buñu bind caabi bi ci ndigal biy des ci jaari-jaari terminal bi.

Ngir jëm teey ci joowkat bi:

```sh
omi auth login --browser
```

Duggal ci ordinaatëer bi nga xam ne fa la terminal bi di doxe: tontu dëggal bi dafay jëfandikoo màkkaan bu gox bi (local address). Toppal tegtal yi nekk ci seetukaay bi (screen).

Gannaaw loolu, wóorlul tëralin wi ak jëm ci API bi:

```sh
omi auth status
omi auth whoami
```

`status` mi ngi wone nekkiinu gox bi te làq mbóot yi, waaye du saytu dëggu gi ci serwëer bi. `whoami` dafay yónnee ab laaj buñu dëggal; bu jàllee, dafay wone ne lëkkale yi ñu ngi dox bu baax te laajul nga wone sa tur.

Tëralin wi mi ngi dencu ci `~/.omi/config.toml`. Bul séddoo dencukaay (file) bii ndax mën na ëmb ay lëkkale yu sutura.

## Saytu say xibaar (Data)

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Lim bu amul dara mën na firi rek ne amul dara luy mengóo ak laaj bi. Jëfandikool ndimbal ngir gis xàjjatleen (filters) yi ci ndigal gu nekk:

```sh
omi memory list --help
omi action-item list --help
```

## Jël JSON ak dox ci xët yi (Pagination)

Tëralal tannal gu mboole mi `--json` **bala** mbooloom ndigal yi:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Ndigal gu njëkk gi dafay laaj 25 fàttaliku yi njëkk; gu ñaareel gi, 25 yiy topp. Benn xët du ndencukaay bu mat sëkk (backup). Njiitu JSON dafay denc turu màndarga yépp, waaye xibaari seetukaay bi mën nañu leen gàttal ngir gën a rafet ci gis-gis.

Ngir denc ab xët ci dencukaay:

```sh
omi --json memory list --limit 25 --offset 0 > fattaliku-xet-1.json
```

Soppite lii dafay sàkk mbaa di wuutal dencukaay bu gox bi. Wóorlul ne ndigal li sotti na bu baax bala nga koy jëfandikoo. Njuumte yi dañuy bindeeku ci bànqaasu njuumte (stderr); dencukaay bu amul dara du firnde ne amul xibaar. Dencukaay bi ñu génne mën na ëmb xibaaru bopp: denc ko ci sutura.

## Génn ci sàqu mi (Logout)

```sh
omi auth logout
```

Ndigal lii dafay dindi lëkkale yi dencu ci gox bi. Ngir neenal caabi ci serwëer bi, jëfandikool saytukatub caabi tabaxkat yi nekk ci sa sàqu.

Ngir yeneen ndigal ak tannal yu gën a xóot, seetall [tegtal gu mag ci làkku Anglais](../README.md) ak `omi --help`.
