# Prims pass cun omi-cli

Questa guida explondi ils emprims cumonds (commands) da omi-cli en rumantsch. Ils nums dals cumonds ed ils messagis dal program restan en englais. Ils exempels da tschertgar mussads qua na mida betg vos memorias (memories), vossas conversaziuns (conversations), vos incumbensas (action items) ni vos objects (goals).

## Installaziun

Basegnus: Python 3.10 u pli nov, ed in conto Omi.

Sche vus avais `pipx`:

```sh
pipx install omi-cli
omi --help
```

Vus pudais era installar en in ambient virtual da Python activ:

```sh
python -m pip install omi-cli
omi --help
```

Sche il terminal na chatta betg `omi`, segirar che l'ambient virtual è activ u che l'ordinatur da `pipx` è en `$PATH`.

## Colliar tes conto

Cumenzar l'assistent interactiv:

```sh
omi auth login
```

Tscherner d'entrar tras il navigatur u d'incollar ina clav API da sviluppader Omi. L'endataziun interactiva zuppenta la clav; evitar da scriver la clav en in cumond che vegn memorisà en l'istorgia dal terminal.

Per ir directamain al navigatur:

```sh
omi auth login --browser
```

Entrar sin il medem computer dal terminal: la resposta d'autenticaziun va a l'adressa locala. Suandar las instrucziuns sin il monitor.

Suenter, verifitgar la configuraziun e l'access API:

```sh
omi auth status
omi auth whoami
```

`status` mussa il stadi local e zuppenta il secret, ma na verifitga betg la valaidad sin il server. `whoami` fa ina dumonda autentifitgada; sche quella reussescha, è cler che las credenzialas funcziunan, senza mussar tes num.

La configuraziun vegn memorisada per standard en `~/.omi/config.toml`. Na partais questa datoteca betg: ella po cuntegnair credenzialas privatas.

## Explorar tes datas

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Ina glista veglia per ordinari signifitga be che nagut correspunda a la tschertga. Utilisar l'agid per chattar ils filters da mintga cumond:

```sh
omi memory list --help
omi action-item list --help
```

## JSON e paginas

Metter l'opziun globala `--json` **avant** la gruppa da cumonds:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Il prim cumond dumonda las emprimas 25 memorias; il segund las 25 proximas. Ina pagina suletta n'è betg ina copia cumpletta. La sortida JSON conserva ils nums entirs, entant che las tabellas sin il monitor las pon scursanir.

Per memorisar ina pagina en ina datoteca:

```sh
omi --json memory list --limit 25 --offset 0 > memorias-pagina-1.json
```

Questa redirecziun creescha u surscriva ina datoteca locala. Segirar che il cumond è finì avant d'utilisar il cuntegn. Ils sbagls vegnan scrit en la sortida d'errur (stderr); ina datoteca veglia n'è betg ina prova che na daten betg. Ina datoteca exportada po cuntegnair infurmaziuns persunalas: memorisar quella en mod privat.

## Sortir

```sh
omi auth logout
```

Quest cumond stizza las credenzialas memorisadas localmain. Per invalidar ina clav sin il server, utilisar la gestiun da claves da sviluppader en tes agen conto.

Per dapli cumonds ed opziuns, guardar la [guida principala en englais](../README.md) e `omi --help`.
