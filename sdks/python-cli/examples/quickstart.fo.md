# Fyrstu fetini við omi-cli

Henda vegleiðingin greiðir frá teimum fyrstu boðunum á føroyskum. Nøvn á boðum og boð
frá forritinum eru framvegis á enskum. Fyrispurnardømini her broyta ikki tínar
minnir, samrøður, uppgávur ella mál.

## Innlegging av forritinum

Krov: Python 3.10 ella nýggjari útgáva og ein Omi konta.

Um tú hevur `pipx` lagt inn:

```sh
pipx install omi-cli
omi --help
```

Tað ber eisini til at leggja tað inn í einum virknum sýndarumhvørvi (virtual environment)
í Python:

```sh
python -m pip install omi-cli
omi --help
```

Um stýriborðið (terminal) ikki finnur `omi`, tryggja tær tá, at sýndarumhvørvið er
virkið, ella at mappain har `pipx` leggur koyrifílur er í tíni `PATH` broytu.

## Knýt tína kontu

Byrja gagnvirka hjálparforritið:

```sh
omi auth login
```

Vel at rita inn umvegis kagara (browser) ella set inn ein Omi mennara API-lykil.
Gagnvirka inntøkan fjælir lykilin; lat vera við at skriva hann í eitt boð, sum
verður verandi í søguni hjá stýriborðinum.

Fyri at fara beinleiðis til kagaran:

```sh
omi auth login --browser
```

Rita inn á somu teldu sum stýriborðið koyrir á: váttanarsvarið nýtir eina
staðbundna adressu. Fylg leiðbeiningini á skíggjanum.

Eftir hetta skalt tú vátta uppsetingina og atgongdina til API:

```sh
omi auth status
omi auth whoami
```

`status` vísir staðbundnu støðuna og fjælir loyniliga lykilin, men kannar ikki
gildið á ambætanum. `whoami` sendir ein samtyktan fyrispurning; um hann eydnast,
váttar hann at loyniorðini virka, uttan neyðugt at vísa navnið títt.

Stillingarnar verða vanliga goymdar í `~/.omi/config.toml`. Deil ikki hesa
fílu: hon kann innihalda tíni loyniligu atgongdarupplýsingar.

## Kanna tíni dáta

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Ein tómur listi kann einfaldliga merkja, at eingir lutir passa til fyrispurningin.
Nýt hjálpina fyri at síggja sílur fyri hvørt boð:

```sh
omi memory list --help
omi action-item list --help
```

## Heinta JSON og fletta millum síður

Set víðfevnda valmøguleikan `--json` **framman fyri** boðbólkin:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Fyrra boðið biður um tey fyrstu 25 minnini; tað seinna um tey næstu 25. Ein síða
er tí ikki ein fullkomin trygdarkopía (backup). JSON úttakið varðveitir full eyðkenni,
meðan talvur á skíggjanum kunnu stytta tey til sjónar.

Fyri at goyma eina síðu í eina fílu:

```sh
omi --json memory list --limit 25 --offset 0 > minni-sida-1.json
```

Henda umstýring stovnar ella yvirskrivar staðbundnu fíluna. Gev gætur, at boðið
er liðugt uttan villur, áðrenn innihaldið verður nýtt. Villur verða skrivaðar til
villuúttak (stderr); ein tóm fíla tryggjar ikki, at eingin dáta eru til staðar.
Útflutta fílan kann innihalda persónligar upplýsingar: goym hana trygt og privatt.

## Útritan (Logout)

```sh
omi auth logout
```

Hetta boðið strikar staðbundið goymdar atgongdarupplýsingar. Fyri at ógilda ein
lykil á ambætanum skal umsiting av mennaralyklum á tínari kontu nýtast.

Fyri onnur boð og fleiri valmøguleikar, sí
[høvuðsvegleiðingina á enskum](../README.md) og `omi --help`.
