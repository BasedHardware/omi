# Emprims pass cun omi-cli

Questa guida ta mussa ils emprims pass cun omi-cli, scrìtta en rumantsch. Ils nums da las cumondas e ls messagis dal program restan en englais. Ils exempels da questa guida na midan betg tias memorias, conversaziuns, elements d'acziun u objectivs.

## Installaziun

Ti dovras Python 3.10 u pli nov, ed in conto Omi.

Sche `pipx` è gia avant maun:

```sh
pipx install omi-cli
omi --help
```

Autramain pon ins l'installar en in ambient virtual da Python activ:

```sh
python -m pip install omi-cli
omi --help
```

Sche il terminal na chatta betg `omi`, controllescha sche l'ambient virtual è activ u sche la funda da `pipx` è en il `$PATH`.

## Cunectar tes conto

Cumenza l'assistent d'annunzia interactiv:

```sh
omi auth login
```

Ti pos tscherner: s'annunziar cun il navigatur u engular ina clav API da sviluppader Omi. L'endataziun interactiva zuppenta la clav; fa attenziun e na laschar betg la clav en l'istorgia dal terminal.

Per s'annunziar directamain cun il navigatur:

```sh
omi auth login --browser
```

T'annunzia sin la medema maschina sin la quala il terminal vegn executà: la resposta d'autorisaziun dovra in'adressa locala. Suonda las instrucziuns sin il visur.

Ussa controllescha la configuraziun e la clav API:

```sh
omi auth status
omi auth whoami
```

`status` mussa il status local e zuppenta ils segrets, ma na controllescha betg cun il server. `whoami` trametta ina dumonda autorisada; sche quai va bain, sas che tias credenzialas funcziunan, ma el na mussa betg tes num.

La configuraziun è en `~/.omi/config.toml`. Na partaglia betg questa datoteca: ella po cuntegnair segrets d'annunzia.

## Explorar las datas

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Ina glista veglia po simplamain signifitgar che naginas datas correspundan. Per emprender ils filters da mintga cumonda, guarda l'agid:

```sh
omi memory list --help
omi action-item list --help
```

## Sortida JSON e paginaziun

Mette l'opziun globala `--json` **avant** il grup da cumondas:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

L'emprima cumonda prenda ils emprims 25 elements; la segunda prenda ils proxims 25. Ina pagina è savens betg plaina. La sortida JSON mantegna tut ils identificaturs, entant che las tabellas sin il visur ils scurschan.

Per scriver ina pagina en ina datoteca:

```sh
omi --json memory list --limit 25 --offset 0 > memorias-pagina-1.json
```

La redirecziun creescha u surscri ina datoteca locala. Controllescha che la cumonda saja ìda bain avant d'utilisar il cuntegn. Ils sbagls van a stderr; ina datoteca veglia na munta betg che naginas datas existian. Las datotecas exportadas pon cuntegnair segrets: archivescha ellas segiramain.

## Sortir

```sh
omi auth logout
```

Questa cumonda allontanescha las credenzialas memorisadas localmain. Per revocar la clav sin il server, utilisescha la gestiun da claves da sviluppader en tes conto.

Per dapli cumondas ed opziuns avanzadas, guarda la [guida principala en englais](../README.md) ed `omi --help`.
