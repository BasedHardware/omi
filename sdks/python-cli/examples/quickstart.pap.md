# Promé pasonan cu omi-cli

E guia aki ta spiega e promé komandonan (commands) di omi-cli na papiamentu. E nòmbernan di e komandonan i e mensahenan di e programa ta keda na ingles. E ehèmpelnan di buskamentu ku ta mustra aki no ta kambia bo memorianan (memories), bo konbersashonnan (conversations), bo kosnan pa hasi (action items) òf bo metanan (goals).

## Instalashon

Mester: Python 3.10 òf mas nobo, i un kuenta Omi.

Si bo tin `pipx`:

```sh
pipx install omi-cli
omi --help
```

Bo por tambe instal'é den un ambiente virtual di Python ku ta aktivo:

```sh
python -m pip install omi-cli
omi --help
```

Si e terminal no haña `omi`, sigurá bo ku e ambiente virtual ta aktivo òf ku e fòlder di `pipx` ta den `$PATH`.

## Conectá bo kuenta

Kuminsá e asistente interaktivo:

```sh
omi auth login
```

Skohe pa drenta via e browser òf pa pega un yabi di API di desaroyadó Omi. E entrada interaktivo ta sconde e yabi; evitá di skirbié den un komando ku ta keda den e historia di e terminal.

Pa bai direkto na e browser:

```sh
omi auth login --browser
```

Drenta riba e mesun komputer ku e terminal: e kontesta di autentikashon ta bai na e adrès lokal. Sigui e instrukshonnan riba e pantaya.

Despues, verifiká e konfigurashon i e akseso API:

```sh
omi auth status
omi auth whoami
```

`status` ta mustra e estado lokal i ta sconde e sekreto, pero no ta verifiká e validat riba e server. `whoami` ta hasi un petishon autentiká; si ta logra, ta kla ku e kredensialnan ta funshoná, sin mustra bo nòmber.

E konfigurashon ta wòrdu wardá pa default den `~/.omi/config.toml`. No kompartí e fail aki: por tin kredensialnan privá.

## Explora bo datonan

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Un lista bashíu normalmente ta nifiká ku no tin nada ku ta korespondé ku e buskamentu. Usa e yudansa pa haña e filternan di kada komando:

```sh
omi memory list --help
omi action-item list --help
```

## JSON i páginanan

Pone e opshon global `--json` **promé** ku e grupo di komandonan:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

E promé komando ta pidi e promé 25 memorianan; e di dos e 25 siguiente. Un página so no ta un kopia kompletu. E JSON ta konservá e nòmbernan enteru, mientras e tablanan riba e pantaya por akortá nan.

Pa warda un página den un fail:

```sh
omi --json memory list --limit 25 --offset 0 > memoria-página-1.json
```

E redirekshon aki ta krea òf ta skirbi riba un fail lokal. Sigurá ku e komando a kaba promé ku bo usa e kontenido. E errornan ta wòrdu skirbí na e salida di error (stderr); un fail bashíu no ta un prueba ku no tin data. Un fail eksportá por tin informashon personal: ward'é privá.

## Sali

```sh
omi auth logout
```

E komando aki ta borra e kredensialnan wardá lokalmente. Pa invalidá un yabi riba e server, usa e maneho di yabi di desaroyadó den bo mes kuenta.

Pa mas komando i opshonnan, mira e [guia prinsipal na ingles](../README.md) i `omi --help`.
