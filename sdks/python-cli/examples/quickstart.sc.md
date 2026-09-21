# Primos passos cun omi-cli

Custa ghia contat is primos cumandos de omi-cli in sardu. Is nòminis de is cumandos e is messàgios de su programa abarrant in inglesu. Is esempros de custa ghia non mudant is arregonos, is cunversatziones, is atziones o is obietivos tuos.

## Installatzione

Ti serbit Python 3.10 o prus nou, e unu contu Omi.

Si `pipx` est giai installadu:

```sh
pipx install omi-cli
omi --help
```

Sinnò, installa·lu in un'ambiente virtuale Python ativu:

```sh
python -m pip install omi-cli
omi --help
```

Si su terminal non agatat `omi`, controlla si s'ambiente virtuale est ativu o si sa cartella de pipx est in `$PATH`.

## Connessione de su contu

Alloga s'assistente de connessione interativu:

```sh
omi auth login
```

Podes isseberare de intrare cun su navegadore o de incollare una crae API de isviluppadore Omi. Sa connessione interativa cuat sa crae tua; sta attentu e non la lesses in s'istòria de su terminal.

Pro intrare deretu cun su navegadore:

```sh
omi auth login --browser
```

Intra in su matessi elaboradore in ue curret su terminal: sa resposta de autorizatzione impreat un'indiritzu locale. Sighi is istrutziones in s'ischermu.

Controlla como sa cunfiguratzione e sa crae API:

```sh
omi auth status
omi auth whoami
```

`status` ammustrat s'istadu locale e cuat is segretos, ma non controllat cun su serbidore. `whoami` faghet una rechesta autorizada; si resessit, cunfirmat chi s'autorizatzione tua funtzionat, ma non ammustrat su nòmine tuo.

Sa cunfiguratzione s'agatat in `~/.omi/config.toml`. Non cumpartzis custu documentu: podet cuntenner segretos de connessione.

## Esplorare is datos

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Una lista bòida podet simplicemente significare chi non b'at datos chi currispondent a sa rechesta. Pro imparare is filtros de cada cumandu, castia s'agiudu:

```sh
omi memory list --help
omi action-item list --help
```

## Essida JSON e paginadura

Pone s'optzione globale `--json` **antis** de su grupu de cumandos:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Su primu cumandu pigat is primos 25 arregonos; su segundu pigat is 25 chi sighint. Una pàgina sòlet non èssere prena. S'essida JSON mantenet totu is identificadores, mentras is tabellas in s'ischermu sòlent iscursare·los.

Pro iscrìere una pàgina in unu documentu:

```sh
omi --json memory list --limit 25 --offset 0 > arregonos-pàgina-1.json
```

Sa ridiretzione creadet o iscriet subra unu documentu locale. Controlla chi su cumandu apat tentu èsitu antis de impreare su cuntènnidu. Is errores andant a stderr; unu documentu bòidu non significat chi non b'at datos. Is documentos esportados podent cuntenner informatziones privadas: custòdia·los in seguresa.

## Disconnessione

```sh
omi auth logout
```

Custu cumandu bogat s'autorizatzione locale sarvada. Pro revocare sa crae in su serbidore, imprea sa gestione de is craes de isviluppadore in su contu tuo.

Pro àteros cumandos e optziones avansadas, castia sa [Ghia printzipale in inglesu](../README.md) e `omi --help`.
