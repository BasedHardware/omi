# Promé pasonan ku omi-cli

E guia aki ta mustra bo e promé pasonan ku omi-cli, skirbí na Papiamentu. Nòmbernan di komandonan i mensahenan di programa ta keda na ingles. E ehèmpelnan di e guia aki no ta kambia bo memorianan, konbersashonnan, elementonan di akshon òf bo metanan.

## Instalashon

Bo mester tin Python 3.10 òf mas nobo, i un kuenta Omi.

Si `pipx` ya ta disponibel:

```sh
pipx install omi-cli
omi --help
```

Òf, bo por instal'é den un ambiente virtual di Python ku ta aktivo:

```sh
python -m pip install omi-cli
omi --help
```

Si e terminal no ta haña `omi`, kontrolá si e ambiente virtual ta aktivo òf si e karpeta di `pipx` ta den `$PATH`.

## Konectá bo kuenta

Kuminsá e asistente di login interaktivo:

```sh
omi auth login
```

Bo por skohé: drenta ku e navegadó òf plak un yabi di API di desaroyadó Omi. E entrada interaktivo ta skonde e yabi; paga tinu i no laga e den e historia di e terminal.

Pa drenta direktamente ku e navegadó:

```sh
omi auth login --browser
```

Drenta riba e mesun mákina kaminda e terminal ta kori: e respuesta di outorisashon ta usa un adrès lokal. Sigui e instrukshonnan riba e pantaya.

Awor kontrolá e konfigurashon i e yabi di API:

```sh
omi auth status
omi auth whoami
```

`status` ta mustra e estado lokal i ta skonde e sekretonan, pero no ta kontrolá ku e servidor. `whoami` ta manda un petishon outorisá; si ta bai bon, bo ta sa ku bo kredenshalnan ta funshoná, pero no ta mustra bo nòmber.

E konfigurashon ta den `~/.omi/config.toml`. No komparti e fishero aki: e por kontein sekretonan di entrada.

## Eksplorá e datonan

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Un lista bashí por nifiká simplemente ku no tin datonan ku ta korespondé. Pa siña e filternan di kada komando, wak e yudansa:

```sh
omi memory list --help
omi action-item list --help
```

## Salida JSON i paginashon

Pone e opshon global `--json` **promé** ku e grupo di komandonan:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

E promé komando ta haña e promé 25 memorianan; e di dos ta haña e 25 siguiente. Un página no ta semper yena. E salida JSON ta konserbá tur e identifikadornan, miéntras ku e tablonan riba e pantaya ta hasi nan kòrtiku.

Pa skirbi un página den un fishero:

```sh
omi --json memory list --limit 25 --offset 0 > memorianan-página-1.json
```

E redirekshon ta kreá òf sobre-eskribí un fishero lokal. Kontrolá ku e komando a funshoná promé ku bo usa e kontenido. E errornan ta bai na stderr; un fishero bashí no ta nifiká ku no tin datonan. E fishernan eksportá por kontein sekretonan: warda nan na un manera sigur.

## Sali

```sh
omi auth logout
```

E komando aki ta kitá e kredenshalnan wardá lokalmente. Pa revoká e yabi riba e servidor, usa e gesthon di yabi di desaroyadó den bo kuenta.

Pa mas komandonan i opshonnan avansá, wak e [guia prinsipal na ingles](../README.md) i `omi --help`.
