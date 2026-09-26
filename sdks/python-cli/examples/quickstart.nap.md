# 'E primme passe cu omi-cli

'Sta guida spiega 'e primme cummanne (commands) 'e omi-cli nnapulitano. 'E nomme d''e cummanne e 'e mmasciate d''o prugramma rummanene 'n ngrese. 'E esempie 'e recerca ca se vedono ccà nun cagnano 'e memorie (memories), 'e cunversaziune (conversations), 'e ccose 'a fà (action items) o 'e mire (goals) tuje.

## Nstallazzione

Te serve: Python 3.10 o cchiù nuovo, e nu cunto Omi.

Si tiene `pipx`:

```sh
pipx install omi-cli
omi --help
```

'U puo pure nstallà dint'a n'ambiente virtuale Python attivo:

```sh
python -m pip install omi-cli
omi --help
```

Si 'o terminale nun trova `omi`, sicurte ca l'ambiente virtuale è attivo o ca 'a cartella 'e `pipx` sta dint'ô `$PATH`.

## Cullegà 'o cunto tujo

Accumincia l'assistente interattivo:

```sh
omi auth login
```

Scieglie 'e trasere cu 'o browser o 'e 'ncullà na chiave API 'e sviluppatore Omi. L'input interattivo ammuccia 'a chiave; evita 'e scriverla dint'a na cummanna ca rummane dint'a storia d''o terminale.

Pe' jì dritto ô browser:

```sh
omi auth login --browser
```

Trase ncopp'ô stesso computer d''o terminale: 'a risposta 'e autenticazzione va a ll'indirizzo locale. Sèquita 'e struziune ncopp'â schermata.

Appriesso, verifica 'a cunfigurazzione e ll'accesso API:

```sh
omi auth status
omi auth whoami
```

`status` mmustra 'o stato locale e ammuccia 'o segreto, ma nun verifica 'a validità ncopp'ô server. `whoami` fa na dumanna autenticata; si riesce, è chiaro ca 'e credenziale faticano, senza ammustà 'o nomme tujo.

'A cunfigurazzione se sarva 'e default dint'a `~/.omi/config.toml`. Nun spartì stu file: pò tenè credenziale private.

## Esplorà 'e date tuje

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Na lista vacante spisso vò dicere sulamente ca niente currisponne â recerca. Ausa ll'aiuto pe' truvà 'e filtre 'e ogne cummanna:

```sh
omi memory list --help
omi action-item list --help
```

## JSON e paggene

Miette ll'opzione globbale `--json` **primma** d''o gruppo 'e cummanne:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

'A primma cummanna addimanna 'e primme 25 memorie; 'a seconna 'e 25 appriesso. Na paggena sola nun è na copia cumpleta. Ll'output JSON conserva 'e nummere sane, mentre 'e tavele ncopp'â schermata 'e ponno accurtà.

Pe' sarvà na paggena dint'a nu file:

```sh
omi --json memory list --limit 25 --offset 0 > memorie-paggena-1.json
```

Sta ridirezzione cria o sorascrive nu file locale. Sicurte ca 'a cummanna è fernuta primma 'e ausà 'o cuntenuto. Ll'errure se scrivono ncopp'â l'output 'e errure (stderr); nu file vacante nun è na prova ca nun ce stanno date. Nu file esportato pò tenè nfurmaziune perzunale: tienilo privato.

## Ascì

```sh
omi auth logout
```

Sta cummanna cancella 'e credenziale sarvate locale. Pe' 'nvalidà na chiave ncopp'ô server, ausa 'a gestione d''e chiave 'e sviluppatore dint'ô cunto tujo.

Pe' cchiù cummanne e opziune, vide 'a [guida prencepale 'n ngrese](../README.md) e `omi --help`.
