# omi-cli-mut aallartinneq

Una ilitsersuut Kalaallisut peqqussutinik siullernik takutitsivoq. Peqqussutit aqqi aamma atortut nalunaarutaat Tuluttut suli ingerlaannarput. Maani atuffassissutit takutinneqartut eqqaamasannik, oqaloqatigiissutinik, suliassanik imaluunniit anguniakkanik allanngortitsinngillat.

## Ilitsersuut atorlugu ikkussineq

Piumasaqaatit: Python 3.10 imaluunniit nutaanerusoq aamma Omi-mi konto.

> Malugiuk: PyPI-mi poortukkap aqqa tassaavoq **`omi-cli`**, kisianni ikkussereernermi peqqussut ingerlanneqartoq tassaalluni **`omi`**. PyPI-mi poortugaq allaanerusoq attuumassuteqanngitsoq `omi`-mik atilik pigineqarpoq — taanna ikkuteqinagu.

`pipx` ikkussimappat:

```sh
pipx install omi-cli
omi --help
```

Aappaatigut, Pythonip ingerlatsiviani pimoorussamik atorneqartumi:

```sh
python -m pip install omi-cli
omi --help
```

Terminalip `omi` nassaarinngippagu, ingerlatsiviup atuunnera imaluunniit `pipx`-ip toqqorsivia illit `PATH`-inniinnera qulakkeeruk.

## Kontunnik atassusiigit

Attaveqaqatigiinnermut ikiorti aallartiguk:

```sh
omi auth login
```

Qarasaasiakkut ammartakkakkut iserneq toqqaruk, imaluunniit Omi-mut ineriartortitsisup API matuersaataanik ikkussineq toqqaruk. Aaqqiissuussap matuersaat isertortuutippaa; terminalip oqaluttuarisaanerani matuersaat allaqinagu.

Toqqaannartumik qarasaasiakkut iserniaraanni:

```sh
omi auth login --browser
```

Terminalip ingerlanneqarfiani qarasaasiap taassuma iluani iserneq naammassiuk, tassami uppernarsaat najukkami adressimut utertinneqartarpoq. Skærmimi ilitsersuutit malikkit.

Taassuma kingorna aaqqissuussineq aamma API-mut isersinnaaneq misissoqqissaakkit:

```sh
omi auth status
omi auth whoami
```

`status`-ip najukkami pissutsit takutippai isertukkallu isertuullugit, kisianni serverimut misissuisanngilaq. `whoami`-p noqqaassut akuerisaq nassitsissutigaa; iluatsinnerata takutippaa ilisarnaatitit eqqortumik ingerlasut.

Aaqqissuussineq `~/.omi/config.toml`-imi toqqorneqartarpoq. Una fiili allanut siammarseqinagu, tassaniippummi illit ilisarnaatitit nammineq pigisatit.

## Paasissutisaatitit takukkit

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Allattorsimaffik imaqanngitsoq taamaallaat isumaqarsinnaavoq noqqaassummut naapertuuttunik nassaartoqanngitsoq. Peqqussutip killeqarfiinik paasisaqarniaraanni ikiorneqarfissaq takuuk:

```sh
omi memory list --help
omi action-item list --help
```

## JSON pissarsiariuk aamma quppernerit ammakkit

Tamanut atuuttoq `--json` peqqussutit **siornatigut** inissiguk:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Peqqussutit siulliup allattukkat siulliit 25-t piumasarpai; tulliata tulliuttut 25-t piumasaralugit. Taamaattumik qupperneq ataaseq assilineqarneq tamakkiisuunngilaq. JSON-ip ilisarnaatit tamakkiisut toqqortarai, tabelilli naalisarsinnaallugit.

Qupperneq ataaseq fiilimi toqqorumallugu:

```sh
omi --json memory list --limit 25 --offset 0 > eqqaamasat-qupperneq-1.json
```

Uuma ingerlateqqinnerata najukkami fiili pilersittarpaa imaluunniit taarsertarlugu. Imaa atunnginnerani peqqussutip iluatsissimanera qulakkeeruk. Kukkussutit stderrimut allanneqartarput; fiili imaqanngitsoq paasissutissanik peqannginneranik uppernarsaataanngilaq. Fiilimi toqqorneqartumi paasissutissat nammineq pigisat ilaasinnaapput: isertuuguk.

## Anigit (Log out)

```sh
omi auth logout
```

Peqqussutip uuma najukkami ilisarnaatit toqqorneqarsimasut peersittarpai. Serverimi matuersaat unitsikkumallugu kontunni ineriartortitsisut matuersaataannik aqutsineq atoruk.

Peqqussutit allat aamma periarfissat qaffasinnerusut pillugit Tuluttut ilitsersuut pingaarneq takuuk:
[../README.md](../README.md) aamma `omi --help`.
