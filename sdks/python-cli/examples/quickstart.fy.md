# Begjinne mei omi-cli

Dizze gids lit de earste pear kommando's yn it Frysk sjen. Kommandonoarnmen en systeemberjochten bliuwe yn it Ingelsk. De lêsfoarbylden hjir feroarje jo oantinkens, petearen, aksjelisten of doelen net.

## It programma ynstallearje

Easken: Python 3.10 of nijer en in Omi-akkount.

> Let op: De pakketnamme op PyPI is **`omi-cli`**, wylst it kommando dat nei ynstallaasje rint **`omi`** is. Der is in oar ûnbesibbe pakket mei de namme `omi` op PyPI — ynstallearje dat pakket net.

As `pipx` ynstallearre is:

```sh
pipx install omi-cli
omi --help
```

As alternatyf, yn in aktive firtuele Python-omjouwing:

```sh
python -m pip install omi-cli
omi --help
```

As de terminal `omi` net fine kin, kontrolearje dan oft de firtuele omjouwing aktyf is of de `pipx`-map yn jo `PATH` stiet.

## Jo akkount ferbine

Start de ynteraktive assistint:

```sh
omi auth login
```

Kies om yn te loggjen fia de browser, of kies de opsje om in Omi-ûntwikkelder-API-kaai te plakken. De ynteraktive ynfier ferberget de kaai; typ de kaai net yn kommando's dy't yn de terminalskiednis bliuwe.

Foar direkte ynloggen fia de browser:

```sh
omi auth login --browser
```

Foltôgje it ynloggjen op deselde kompjûter dêr't de terminal op draait, om't de ferifikaasje weromkomt nei in lokaal adres. Folgje de ynstruksjes op it skerm.

Kontrolearje dêrnei de konfiguraasje en de API-tagong:

```sh
omi auth status
omi auth whoami
```

`status` toant de lokale tastân en ferberget geheimen, mar ferifiearret net mei de tsjinner. `whoami` stjoert in autorisearre fersyk; sukses betsjut dat jo bewiisbrieven goed wurkje.

De konfiguraasje wurdt standert bewarre yn `~/.omi/config.toml`. Diel dit bestân net, om't it jo priveegegevens befettet.

## Jo gegevens besjen

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

In lege list kin gewoan betsjutte dat der gjin items oerienkomme mei de fraach. Om de filters fan in kommando te begripen, sjoch de help:

```sh
omi memory list --help
omi action-item list --help
```

## JSON ûntfange en troch siden blêdzje

Plaats de globale opsje `--json` **foar** de kommandogroep:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

It earste kommando freget de earste 25 records op; it twadde freget de folgjende 25 op. Dêrom is ien side gjin folsleine reservekopy. De JSON-útfier behâldt folsleine identifiers, wylst tabellen se ynkoarte kinne.

Om in side yn in bestân op te slaan:

```sh
omi --json memory list --limit 25 --offset 0 > oantinkens-side-1.json
```

Dizze trochferwizing makket of ferfangt in lokaal bestân. Soargje derfoar dat it kommando slagge is foardat jo de ynhâld brûke. Flaterberjochten wurde skreaun nei stderr; in leech bestân is gjin bewiis dat der gjin gegevens binne. Hâld dit bestân feilich, om't it persoanlike ynformaasje befetsje kin.

## Utlogge (Log out)

```sh
omi auth logout
```

Dit kommando ferwideret lokaal bewarre bewiisbrieven. Om in kaai op de tsjinner yn te lûken, brûk it ûntwikkelder-kaaibehear yn jo akkount.

Foar oare kommando's en mear opsjes, sjoch asjebleaft de haadgids yn it Ingelsk:
[../README.md](../README.md) en `omi --help`.
