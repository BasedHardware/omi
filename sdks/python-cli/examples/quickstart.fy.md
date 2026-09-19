# Earste stappen mei omi-cli

Dizze gids beskriuwt de earste kommando's (commands) fan omi-cli yn it Frysk. De nammen fan de kommando's en de berjochten fan it programma bliuwe yn it Ingelsk. De sykfoarbylden dy't hjir te sjen binne, feroarje jo ûnthâld (memories), jo petearen (conversations), jo aksjepunten (action items) of jo doelen (goals) net.

## Ynstallaasje

Fereaske: Python 3.10 of nijer en in Omi-account.

As jo `pipx` hawwe:

```sh
pipx install omi-cli
omi --help
```

Jo kinne it ek ynstallearje yn in aktive Python-firtuele omjouwing:

```sh
python -m pip install omi-cli
omi --help
```

As de terminal `omi` net fynt, soargje der dan foar dat de firtuele omjouwing aktyf is of dat de map fan `pipx` yn `$PATH` stiet.

## Jo account ferbine

Start de ynteraktive assistint:

```sh
omi auth login
```

Kies foar oanmelde fia de browser of foar it plakken fan in Omi developer API-kaai. Ynteraktive ynfier ferberget de kaai; foarkom dat jo dy yn in kommando skriuwe dy't yn de terminalhistoarje bewarre wurdt.

Om direkt nei de browser te gean:

```sh
omi auth login --browser
```

Meld jo oan op deselde kompjûter as de terminal: it autentikaasje-antwurd giet nei it lokale adres. Folgje de ynstruksjes op it skerm.

Dêrnei kinne jo de konfiguraasje en API-tagong ferifiearje:

```sh
omi auth status
omi auth whoami
```

`status` toant de lokale steat en ferberget it geheim, mar ferifiearret de jildigens op 'e server net. `whoami` docht in autentisearre fersyk; as dat slagget, is dúdlik dat de oanmeldgegevens wurkje, sûnder jo namme te toanen.

De konfiguraasje wurdt standert bewarre yn `~/.omi/config.toml`. Diel dit bestân net: it kin fertroulike oanmeldgegevens befetsje.

## Jo gegevens ferkenne

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

In lege list betsjut faak gewoan dat neat oerienkomt mei it sykjen. Brûk de help om de filters fan elk kommando te finen:

```sh
omi memory list --help
omi action-item list --help
```

## JSON en sidearjen

Set de globale opsje `--json` **foar** de kommando-groep:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

It earste kommando freget de earste 25 oantinkens op; it twadde de folgjende 25. Ien side is net in folsleine reservekopy. De JSON-útfoer bewarret hiele getallen, wylst tabellen op it skerm se koartsje kinne.

Om in side yn in bestân te bewarjen:

```sh
omi --json memory list --limit 25 --offset 0 > oantinkens-side-1.json
```

Dizze omlieding makket in lokaal bestân oan of oerskriuwt it. Soargje derfoar dat it kommando klear is foardat jo de ynhâld brûke. Flaters wurde nei de flaterútfoer (stderr) skreaun; in leech bestân is gjin bewiis dat der gjin gegevens binne. In eksportearre bestân kin persoanlike ynformaasje befetsje: hâld it privee.

## Útlogge

```sh
omi auth logout
```

Dit kommando smyt de lokaal bewarre oanmeldgegevens fuort. Om in kaai op 'e server ûnjildich te meitsjen, brûk it behear fan developer-kaaien yn jo eigen account.

Foar mear kommando's en opsjes, sjoch de [haadgids yn it Ingelsk](../README.md) en `omi --help`.
