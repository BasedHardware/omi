# Mehato ea pele le omi-cli

Tataiso ena e hlalosa litaelo (commands) tsa pele tsa omi-cli ka Sesotho. Mabitso a litaelo le melaetsa ea lenaneo li lula ka Senyesemane. Mehlala ea patlo e bontšitsoeng mona ha e fetole memori (memories), lipuisano (conversations), mesebetsi (action items) kapa lipakane (goals) tsa hau.

## Ho kenya

Se hlokahalang: Python 3.10 kapa ho feta, le ak'haonte ea Omi.

Haeba u na le `pipx`:

```sh
pipx install omi-cli
omi --help
```

U ka boela ua e kenya ka har'a virtual environment ea Python e sebetsang:

```sh
python -m pip install omi-cli
omi --help
```

Haeba terminal e sa fumane `omi`, netefatsa hore virtual environment e sebetsa kapa hore foldara ea `pipx` e ho `$PATH`.

## Ho hokela ak'haonte ea hau

Qala motlatsi oa puisano:

```sh
omi auth login
```

Khetha ho kena ka browser kapa ho beha Omi developer API key. Ho kenya ka puisano ho pata key; qoba ho e ngola ka litaelo tse tla bolokoa nalaneng ea terminal.

Ho ea ka kotloloho ho browser:

```sh
omi auth login --browser
```

Kena komporong e le 'ngoe le terminal: karabo ea netefatso e ea atereseng ea lehae. Latela litaelo tse skrineng.

Ka mor'a moo, netefatsa tlhophiso le phihlello ea API:

```sh
omi auth status
omi auth whoami
```

`status` e bontša boemo ba lehae 'me e pata sephiri, empa ha e netefatse ho nepahala ho server. `whoami` e etsa kopo e netefalitsoeng; haeba e atleha, ho hlakile hore lintlha tsa ho kena lia sebetsa, ntle le ho bontša lebitso la hau.

Tlhophiso e bolokoa ka mokhoa o tloaelehileng ho `~/.omi/config.toml`. Se arolelane faele ena: e ka ba le lintlha tsa lekunutu.

## Ho hlahloba data ea hau

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Lenane le se nang letho hangata le bolela feela hore ha ho letho le lumellanang le patlo. Sebelisa thuso ho fumana li-filter tsa taelo e 'ngoe le e 'ngoe:

```sh
omi memory list --help
omi action-item list --help
```

## JSON le maqephe

Beha khetho ea lefats'e `--json` **pele** ho sehlopha sa litaelo:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Taelo ea pele e kopa memori tse 25 tsa pele; ea bobeli e kopa tse 25 tse latelang. Leqephe le le leng ha se kopi e felletseng. Phetiso ea JSON e boloka linomoro tse felletseng, ha litafole tse skrineng li ka li khutsufatsa.

Ho boloka leqephe faeleng:

```sh
omi --json memory list --limit 25 --offset 0 > memori-leqephe-1.json
```

Phetisetso ena e theha kapa e ngola hape faele ea lehae. Netefatsa hore taelo e felile pele u sebelisa litaba tsa eona. Liphoqo li ngoloa ho phetiso ea liphoqo (stderr); faele e se nang letho ha se bopaki ba hore ha ho data. Faele e rometsoeng e ka ba le tlhahisoleseding ea botho: e boloke e le lekunutu.

## Ho tsoa

```sh
omi auth logout
```

Taelo ena e hlakola lintlha tsa ho kena tse bolokiloeng sebakeng sa heno. Ho etsa hore key e se ke ea sebetsa ho server, sebelisa tsamaiso ea developer key ak'haonteng ea hau.

Bakeng sa litaelo le likhetho tse ling, sheba [tataiso e kholo ka Senyesemane](../README.md) le `omi --help`.
