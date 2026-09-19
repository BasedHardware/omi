# omi-cli Faaba Waani-waani

Tira wo ga `omi-cli` jineɲe lordey fasal Zarmaciine (Zarma) sanni ra. Lordey maaɲey nda porogaramu alhabarey ga goro ka te Turanci sanni ra. Ceeci misaaley kaŋ yaŋ cawandi ne si war fongiyaney (memories), faagayey (conversations), goy izey kaŋ ga hima ka te (action items), wala anniyey (goals) barmay.

## Porogaramu Sinjiyaŋ (Installation)

Wajibi harey: Python 3.10 wala a jineɲe tajoo nda Omi kontu.

Da `pipx` go war se kulu:

```sh
pipx install omi-cli
omi --help
```

War ga hin k'a sinji koyne Python goy-dogo kaŋ ga goy ra (virtual environment):

```sh
python -m pip install omi-cli
omi --help
```

Da `omi` lordoo mana duwandi terminaloo ra, guna wala virtual environment ga goy wala `pipx` fondo go war `$PATH` ra.

## War Kontoo Dobuyaŋ (Authentication)

Šintin faaba-koyoo kaŋ ga faaba:

```sh
omi auth login
```

Suuba ka furo browser do wala ka war Omi developer API key daŋ a ra. Furo-doy wo ga saafaloo tugu; ma si a hantum lordey ra kaŋ ga goro terminaloo taariiko ra.

Ka koy doon browser do:

```sh
omi auth login --browser
```

Furo ordinater foo kaŋ terminaloo ga goy a boŋ ra: tabatandiyan zaaboo ga goy nda koy-dogo adresoo. Gan sanni-izey kaŋ yaŋ go bii-dogo boŋ.

Woodin banda, hanseyan nda API duwayan koroši:

```sh
omi auth status
omi auth whoami
```

`status` ga koy-dogo alhaaloo cabe ka gundoo tugu, amma a si a goyoo koroši serveroo ga. `whoami` ga tabatandi ŋwaaray sanba; d'a nka te boori, a ga tabatandi kaŋ gundey ga goy bila nda a cabe war maaɲoo.

Hanseyan ga heenyandi `~/.omi/config.toml` ra. Ma si tira wo zere boro fo se: a ga hin ka gondo gundo tabatandiyaŋ.

## War Alhabarey Korošiyaŋ (Inspection)

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Maaɲe koonu ga hin ka te ceeciyan mana a dumo fo duwa. Goy nda faaba ka suubarey guna lordi kulu ra:

```sh
omi memory list --help
omi action-item list --help
```

## JSON Zaayan nda Mooceliyan (Pagination)

Duniya-mee suubaa `--json` daŋ lordi margoo **jine**:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Lordi jinayoo ga fongiyan 25 jinayey ŋwaaray; a hinkantoo ga 25 kaŋ ga gan ŋwaaray. Moo foo manti gaabandi kulu no (backup). JSON fattaroo ga maaɲe timmey kulu gaabu, baa da bii-dogo taabaloo ga hin k'a kayandi zama a ma cabe boori.

Ka moo foo gaabu tira ra:

```sh
omi --json memory list --limit 25 --offset 0 > fongiyan-moo-1.json
```

Fondo wo ga tira te wala a barmay koy-dogo ra. Guna kaŋ lordoo ben ka boori jina ka goy nda a gundo harey. Firrey ga hantumandi firri fattayan dogoo ra (stderr); tira koonu manti alhabar si no. Tira kaŋ fatta ga hin ka gondo war boŋ alhabar: jine k'a gaabu kanga.

## Ka Fatta Kontoo ra (Logout)

```sh
omi auth logout
```

Lordi wo ga gundo harey kaŋ gaabandi koy-dogo ra kaa. Ka saafaloo kaa serveroo ga, goy nda developer key korošiyan war kontoo ra.

Lordi tana nda suubari tana yaŋ se, guna [Turanci tira beeroo](../README.md) nda `omi --help`.
