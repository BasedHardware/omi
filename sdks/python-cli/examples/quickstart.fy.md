# Earste stappen mei omi-cli

Dizze hantlieding leit de earste kommando's fan omi-cli út yn it Frysk. Kommandonammen en programmaberjochten bliuwe yn it Ingelsk. De foarbylden yn dizze hantlieding feroarje jo oantinkens, konversaasjes, aksje-items of doelen net.

## Ynstallaasje

Jo hawwe Python 3.10 of nijer nedich, en in Omi-akkount.

As `pipx` al ynstallearre is:

```sh
pipx install omi-cli
omi --help
```

Oars kinne jo it yn in aktive Python-firtuele omjouwing ynstallearje:

```sh
python -m pip install omi-cli
omi --help
```

As de terminal `omi` net fynt, kontrolearje dan oft de firtuele omjouwing aktyf is of oft de map fan pipx yn `$PATH` stiet.

## Ferbyn jo akkount

Start de ynteraktive oanmeldwizard:

```sh
omi auth login
```

Jo kinne kieze om mei de browser oan te melden of in Omi-ûntwikkelder-API-kaai te plakken. De ynteraktive oanmelding ferberget jo kaai; wês foarsichtich en lit it net yn jo terminalhistoarje stean.

Om direkt mei de browser oan te melden:

```sh
omi auth login --browser
```

Oanmelde op deselde kompjûter dêr't de terminal op rint: it autorisaasje-antwurd brûkt in lokaal adres. Folgje de oanwizings op it skerm.

Kontrolearje no de konfiguraasje en de API-kaai:

```sh
omi auth status
omi auth whoami
```

`status` toant de lokale steat en ferberget geheimen, mar kontrolearret net by de tsjinner. `whoami` docht in autorisearre fersyk; as it slagget, befêstiget it dat jo bemachtiging wurket, mar it toant jo namme net.

Konfiguraasje stiet yn `~/.omi/config.toml`. Diel dit bestân net: der kinne oanmeldgeheimen yn stean.

## Ferkenne fan gegevens

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

In lege list kin gewoan betsjutte dat der gjin gegevens binne dy't by de fraach passe. Om de filters fan elk kommando te learen, besjoch de help:

```sh
omi memory list --help
omi action-item list --help
```

## JSON-útfier en paginering

Set de globale `--json`-opsje **foar** de kommandogroep:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

It earste kommando freget de earste 25 oantinkens op; it twadde freget de folgjende 25. Ien side is faaks net fol. JSON-útfier behâldt alle identifikatoaren, wylst tabellen op it skerm se faak koartsje.

Om in side nei in bestân te skriuwen:

```sh
omi --json memory list --limit 25 --offset 0 > oantinkens-side-1.json
```

Redireksje makket in lokaal bestân oan of skriuwt it oer. Kontrolearje oft it kommando slagge is foardat jo de ynhâld brûke. Flaters geane nei stderr; in leech bestân betsjut net dat der gjin gegevens binne. Eksportearre bestannen kinne privee-ynformaasje befetsje: bewarje se feilich.

## Ofmelde

```sh
omi auth logout
```

Dit kommando fuortsmiet de lokale bewarre bemachtiging. Om de kaai op 'e tsjinner te annulearjen, brûk it ûntwikkelder-kaaibehear op jo akkount.

Besjoch foar oare kommando's en avansearre opsjes de [Ingelske haadhantlieding](../README.md) en `omi --help`.
