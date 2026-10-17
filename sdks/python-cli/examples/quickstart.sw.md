# Kuanza haraka na omi-cli

Mwongozo huu unaeleza amri za msingi kwa Kiswahili. Majina ya amri na ujumbe
wa programu hubaki kwa Kiingereza. Amri za mfano hapa chini hazibadilishi
kumbukumbu, mazungumzo, vipengee vya vitendo au malengo yako.

## Kusakinisha programu

Mahitaji: Python 3.10 au mpya zaidi na akaunti ya Omi.

Ikiwa `pipx` imesakinishwa:

```sh
pipx install omi-cli
omi --help
```

Au sakinisha katika mazingira ya Python virtual iliyowezeshwa:

```sh
python -m pip install omi-cli
omi --help
```

Ikiwa terminal haioni `omi`, hakikisha mazingira ya virtual imewezeshwa au
saraka ambayo `pipx` inaweka executable iko kwenye `PATH`.

## Kuunganisha akaunti yako

Endesha mwongozo wa kuingiliana:

```sh
omi auth login
```

Chagua kuingia kupitia kivinjari au bandika ufunguo wa API wa msanidi wa Omi.
Uingizaji wa kuingiliana huficha ufunguo; usiuandike kwenye amri zinazohifadhiwa
kwenye historia ya terminal.

Kutumia kivinjari moja kwa moja:

```sh
omi auth login --browser
```

Ingia kwenye kompyuta ile ile yenye terminal kwa sababu uthibitishaji hutumia
anwani ya callback ya ndani. Fuata maagizo yanayoonekana skrini.

Baada ya kuingia, kagua usanidi na ufikiaji wa API:

```sh
omi auth status
omi auth whoami
```

`status` inaonyesha hali ya ndani na kuficha siri, lakini haithibitishi
uhalali wake kwenye seva. `whoami` hutuma ombi lililothibitishwa; ikiwa
inafaulu, hati zako zinafanya kazi bila kuonyesha jina lako.

Usanidi huhifadhiwa kwa chaguo-msingi katika `~/.omi/config.toml`. Usishiriki
faili hii kwa sababu inaweza kuwa na hati.

## Kusoma data yako

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Orodha tupu inaweza kumaanisha kuwa hakuna kipengee kilicholingana na kichujio.
Tazama chaguo za kila amri katika msaada:

```sh
omi memory list --help
omi action-item list --help
```

## Kupata JSON na kuvinjari kurasa

Weka chaguo la kimataifa `--json` **kabla** ya kikundi cha amri:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Amri ya kwanza huomba kumbukumbu 25 za kwanza; ya pili huomba 25 zinazofuata.
Ukurasa mmoja si hifadhi kamili. Toleo la JSON huhifadhi ID kamili, ilhali
jedwali linaweza kufupisha ID kwa ajili ya kuonyesha.

Kuhifadhi ukurasa kwenye faili:

```sh
omi --json memory list --limit 25 --offset 0 > kumbukumbu-ukurasa-1.json
```

Uelekezaji huunda au kuandika upya faili ya ndani. Hakikisha amri imekamilika
kwa mafanikio kabla ya kutumia yaliyomo. Makosa huandikwa kwa stderr; faili
tupu si uthibitisho kwamba hakuna data. Faili ya uhamishaji inaweza kuwa na
taarifa binafsi — iweke kwa faragha.

## Kutumia profaili

Hali huhifadhiwa katika `~/.omi/config.toml` (inaweza kubadilishwa kwa
`$OMI_CONFIG`). Kila profaili ina njia yake ya uthibitishaji na anwani ya API.
Badilisha profaili kwa `--profile`:

```sh
omi config profile use kazi
omi auth login
omi --profile binafsi memory list
```

Amri za kawaida za usanidi:

```sh
omi config show
omi config path
omi config profile list
```

## Msimbo wa kutoka

Misimbu hii ya kutoka ni imara na muhimu kwa script au mawakala:

| Msimbo | Maana | Hali ya mfano |
| ---: | --- | --- |
| 0 | mafanikio | Amri imekamilika |
| 1 | kosa la matumizi | Bendera mbaya, hoja inayokosekana au uthibitishaji ulioshindwa |
| 2 | kosa la uthibitishaji | Hati hazipo, token imeisha au ruhusa hazitoshi |
| 3 | kosa la seva | Seva 5xx au muunganisho umeshindwa |
| 4 | kiwango kimezidiwa | Seva ilirudisha HTTP 429 |
| 5 | haikupatikana | Seva ilirudisha HTTP 404 |

## Kutoka

```sh
omi auth logout
```

Hii huondoa hati zilizohifadhiwa ndani. Kuufuta ufunguo kwenye seva, tumia
usimamizi wa ufunguo wa msanidi kwenye akaunti yako.

Kwa amri na chaguo zaidi, angalia [README kuu ya Kiingereza](../README.md) na
uendeshe `omi --help`.
