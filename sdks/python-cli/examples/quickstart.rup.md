# Protili pãshefts cu omi-cli

Aest ghidu spuni protili pãshefts (commands) di omi-cli tu armãneashti. Numile di pãshefts shi misãdzile di programul rãmãn tu anglicheashti. Protile di cãutari arãtati aoa nu alãxea memuriili (memories), zburãrili (conversations), lucrili (action items) icã scopurili (goals) a tale.

## Instalari

Cari lipseashti: Python 3.10 icã ma noauã, shi un contu Omi.

Ma ai `pipx`:

```sh
pipx install omi-cli
omi --help
```

Poilji instalari shi tu un ambient virtual di Python cari lucreadzã:

```sh
python -m pip install omi-cli
omi --help
```

Ma terminalul nu aflã `omi`, sigurã cã ambientul virtual lucreadzã icã cã directorlu di `pipx` easti tu `$PATH`.

## Ligarea contului a tãu

Ahurheashti asistãntul interactiv:

```sh
omi auth login
```

Aleaghi s-intri prin browser icã s-baghi un clishe API di disvoltator Omi. Inputul interactiv ascundi clishea; fudi s-scrii clishea tu un pãsheft cari va s-hibã tu istoria di terminalu.

S-intri directu tu browser:

```sh
omi auth login --browser
```

Intrã tu acela computer cu terminalu: raspundul di autentificari s-ducã tu adresa localã. Urmeadzã instructsiile tu ecran.

Apoi, verificã configuratsia shi acessul API:

```sh
omi auth status
omi auth whoami
```

`status` aratã statul local shi ascundi secretul, ma nu verificã validitatea tu server. `whoami` fa un dimãndare autentificatã; ma lucreadzã, easti clar cã credentsialili lucreadzã, fãrã s-arate numele a tãu.

Configuratsia easti piturnisitã ca default tu `~/.omi/config.toml`. Nu parti aestu documentu: po s-aibã credentsiali privati.

## Cãutarea datelor a tale

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Un listã goalã spuni adesea cã nu easti nimic cari s-potrivescu cu cãutarea. Ufiliseadzã agiutorlu s-aflã filtrele di fiekare pãsheft:

```sh
omi memory list --help
omi action-item list --help
```

## JSON shi frãndzãli

Puni optsiunea globalã `--json` **nãinti** di grupa di pãshefts:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Prãmlu pãsheft ceari protili 25 memurii; a doilu a 25 cari vin dupã. Un frãndzã singur nu easti un copii completu. JSON pãstreazã numerili ntregi, ma tabelili tu ecran li pot scurta.

S-piturniseshti un frãndzã tu un documentu:

```sh
omi --json memory list --limit 25 --offset 0 > memurii-frãndzã-1.json
```

Aestã redirectionare creeadzã icã scrii pãstã un documentu local. Sigurã cã pãsheftlu s-dipisi nãinti s-ufiliseashti con tinutul. Greashili s-scriu tu outputul di greashalã (stderr); un documentu goalã nu easti un probã cã nu suntu date. Un documentu exportat po s-aibã informatsii personali: piturniseash til privatu.

## Ieghirea

```sh
omi auth logout
```

Aestu pãsheft scoardã credentsialili piturnisitã local. S-invalideadzã un clishe tu server, ufiliseadzã administrarea di clishe di disvoltator tu contul a tãu.

Pentru ma multu pãshefts shi optsiuni, veadzã [ghidul principal tu anglicheashti](../README.md) shi `omi --help`.
