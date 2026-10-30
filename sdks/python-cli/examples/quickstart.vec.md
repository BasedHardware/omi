# I primi passi co omi-cli

Sta guida ła spiega i primi comandi (commands) de omi-cli in vèneto. I nomi de i comandi e i mesaĝi del programa i resta in inglexe. I esempi de riserca mostrà qua no i canbia łe to memorie (memories), łe to conversasion (conversations), łe to atività (action items) o i to obietivi (goals).

## Instałasion

Ghe vol: Python 3.10 o pì novo, e un account Omi.

Se te ghè `pipx`:

```sh
pipx install omi-cli
omi --help
```

Te pol anca instałarlo drento un ambiente virtuałe Python ativo:

```sh
python -m pip install omi-cli
omi --help
```

Se el terminal no cata `omi`, asicura che l'ambiente virtuałe el sipa ativo o che ła cartèła de `pipx` ła sipa in `$PATH`.

## Conegere el to account

Scumisia l'asistente interativo:

```sh
omi auth login
```

Siegli de entrar col browser o de incolar na ciave API de svilupador Omi. L'input interativo el sconde ła ciave; evita de scrivarla in un comando che resta inte ła storia del terminal.

Par ndar drito al browser:

```sh
omi auth login --browser
```

Entra sul isteso computer del terminal: ła risposta de autenticasion ła va a l'indiriso locałe. Segui łe istrusion sul schermo.

Par dopo, verifica ła configurasion e l'aceso API:

```sh
omi auth status
omi auth whoami
```

`status` el mostra el stato locałe e el sconde el segreto, ma no'l verifica ła vałidità sul server. `whoami` el fa na richiesta autenticà; se ła funsiona, xe ciaro che łe credensiałi łe funsiona, sensa mostrar el to nome.

Ła configurasion ła vien salvà de default in `~/.omi/config.toml`. No spartir sto file: el pol contegnere credensiałi privae.

## Esplorar i to dati

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Na lista voda de solito ła signaifica soło che no ghe xe njente che corisponde a ła riserca. Dòpara l'agiuto par catar i filtri de ogni comando:

```sh
omi memory list --help
omi action-item list --help
```

## JSON e pajine

Mete l'opsion globałe `--json` **prima** del grupo de comandi:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

El primo comando el domanda łe prime 25 memorie; el secondo łe 25 che vien dopo. Na pajina soła no xe na copia conpleta. L'output JSON el conserva i nùmari intieri, mentre łe tabełe sul schermo łe pol scursarli.

Par salvar na pajina in un file:

```sh
omi --json memory list --limit 25 --offset 0 > memorie-pajina-1.json
```

Sta rediresion ła crea o ła sorascrive un file locałe. Asicura che el comando el sipa finio prima de doparar el contegnuo. I erori i vien scridi nela output de eror (stderr); un file vodo no xe na prova che no ghe sipia dati. Un file esportà el pol contegnere informasion personałe: tienlo privà.

## Desconetarse

```sh
omi auth logout
```

Sto comando el scanseła łe credensiałi salvae localmente. Par invalidar na ciave sul server, dòpara ła gestion de łe ciavi de svilupador inte el to account.

Par pì comandi e opsion, varda ła [guida prinsipałe in inglexe](../README.md) e `omi --help`.
