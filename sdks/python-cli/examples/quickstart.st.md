# Mehato ea pele le omi-cli

Tataiso ena e bontša mehato ea pele le omi-cli ka Sesotho. Mabitso a litaelo le melaetsa ea lenaneo li lula ka Senyesemane. Mehlala ea tataiso ena ha e fetole lihopololelo tsa hau, lipuisano, lintho tsa liketso kapa lipheo tsa hau.

## Ho kenya

U hloka Python 3.10 kapa e ncha, le akhaonto ea Omi.

Haeba `pipx` e se e kenoe:

```sh
pipx install omi-cli
omi --help
```

Ho seng joalo, e kenye tikolohong ea Python e sebetsang:

```sh
python -m pip install omi-cli
omi --help
```

Haeba terminal e sa fumane `omi`, hlahloba hore na tikoloho e sebetsa kapa foldara ea pipx e ho `$PATH`.

## Ho hokela akhaonto ea hau

Qala motataisi oa ho kena:

```sh
omi auth login
```

U ka khetha ho kena ka sebatli kapa ho beha senotlolo sa API sa moqapi oa Omi. Ho kena ho pata senotlolo sa hau; hlokomela hore u se ke ua e siea nalaneng ea terminal.

Ho kena ka kotloloho ka sebatli:

```sh
omi auth login --browser
```

Kena khomphuteng e le 'ngoe le terminal: karabo ea tumello e sebelisa aterese ea lehae. Latela litaelo tse holim'a skrine.

Hlahloba joale tlhophiso le senotlolo sa API:

```sh
omi auth status
omi auth whoami
```

`status` e bontša boemo ba lehae le ho pata liphiri, empa ha e hlahlobe le seva. `whoami` e etsa kopo e lumelletsoeng; haeba e atleha, e tiisa hore tumello ea hau ea sebetsa, empa ha e bontše lebitso la hau.

Tlhophiso e ho `~/.omi/config.toml`. U se ke ua arolelana faele ena: e ka ba le liphiri tsa ho kena.

## Ho hlahloba data

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Lenane le se nang letho le ka 'na la bolela feela hore ha ho data e lumellanang le potso. Ho ithuta li-filter tsa taelo ka 'ngoe, sheba thuso:

```sh
omi memory list --help
omi action-item list --help
```

## Sephetho sa JSON le maqephe

Beha khetho ea lefats'e `--json` **pele** ho sehlopha sa litaelo:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Taelo ea pele e nka lihopololelo tse 25 tsa pele; ea bobeli e nka tse 25 tse latelang. Leqephe le le leng hangata ha le tletse. Sephetho sa JSON se boloka likhetho tsohle, ha litafole tsa skrine hangata li li khutsufatsa.

Ho ngola leqephe faeleng:

```sh
omi --json memory list --limit 25 --offset 0 > lihopololelo-leqephe-1.json
```

Ho fetisetsa ho etsa kapa ho ngola faele ea lehae. Hlahloba hore taelo e atlehile pele u sebelisa litaba. Liphoso li ea stderr; faele e se nang letho ha e bolele hore ha ho data. Lifaele tse rometsoeng li ka ba le tlhahisoleseling ea lekunutu: li boloke hantle.

## Ho tsoa

```sh
omi auth logout
```

Taelo ena e tlosa tumello e bolokiloeng ea lehae. Ho hlakola senotlolo ho seva, sebelisa tsamaiso ea linotlolo tsa moqapi ho akhaonto ea hau.

Bakeng sa litaelo tse ling le likhetho tse tsoetseng pele, sheba [Tataiso e kholo ea Senyesemane](../README.md) le `omi --help`.
