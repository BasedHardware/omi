# Fyrstu stig við omi-cli

Henda vegleiðing lýsir fyrstu boðunum (commands) hjá omi-cli á føroyskum. Nøvnini á boðunum og skilaboðini frá forritinum verða verandi á enskum. Dømini við leiting, sum víst eru her, broyta ikki minnið títt (memories), samrøðurnar tínar (conversations), verkin tíni (action items) ella málini tíni (goals).

## At seta forritið upp

Tørvur: Python 3.10 ella nýggjari, og ein Omi-konto.

Um tú hevur `pipx`:

```sh
pipx install omi-cli
omi --help
```

Tú kanst eisini seta tað upp í einum virknum Python-umhvørvi:

```sh
python -m pip install omi-cli
omi --help
```

Um terminalurin ikki finnur `omi`, tryggja tær, at umhvørvið er virkið, ella at mappan hjá `pipx` er í `$PATH`.

## At knýta kontoina tína

Byrja við tí interaktiva hjálparanum:

```sh
omi auth login
```

Vel at lógva inn gjøgnum kagan (browser) ella at límta inn ein Omi developer API-lykil. Interaktivur innskrivningur fjalir lykilin; forða tær at skriva hann í eitt boð, sum verður goymt í terminal-søguni.

Fyri at fara beint til kagan:

```sh
omi auth login --browser
```

Lógva inn á sama telduna sum terminalurin: authentication-svarið fer til lokala adressuna. Fylg leiðbeiningunum á skerminum.

Eftir tað kanst tú vátta uppsetningina og API-atgongdina:

```sh
omi auth status
omi auth whoami
```

`status` vísir lokala støðu og fjalir loyniorðið, men váttar ikki gyldigheitina á servaranum. `whoami` ger eina váttaða fyrispurning; um hann eydnast, er greitt at innskráningin virkar, uttan at navnið títt verður víst.

Uppsetningin verður goymd sum standard í `~/.omi/config.toml`. Deil ikki hesa fílu: hon kann innihalda trúnaðarupplýsingar.

## At kanna dáta tíni

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Ein tómur listi merkir ofta bara, at ekkert passar við leitingina. Brúka hjálpina fyri at finna filtur fyri hvørt boð:

```sh
omi memory list --help
omi action-item list --help
```

## JSON og síðuskipti

Set tann altjóða valmøguleikan `--json` **áðrenn** boðbólkin:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Fyrra boðið biður um fyrstu 25 minnini; annað um tey næstu 25. Ein síða er ikki fullgjør trygging. JSON-útskriftin varðveitir heil tøl, meðan talvur á skerminum kunnu gera tey styttri.

Fyri at goyma eina síðu í eina fílu:

```sh
omi --json memory list --limit 25 --offset 0 > minni-sida-1.json
```

Henda umleingjan skapar ella yvirskrivar eina lokala fílu. Tryggja tær, at boðið var fullgjørt, áðrenn tú brúkar innihaldið. Villur verða skrivaðar til error-útskriftina (stderr); ein tóm fíla er ikki prógv fyri, at eingin dáta er til. Ein útflutt fíla kann innihalda persónligar upplýsingar: goym hana privat.

## At rita út

```sh
omi auth logout
```

Hetta boðið strikar innskráningarupplýsingarnar, sum eru goymdar lokalt. Fyri at ógilda ein lykil á servaranum, brúka umsitingina fyri developer-lyklar á tínum egnu konto.

Fyri fleiri boð og valmøguleikar, sí [høvuðsvegleiðingina á enskum](../README.md) og `omi --help`.
