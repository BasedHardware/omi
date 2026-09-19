# Kom í gongd við omi-cli

Hesi leiðbeining vísir tær fyrstu boðini á føroyskum. Nøvn á boðum og kervsboð vera verandi á enskum. Lesidømini, ið verða víst her, broyta ikki tíni minni, samrøður, gerðalistar ella mál.

## Legg forritið inn

Krøv: Python 3.10 ella nýggjari útgáva og ein Omi-vangi.

> Legg til merkis: Pakkanavnið á PyPI er **`omi-cli`**, meðan boðið, ið koyrir eftir innlegging, er **`omi`**. Ein annar óviðkomandi pakki við heitinum `omi` er á PyPI — installera ikki tann pakkan.

Um `pipx` er innlagt:

```sh
pipx install omi-cli
omi --help
```

Annars, í einum virknum Python sýndarumhvørvi:

```sh
python -m pip install omi-cli
omi --help
```

Um terminalurin ikki finnur `omi`, kanna so eftir, um sýndarumhvørvið er virkið, ella um `pipx`-mappan er í tínari `PATH`.

## Knyt tín vanga at

Byrja tað virkna hjálpartólið:

```sh
omi auth login
```

Vel at rita inn umvegis kagara, ella vel møguleikan at seta inn ein Omi mennara-API-lykil. Innslátturin krógvar lykilin; skriva ikki lykilin í boð, ið verða goymd í søguni hjá terminalinum.

Fyri beinleiðis innritan umvegis kagara:

```sh
omi auth login --browser
```

Fullfør innritanina á somu teldu, har terminalurin koyrir, av tí at váttanin fer aftur til eina lokala adressu. Fylg leiðbeiningunum á skíggjanum.

Eftir tað, kanna uppsetingina og API-atgongdina:

```sh
omi auth status
omi auth whoami
```

`status` vísir lokalu støðuna og krógvar loyndarmál, men váttar ikki við ambætan. `whoami` sendir eina góðkenda áheitan; eydnað úrslit merkir, at tíni loyniorð virka rætt.

Uppsetingin verður goymd sum sjálvgevið í `~/.omi/config.toml`. Deil ikki hesa fílu, tí hon inniheldur tíni persónligu loyniorð.

## Hygg at tínum dátu

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Ein tómur listi kann bert merkja, at einki samsvarar við tína fyrispurning. Fyri at skilja sílini hjá einum boði, hygg í hjálpina:

```sh
omi memory list --help
omi action-item list --help
```

## Fá JSON og blaða millum síður

Set tað almenna valið `--json` **áðrenn** boðbólkin:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Fyrsta boðið biður um tey fyrstu 25 skjølini; annað boðið biður um tey næstu 25. Tí er ein síða ikki ein fullfíggjað trygdarkopí. JSON-úttakið varðveitir fullar eyðmerkingar, meðan talvur kunnu stytta tær.

Fyri at goyma eina síðu í einari fílu:

```sh
omi --json memory list --limit 25 --offset 0 > minni-sida-1.json
```

Henda umstýring stovnar ella kemur í staðin fyri eina lokala fílu. Áðrenn tú brúkar innihaldið, tryggja tær, at boðið hepnaðist. Villur verða skrivaðar á stderr; ein tóm fíla er ikki próv fyri manglandi dátu. Goymda fílan kann innihalda persónligar upplýsingar: goym hana trygt.

## Rita út (Log out)

```sh
omi auth logout
```

Hetta boðið strikar loyniorð, ið eru goymd lokalt. Fyri at ógilda ein lykil á ambætaranum, nýt mennaralykla-stýringina á tínum vanga.

Fyri onnur boð og víðkaðar møguleikar, sí vinarliga høvuðsleiðbeiningina á enskum:
[../README.md](../README.md) og `omi --help`.
