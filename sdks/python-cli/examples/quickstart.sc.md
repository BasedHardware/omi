# Is primos passos cun omi-cli

Custa ghia ispiegat is primos cumandos (commands) de omi-cli in sardu. Is nòminis de is cumandos e is messàgios de su programa abarrant in inglesu. Is esempros de chirca mustrados inoghe no cambiant is memòrias (memories), is conversatziones (conversations), is ainas (action items) nen is obiettivos (goals) tuos.

## Installatzioni

Bisongiu: Python 3.10 o prus reghente, e unu contu Omi.

Si tenes `pipx`:

```sh
pipx install omi-cli
omi --help
```

Podes puru installare in un'ambiente virtuale Python ativu:

```sh
python -m pip install omi-cli
omi --help
```

Si su terminal no agatat `omi`, assegura·te chi s'ambiente virtuale est ativu o chi sa cartella de `pipx` est in `$PATH`.

## Connectare su contu tuo

Cumintza s'assistente interativu:

```sh
omi auth login
```

Sceberi de intrare cun su navigadore o de incollare una crae API de isvilupadore Omi. S'input interativu cuat sa crae; evita de l'iscriere in unu cumandu chi abarrat in s'istòria de su terminal.

Pro andare deretu a su navigadore:

```sh
omi auth login --browser
```

Intra in su matessi elaboradore de su terminal: sa risposta de autenticatzione andat a s'indiritzu locale. Sighi is istrutziones in s'ischermu.

A pustis, verìfica sa cunfiguratzione e s'atzessu API:

```sh
omi auth status
omi auth whoami
```

`status` mustrat s'istadu locale e cuat su segretu, ma no verìficat sa validade in su serbidore. `whoami` faghet una dimanda autenticada; si resessit, est craru chi is credentziales funzionant, chene mustrare su nòmine tuo.

Sa cunfiguratzione est sarvada comente a default in `~/.omi/config.toml`. No cumpartzis custu file: podet cuntènnere credentziales privadas.

## Esplorare is datos tuos

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Una lista bòida a s'ispissu signìficat petzi chi non b'est nudda chi currispondet a sa chirca. Imprea s'agiudu pro agatare is filtros de onni cumandu:

```sh
omi memory list --help
omi action-item list --help
```

## JSON e pàginas

Pone s'optzione globale `--json` **antis** de su grupu de cumandos:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Su primu cumandu pedit is primas 25 memòrias; su segundu is 25 chi sighint. Una pàgina sola no est una còpia cumpleta. S'output JSON mantenit is nùmeros intreos, mentras is taulas in s'ischermu podent iscurtzare·los.

Pro sarvare una pàgina in unu file:

```sh
omi --json memory list --limit 25 --offset 0 > memòria-pàgina-1.json
```

Custa rediretzione creadet o subraiscriet unu file locale. Assegura·te chi su cumandu est agabbadu antis de impreare su cuntènnidu. Is errores bènnint iscritas in s'output de errore (stderr); unu file bòidu no est una proa chi non b'apat datos. Unu file esportadu podet cuntènnere informatzione personale: mantene·lu privadu.

## Essire

```sh
omi auth logout
```

Custu cumandu cantzellat is credentziales sarvadas in locale. Pro invalidare una crae in su serbidore, imprea sa gestione de is craes de isvilupadore in su contu tuo.

Pro àteros cumandos e optziones, castia sa [ghia printzipale in inglesu](../README.md) e `omi --help`.
