# Emprim pass cun omi-cli

Questa guida declera las emprimas cumondas en rumantsch. Ils nums da las
cumondas ed ils messadis dal program restan en englais. Ils exempels da
dumondas preschentads qua na midan betg tias regurdientschas, conversaziuns,
incumbensas u finamiras.

## Installaziun dal program

Requisits: Python 3.10 u pli nova versiun ed in access Omi.

Sch'as ha installÃ  `pipx`:

```sh
pipx install omi-cli
omi --help
```

Ins po era installar en in ambient virtual (virtual environment) da Python:

```sh
python -m pip install omi-cli
omi --help
```

Sch'il terminal na chattia betg `omi`, verifitgescha che l'ambient virtual saja
activ u che la cartella nua che `pipx` installescha scripts executabels saja en
tia variabla `PATH`.

## Connescha tes access

Starta l'assistent interactiv:

```sh
omi auth login
```

Tscherne da s'annunziar via browser u collia ina clav API per sviluppaders dad Omi.
L'entrada interactiva zuppenta la clav; evita da scriver ella en ina cumonda che
resta en l'istorgia dal terminal.

Per ir directamain al browser:

```sh
omi auth login --browser
```

Annunzia te sin il medem computer nua che il terminal currat: la resposta d'autenticaziun
utilisescha in adress local. Suai las instrucziuns sin l'ecran.

Suenter quai verifitgeschia l'installaziun e l'access a l'API:

```sh
omi auth status
omi auth whoami
```

`status` mussa il stadi local e zuppenta il secret ma na controlla betg la valur
sin il server. `whoami` trametta ina dumonda autenticada; sch'i funcziuna, conferma
quai che las credenzialas funcziunan, senza necessariamain mussar tes num.

Las configuraziuns vegnan salvadas automaticamain en `~/.omi/config.toml`. Na
cundividia betg questa datoteca: ella po cuntegnir tias infurmaziuns secretas
d'access.

## Explora tias datas

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Ina glista vida pudess simplamain muntar che nagin element correspunda a la
dumonda. Utilisescha l'agid per veser filtras per mintga cumonda:

```sh
omi memory list --help
omi action-item list --help
```

## Obtegnair JSON e navigar tranter paginas

Metta l'opziun globala `--json` **avant** il grup da cumondas:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

L'emprima cumonda dumonda las emprimas 25 regurdientschas; la segunda dumonda
las proximas 25. Ina pagina sola n'Ã¨ pia betg in backup cumplet. L'output JSON
mantegna IDs cumplets, entant che tabellas sin l'ecran pudessan scursanir els
per la mussada.

Per salvar ina pagina en ina datoteca:

```sh
omi --json memory list --limit 25 --offset 0 > regurdientschas-pagina-1.json
```

Quest redirect creescha u surscriva la datoteca locala. Verifitgescha che la
cumonda haja terminÃ  senza errurs avant d'utilisar il cuntegn. Errurs vegnan
scrittas en l'output d'errur (stderr); ina datoteca vida na garantescha betg
che naginas datas existian. La datoteca exportada po cuntegnir datas persunalas:
tenila privata.

## Deconnexiun (Logout)

```sh
omi auth logout
```

Questa cumonda effatga las infurmaziuns d'access salvadas localmain. Per revocar
ina clav sin il server utilisescha la gestiun da clav API en tes access.

Per autras cumondas ed opziuns pli detagliadas, vesai la
[guida principala en englais](../README.md) e `omi --help`.
