# Vuide svelte di omi-cli

Cheste vuide e spieghe i prins comants par furlan (Friulian). I nons dai comants e i messaçs dal program a restin par inglês. I esemplis di esplorazion che a son chi no modifichin lis vuestris memoriis (memories), conversazions (conversations), azions di fâ (action items) o obietîfs (goals).

## Instalazion

Rechisîts: Python 3.10 o une version plui resinte, e un account Omi.

Se tu âs instalât `pipx`:

```sh
pipx install omi-cli
omi --help
```

Tu puedis ancje instalâlu dentri di un ambient virtuâl di Python atîf:

```sh
python -m pip install omi-cli
omi --help
```

Se il terminâl nol cjate `omi`, controle che l'ambient virtuâl al sedi atîf o che il percors di instalazion di `pipx` al sedi tal to `$PATH`.

## Coneti il to account

Fâs partî il percors interatîf par jentrâ:

```sh
omi auth login
```

Sielç di jentrâ cul navigadôr o incolant la clâf API di svilupadôr di Omi. L'inseriment interatîf al plate la clâf; chest al jude a evitâ di scrivi la clâf tal storic dai comants dal terminâl.

Par jentrâ diretementri cul navigadôr:

```sh
omi auth login --browser
```

Jentre tal stes computer dulà che tu sês tal terminâl: il callback di autorizazion al dopre une direzion locâl. Va daûr des instruzions sul schermi.

Daspò, controle la configurazion e l'acès ae API:

```sh
omi auth status
omi auth whoami
```

`status` al mostre il stât locâl e al plate i segrets, ma nol convalide la validitât cul servidôr. `whoami` al fâs une clamade autentiche; se e à sucès, e conferme che lis credenziâls a funzionin, cence la dibisugne di esponi il to non.

La configurazion e je salvade in maniere predefinide in `~/.omi/config.toml`. No sta a condividi chest file: al pues contignî segrets di acès.

## Esplorazion dai dâts

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Une liste vueide e pues volê dî dome che no son ancjemò dâts che a corispuindin ae ricerche. Dopre l'aiût par discuvierzi i filtris disponibii par ogni comant:

```sh
omi memory list --help
omi action-item list --help
```

## Jessude JSON e pagjinazion

Met la opzion globâl `--json` **prime** dal grup di comants:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Il prin comant al domande lis primis 25 memoriis; il secont al cjape lis 25 sucessivis. Une pagjine no je un backup complet. La jessude JSON e ten ducj i ID intiers, intant che lis tabelis a schermi a puedin scurtâju pe visualizazion.

Par salvâ une pagjine suntun file:

```sh
omi --json memory list --limit 25 --offset 0 > memoriis-pagjine-1.json
```

Cheste redirezion e cree o e sorescûr il file locâl. Controle che il comant al sedi lât a bon fin prime di doprâ il contignût. I erôrs a son scrits su stderr; un file vueit nol garantìs che no sedin dâts. Il file esportât al pues contignî dâts personâi: no sta a pandilu.

## Jessude (Logout)

```sh
omi auth logout
```

Chest comant al scancele lis credenziâls salvadis in locâl. Par revocâ une clâf sul servidôr, dopre la pagjine des clâfs dai svilupadôrs tal to account.

Par altris comants e opzions plui avanzadis, cjale la [vuide principâl par inglês](../README.md) e `omi --help`.
