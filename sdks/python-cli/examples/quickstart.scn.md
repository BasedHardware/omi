# Li primi passi cu omi-cli

Sta guida spiega li primi cumanni (commands) di omi-cli 'n sicilianu. Li nomi di li cumanni e li missaggi dû prugramma ristànu 'n ngrisi. Li esempi di circata ammustrati ccà nun càncianu li to ricordu (memories), li to cunversazzioni (conversations), li to cosi di fari (action items) o li to ubbiettivi (goals).

## Nstallazzioni

Ci voli: Python 3.10 o cchiù novu, e un cuntu Omi.

Si hai `pipx`:

```sh
pipx install omi-cli
omi --help
```

Lu poi nstallari macari nta n'ambienti virtuali Python attivu:

```sh
python -m pip install omi-cli
omi --help
```

Si lu terminali nun trova `omi`, fai 'n modu ca l'ambienti virtuali è attivu o ca la cartella di `pipx` s'attrova ntô `$PATH`.

## Cunnettiri lu to cuntu

Accuminza l'assistenti interattivu:

```sh
omi auth login
```

Scegghji d'accèdiri cu lu browser o d'incuddari na chiavi API pû sviluppaturi Omi. L'input interattivu ammuccia la chiavi; evita di scrìviri la chiavi nta un cumannu ca veni arricurdatu ntâ storia dû terminali.

Pi jiri drittu ô browser:

```sh
omi auth login --browser
```

Accedi ntô stissu computer dû terminali: la risposta di autenticazzioni va a l'indirizzu lucali. Sèquita li struzzioni ntô schermu.

Appoi, verifica la cunfigurazzioni e l'accessu API:

```sh
omi auth status
omi auth whoami
```

`status` mustra lu statu lucali e ammuccia lu secret, ma nun verifica la validitati ntô server. `whoami` fa na dumanna autenticata; si riesci, è chiaru ca li cridenziali fùncianu, senza ammustrari lu to nomu.

La cunfigurazzioni veni sarvata di default ntô `~/.omi/config.toml`. Nun spàrtiri stu file: pò cunteniri cridenziali risirvati.

## Esplurari li to dati

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Na lista vacanti spissu significa sulu ca nenti currispunni â circata. Usa l'aiutu pi truvari li filtri di ogni cumannu:

```sh
omi memory list --help
omi action-item list --help
```

## JSON e paginazzioni

Metti l'opzioni glubbali `--json` **prima** dû gruppu di cumanni:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Lu primu cumannu dumanna li primi 25 ricordu; lu secunnu li 25 appressu. Na pàggina sula nun è na copia cumpleta. L'output JSON priserva li nùmmari interi, mentri li tàuli ntô schermu li pònnu accurtari.

Pi sarvari na pàggina nta un file:

```sh
omi --json memory list --limit 25 --offset 0 > ricordu-paggina-1.json
```

Sta ridirezzioni criàu o suprascrivi un file lucali. Assicùrati ca lu cumannu finiu prima d'usari lu cuntinutu. Li erruri vèninu scritti ntâ l'output di erruri (stderr); un file vacanti nun è na prova ca nun cc'è dati. Un file esportatu pò cunteniri nfurmazzioni pirsunali: tenilu privatu.

## Scùnniri

```sh
omi auth logout
```

Stu cumannu cancella li cridenziali sarvati lucalmenti. Pi invaliddari na chiavi ntô server, usa la gestioni dî chiavi dû sviluppaturi ntô to cuntu.

Pi àutri cumanni e opzioni, talìa la [guida principali 'n ngrisi](../README.md) e `omi --help`.
