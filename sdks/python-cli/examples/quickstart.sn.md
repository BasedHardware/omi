# Kutanga Nekukurumidza ne-omi-cli

Gwaro iri rinotsanangura mirayiro yekutanga mumutauro wechiShona. Mazita emirayiro nemameseji echirongwa anoramba ari muChirungu. Mienzaniso yemibvunzo iri pano haishanduri ndangariro dzenyu (memories), nhaurirano (conversations), mabasa ekuita (action items), kana zvinangwa (goals).

## Kuisa chirongwa

Zvinodiwa: Python 3.10 kana vhezheni itsva pamwe neakaundi yeOmi.

Kana muine `pipx` yakaiswa:

```sh
pipx install omi-cli
omi --help
```

Seimwe nzira, munogona kuisa mukati me-virtual environment yePython iri kushanda:

```sh
python -m pip install omi-cli
omi --help
```

Kana terminal ikasawana `omi`, iva nechokwadi chekuti virtual environment iri kushanda kana kuti dhairekitori rinoiswa ma-executable e-`pipx` riri mu-`$PATH` yenyu.

## Kubatanidza akaundi yenyu

Tanga mubatsiri anodyidzana (interactive assistant):

```sh
omi auth login
```

Sarudza kupinda uchishandisa browser kana sarudzo yekuisa Omi developer API key. Kupinda kwemubatsiri kunovanza kiyi; dzivisa kunyora kiyi mumurayiro unozosara mune nhoroondo yeterminal.

Kuti uende wakananga kubrowser:

```sh
omi auth login --browser
```

Pinda pakombiyuta imwe chete inofamba neterminal: mhinduro yekutendesa inoshandisa kero yemuno (local address). Tevedzera mirairo iri pachiratidziro.

Mushure meizvozvo, tarisa kumisikidzwa uye kuwana API:

```sh
omi auth status
omi auth whoami
```

`status` inoratidza mamiriro emuno uye inovanza zvakavanzika, asi haitarisi chokwadi pane server. `whoami` inotumira chikumbiro chakatendeswa; kana zvikabudirira, zvinoratidza kuti zvitupa zviri kushanda pasina kuratidza zita renyu.

Kugadziriswa kunochengetwa zvakagara zvakadaro mu-`~/.omi/config.toml`. Usagovera faira iri nekuti rinogona kunge riine zvitupa zvenyu zvakavanzika.

## Kutarisa data renyu

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Rongonyorwa risina chinhu rinogona kungoreva kuti hapana zvinhu zvinoenderana nemubvunzo. Shandisa rubatsiro kuwana masefa pane yega yega murayiro:

```sh
omi memory list --help
omi action-item list --help
```

## Kutora JSON nekufamba nemapeji (Pagination)

Isa sarudzo yepasi rose `--json` **pamberi** peboka remirayiro:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Murayiro wekutanga unokumbira ndangariro dzekutanga makumi maviri neshanu; wechipiri, makumi maviri neshanu anotevera. Peji rimwe chete harisi backup yakazara. JSON inochengetedza mazita akazara ezvitupa, nepo matafura ari pachiratidziro achigona kuapfupisa kuti anake kuona.

Kuti uchengetedze peji mufaira:

```sh
omi --json memory list --limit 25 --offset 0 > ndangariro-peji-1.json
```

Kutungamira uku kunogadzira kana kutsiva faira remuno. Iva nechokwadi chekuti murayiro wapera zvakanaka usati washandisa zvirimo. Zvikanganiso zvinonyorwa mune zvakabuda zvakakanganisika (stderr); faira risina chinhu harisi vimbiso yekuti hapana data. Faira rakatumirwa rinogona kunge riine ruzivo rwemunhu pachake: richengetedze zvakachengeteka.

## Kubuda muakaundi (Logout)

```sh
omi auth logout
```

Murayiro uyu unodzima zvitupa zvakachengetwa munharaunda. Kuti udzime kiyi paseva, shandisa manejimendi ekiyi yemugadziri muakaundi yenyu.

Kuti uwane mimwe mirayiro uye sarudzo dzepamusoro, tarisa [gwaro guru reChirungu](../README.md) pamwe ne-`omi --help`.
