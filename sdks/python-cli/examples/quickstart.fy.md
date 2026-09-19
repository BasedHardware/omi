# Earste stappen mei omi-cli

Dizze hânlieding jout útlis oer de earste kommando's yn it Frysk. Kommandonammen en
berjochten fan it programma bliuwe yn it Ingelsk. De foarbyldfragen hjir feroarje dyn
oantinkens, petearen, taken of doelen net.

## Ynstallaasje fan it programma

Betingsten: Python 3.10 of nijer en in Omi-akkount.

Ast `pipx` ynstallearre hast:

```sh
pipx install omi-cli
omi --help
```

It kin ek ynstallearre wurde yn in aktive firtuele omjouwing (virtual environment)
yn Python:

```sh
python -m pip install omi-cli
omi --help
```

As de terminal `omi` net fine kin, kontrolearje dan oft de firtuele omjouwing aktyf
is of dat de map wêryn `pipx` útfierbere triemen pleatst yn dyn `PATH`-fariabele stiet.

## Ferbyn dyn akkount

Start de ynteraktive assistint:

```sh
omi auth login
```

Kies om yn te loggen fia de browser of plak in Omi-ûntwikkeler API-kaai.
De ynteraktive ynfier ferberget de kaai; foarkom datst him yn in kommando typst dat
yn de skiednis fan de terminal efterbliuwt.

Om direkt nei de browser te gean:

```sh
omi auth login --browser
```

Loch yn op deselde kompjûter as dêr't de terminal op draait: it ferifikaasje-antwurd
brûkt in lokaal adres. Folgje de ynstruksjes op it skerm.

Kontrolearje dêrnei de ynstelling en tagong ta de API:

```sh
omi auth status
omi auth whoami
```

`status` toant de lokale status en ferberget it geheim, mar kontrolearret de jildigens
op de tsjinner net. `whoami` stjoert in autorisearre fersyk; as dat slagget, befêstiget
it dat de bewiisbrieven wurkje, sûnder needsaaklik dyn namme te toanen.

De konfiguraasje wurdt standert bewarre yn `~/.omi/config.toml`. Diel dizze triem
net: hy kin dyn geheime tagongsgegevens befetsje.

## Ferken dyn gegevens

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

In lege list kin gewoanwei betsjutte dat der gjin items oerienkomme mei de fraach.
Brûk de helpfunksje om filters foar elk kommando te sjen:

```sh
omi memory list --help
omi action-item list --help
```

## JSON ophelje en troch siden blêdzje

Set de globale opsje `--json` **foar** de kommandogroep:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

It earste kommando freget om de earste 25 oantinkens; it twadde om de folgjende 25.
Ien side is dus gjin folsleine reservekopy (backup). De JSON-útfier behâldt folsleine
ID's, wylst tabellen op it skerm se kinne ynkoartsje foar werjefte.

Om in side yn in triem op te slaan:

```sh
omi --json memory list --limit 25 --offset 0 > oantinkens-side-1.json
```

Dizze omlieding makket de lokale triem oan of oerskriuwt him. Soargje derfoar dat
it kommando sûnder flaters klear is foardatst de ynhâld brûkst. Flaters wurde skreaun
nei flaterútfier (stderr); in lege triem garandearret net dat der gjin gegevens binne.
De eksportearre triem kin persoanlike ynformaasje befetsje: hâld him privee.

## Útlogge (Logout)

```sh
omi auth logout
```

Dit kommando wisket de lokaal bewarre bewiisbrieven. Om in kaai op de tsjinner yn te
lûken, brûk it behear fan ûntwikkelerkaaien op dyn akkount.

Foar oare kommando's en mear opsjes, sjoch
[de haadhânlieding yn it Ingelsk](../README.md) en `omi --help`.
