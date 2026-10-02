# Gavên Yekem bi omi-cli re

Ev rêber fermanên yekem bi zimanê Kurdî rave dike. Navên fermanan û peyamên
bernameyê bi îngilîzî dimînin. Nimûneyên pirsyarê yên li vir hatine nîşandan
bîranîn, axaftin, kar an armancên we naguherînin.

## Sazkirina bernameyê

Pêdivî: Python 3.10 an guhertoyek nûtir û hesabek Omi.

Heke `pipx` sazkirî be:

```sh
pipx install omi-cli
omi --help
```

Wekî din, hûn dikarin wê di nav jîngehek virtual a Python a çalak de saz bikin:

```sh
python -m pip install omi-cli
omi --help
```

Heke termînal `omi` nebîne, kontrol bikin ka jîngeha virtual çalak e an peldanka
ku `pipx` pelên xebitandinê lê saz dike di `PATH` a we de ye.

## Girêdana hesabê xwe

Alîkarê înteraktîf bidin destpêkirin:

```sh
omi auth login
```

Têketina bi rêya gerokê (browser) an vebijarka pêvekirina mifteya API ya pêşvebirê Omi hilbijêrin.
Ketina înteraktîf mifteyê vedişêre; xwe ji nivîsandina wê di fermanekê de ku di dîroka termînalê de bimîne biparêzin.

Ji bo rasterast çûna gerokê:

```sh
omi auth login --browser
```

Li ser heman komputera ku termînal lê dixebite têkevinê: bersiva erêkirinê navnîşanek herêmî bikar tîne.
Rêwerzên li ser ekranê bişopînin.

Piştî wê, vesazkirin û gihîştina API kontrol bikin:

```sh
omi auth status
omi auth whoami
```

`status` rewşa herêmî nîşan dide û sira vedişêre, lê rastdariya li ser serverê kontrol nake.
`whoami` daxwazek erêkirî dişîne; heke bi ser keve, ew piştrast dike ku nasname dixebitin, bêyî ku navê we nîşan bide.

Vesazkirin bixweber di `~/.omi/config.toml` de tê hilanîn. Vê pelê bi kesên din re parve nekin:
dibe ku agahdariya we ya nepenî tê de hebe.

## Dîtina daneyên xwe

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Lîsteyek vala dikare tenê were wateya ku ti tiştên li gorî pirsyarê nînin.
Ji bo dîtina parzûnên her fermanê alîkariyê bikar bînin:

```sh
omi memory list --help
omi action-item list --help
```

## Bidestxistina JSON û geroka di nav rûpelan de

Vebijarka gerdûnî `--json` **berî** koma fermanê bi cih bikin:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Fermana yekem 25 bîranînên yekem dixwaze; ya duyemîn, 25 ên din. Ji ber vê yekê rûpelek tenê ne kopiyek tevahî (backup) ye.
Derketina JSON nasnameyên tevahî diparêze, lê tabloyên li ser ekranê dikarin wan ji bo nîşandanê kurt bikin.

Ji bo hilanîna rûpelek di pelekê de:

```sh
omi --json memory list --limit 25 --offset 0 > biranin-rupel-1.json
```

Ev beralîkirin pelê herêmî diafirîne an diguhezîne. Berî ku naveroka wê bikar bînin,
piştrast bikin ku ferman bi serkeftî bi dawî bûye. Çewtî li derketina çewtiyê (stderr) têne nivîsandin;
pelek vala garantî nake ku dane tune ne. Pela hinartî dibe ku agahdariya kesane hebe: wê nepenî bihêlin.

## Derketina ji hesabê (Logout)

```sh
omi auth logout
```

Ev ferman nasnameyên herêmî hatine hilanîn jê dibe. Ji bo betalkirina mifteyek li ser serverê,
rêveberiya mifteyên pêşvebirê di hesabê xwe de bikar bînin.

Ji bo fermanên din û vebijarkên pêşkeftî, li [rêberê sereke bi îngilîzî](../README.md) û `omi --help` binêrin.
