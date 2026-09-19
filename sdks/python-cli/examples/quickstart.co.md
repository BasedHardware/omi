# Principià cù omi-cli

Sta guida mostra i primi cumandi in lingua corsa. I nomi di i cumandi è i missaghji di u sistema fermanu in inglese. L'esempii di lettura furniti quì ùn mudificheranu micca e vostre memorie, cunversazione, liste d'azzioni o scopi.

## Stallà u prugramma

Requisiti: Python 3.10 o una versione più recente è un contu Omi.

> Attenti: U nome di u pacchettu nant'à PyPI hè **`omi-cli`**, mentre chì u cumandu chì viaghja dopu à a stallazione hè **`omi`**. Ci hè un altru pacchettu senza rilazione chjamatu `omi` nant'à PyPI — ùn stallate micca quellu pacchettu.

S'ellu hè stallatu `pipx`:

```sh
pipx install omi-cli
omi --help
```

In alternativa, ind'un ambiente virtuale Python attivu:

```sh
python -m pip install omi-cli
omi --help
```

S'ellu u terminale ùn trova micca `omi`, verificate chì l'ambiente virtuale sia attivu o chì u cartulare di `pipx` sia ind'u vostru `PATH`.

## Cunnettà u vostru contu

Lanciate l'assistente interattivu:

```sh
omi auth login
```

Sceglite d'identificavvi via u navigatore, o sceglite l'opzione per incollà una chjave API di sviluppatore Omi. L'entrata interattiva piatta a chjave; ùn scrivite micca a chjave in cumandi chì fermanu ind'a cronolugia di u terminale.

Per un'entrata diretta via u navigatore:

```sh
omi auth login --browser
```

Fate l'entrata nant'à u listessu urdinatore induve viaghja u terminale, perchè l'autentificazione volta à un indirizzu lucale. Seguitate l'istruzzioni nant'à u screnu.

Dopu à quessa, verificate a cunfigurazione è l'accessu à l'API:

```sh
omi auth status
omi auth whoami
```

`status` mostra u statu lucale è piatta i secreti, ma ùn li verifica micca cù u servore. `whoami` manda una dumanda autentifikata; a riescita significa chì i vostri dati d'identificazione funzionanu bè.

A cunfigurazione hè salvata per difettu ind'è `~/.omi/config.toml`. Ùn sparte micca stu schedariu perchè cuntene i vostri dati persunali.

## Vede i vostri dati

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Una lista viota pò significà solu chì ùn ci hè micca elementi chì currispondenu à a ricerca. Per capisce i filtri d'un cumandu, fighjate l'aiutu:

```sh
omi memory list --help
omi action-item list --help
```

## Uttene JSON è navigà e pagine

Pone l'opzione glubale `--json` **prima** di u gruppu di cumandi:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

U primu cumandu dumanda i primi 25 registri; u secondu dumanda i 25 seguenti. Per quessa, una pagina ùn hè micca una copia di salvezza cumpleta. U risultatu JSON mantene l'identificatori cumpleti, mentre chì e tavule ponu accurtalli.

Per salvà una pagina ind'un schedariu:

```sh
omi --json memory list --limit 25 --offset 0 > memorie-pagina-1.json
```

Sta ridirezzione crea o rimpiazza un schedariu lucale. Prima d'aduprà u cuntenutu, assicuratevi chì u cumandu hà riesciutu. L'errori sò scritti nant'à stderr; un schedariu viotu ùn hè micca prova chì ùn ci hè dati. U schedariu salvatu pò cuntene infurmazioni persunali: tenitelu sicuru.

## Scunnettassi (Log out)

```sh
omi auth logout
```

Stu cumandu caccia i dati d'identificazione salvati lucalmente. Per annullà una chjave nant'à u servore, aduprate a gestione di e chjave di sviluppatore ind'u vostru contu.

Per altri cumandi è opzioni avanzate, fighjate a guida principale in inglese:
[../README.md](../README.md) è `omi --help`.
