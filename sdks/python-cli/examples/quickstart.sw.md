# Kuanza kutumia omi-cli

Mwongozo huu unaonyesha amri chache za kwanza kwa Kiswahili. Majina ya amri na jumbe za mfumo zinabaki kwa Kiingereza. Mifano ya kusoma iliyotolewa hapa haitabadilisha kumbukumbu, mazungumzo, orodha ya kazi au malengo yako.

## Sakinisha programu

Mahitaji: Python 3.10 au toleo jipya zaidi na akaunti ya Omi.

> Angalizo: Jina la kifurushi kwenye PyPI ni **`omi-cli`**, wakati amri inayoendeshwa baada ya kusakinisha ni **`omi`**. Kuna kifurushi tofauti kisichohusiana kiitwacho `omi` kwenye PyPI — usisakinishe kifurushi hicho.

Ikiwa `pipx` imesakinishwa:

```sh
pipx install omi-cli
omi --help
```

Vinginevyo, ndani ya mazingira pepe ya Python:

```sh
python -m pip install omi-cli
omi --help
```

Ikiwa terminal haipati `omi`, hakikisha mazingira pepe yanafanya kazi au saraka ya `pipx` ipo kwenye `PATH` yako.

## Unganisha akaunti yako

Anzisha msaidizi wa maingiliano:

```sh
omi auth login
```

Chagua kuingia kupitia kivinjari, au weka ufunguo wa API ya msanidi programu wa Omi. Uingizaji fiche huficha ufunguo; usiandike ufunguo kwenye amri itakayohifadhiwa kwenye kumbukumbu ya terminal.

Kuingia moja kwa moja kupitia kivinjari:

```sh
omi auth login --browser
```

Kamilisha kuingia kwenye kompyuta ile ile inayoendesha terminal, kwani uthibitishaji unarudi kwenye anwani ya ndani. Fuata maagizo yanayoonekana kwenye skrini.

Baada ya hapo, kagua usanidi na ufikiaji wa API:

```sh
omi auth status
omi auth whoami
```

`status` inaonyesha hali ya ndani na kuficha siri, lakini haithibitishi na seva. `whoami` hutuma ombi lililoidhinishwa; mafanikio yanamaanisha hati zako zinafanya kazi vizuri.

Usanidi unahifadhiwa kwa chaguo-msingi katika `~/.omi/config.toml`. Usishiriki faili hii kwa sababu ina hati zako za siri.

## Tazama data yako

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Orodha tupu inaweza kumaanisha tu kwamba hakuna vipengee vinavyolingana na ombi lako. Ili kuelewa vichujio vya amri, angalia usaidizi:

```sh
omi memory list --help
omi action-item list --help
```

## Pata JSON na kurasa

Weka chaguo la jumla `--json` **kabla** ya kikundi cha amri:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Amri ya kwanza inaomba rekodi 25 za kwanza; ya pili inaomba rekodi 25 zinazofuata. Kwa hivyo ukurasa mmoja sio nakala kamili. Matokeo ya JSON yanahifadhi vitambulisho kamili, wakati majedwali yanaweza kuvifupisha.

Kuhifadhi ukurasa kwenye faili:

```sh
omi --json memory list --limit 25 --offset 0 > kumbukumbu-ukurasa-1.json
```

Uelekezaji huu huunda au kubadilisha faili ya ndani. Kabla ya kutumia maudhui, hakikisha amri imefaulu. Makosa huandikwa kwenye stderr; faili tupu si uthibitisho wa kutokuwepo kwa data. Faili iliyohifadhiwa inaweza kuwa na taarifa binafsi: iweke salama.

## Ondoka kwenye akaunti

```sh
omi auth logout
```

Amri hii huondoa hati zilizohifadhiwa ndani ya kompyuta. Kufuta au kubatilisha ufunguo kwenye seva, tumia usimamizi wa funguo za msanidi programu kwenye akaunti yako.

Kwa amri nyingine na chaguzi za juu, tafadhali tazama mwongozo mkuu kwa Kiingereza:
[../README.md](../README.md) na `omi --help`.
