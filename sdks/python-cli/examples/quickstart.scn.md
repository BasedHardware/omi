# Primi passi cu omi-cli

Sta guida ammustra li primi cumanni di omi-cli 'n sicilianu. Li noma dî cumanni e li missaggi dû prugramma rìstanu 'n ngrisi. L'esempi di sta guida nun càncianu li to mimurîi, li to cunversazzioni, li to azzioni o li to ubbiettivi.

## Nstallazzioni

Ti servi Python 3.10 o cchiù novu, e un cuntu Omi.

Si `pipx` è già nstallatu:

```sh
pipx install omi-cli
omi --help
```

Sinnò, nstallallu 'n un ambient virtuali Python attivu:

```sh
python -m pip install omi-cli
omi --help
```

Si lu terminali nun trova `omi`, talìa si l'ambient virtuali è attivu o si la cartedda di pipx s'attrova ntô `$PATH`.

## Cunnèttiri lu cuntu

Accumenna lu magu di accessu ntirazzioni:

```sh
omi auth login
```

Poi' scegghiri d'accèdiri cu lu browser o d'incuddari na chiavi API di sviluppaturi Omi. L'accessu ntirazzioni ammuccia la to chiavi; sta attentu e nun la lassari ntâ cronuluggìa dû to terminali.

Pi accèdiri direttamenti cu lu browser:

```sh
omi auth login --browser
```

Accedi supra lu stissu computer unni curri lu terminali: la risposta d'autorizzazzioni usa n'ndirizzu lucali. Sèqui li struzzioni supra lu schirmu.

Controlla ora la cunfigurazzioni e la chiavi API:

```sh
omi auth status
omi auth whoami
```

`status` ammustra lu statu lucali e ammuccia li sigreti, ma nun controlla cu lu server. `whoami` fa na dumanna autorizzata; si riesci, cunferma ca la to autorizzazzioni funziona, ma nun ammustra lu to nomu.

La cunfigurazzioni s'attrova ntô `~/.omi/config.toml`. Nun spàrtiri stu file: pò cuntèniri sigreti d'accessu.

## Esplurari li dati

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Na lista vacanti pò significari semplicimenti ca nun cc'è nuddu datu ca currispunni â dumanna. Pi mpàrari li filtri di ogni cumannu, taliìa l'aiutu:

```sh
omi memory list --help
omi action-item list --help
```

## Output JSON e paginazzioni

Metti l'opzioni glubbali `--json` **prima** dû gruppu di cumanni:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Lu primu cumannu pigghia li primi 25 mimurîi; lu sicunnu pigghia li 25 appressu. Na pàggina sula spissu nun è china. L'output JSON manteni tutti l'identificaturi, mentri li tabelli supra lu schirmu spissu li accorcianu.

Pi scrìviri na pàggina nta un file:

```sh
omi --json memory list --limit 25 --offset 0 > mimurîi-pàggina-1.json
```

La ridirezzioni cria o scrivi supra a un file lucali. Controlla ca lu cumannu appi successu prima d'usari lu cuntinutu. Li errori vannu a stderr; un file vacanti nun significa ca nun cc'è datu. Li file esportati ponnu cuntèniri nfurmazzioni privata: sarvàlili cu cura.

## Nisciuta

```sh
omi auth logout
```

Stu cumannu rimovi l'autorizzazzioni lucali sarvata. Pi rivucari la chiavi ntô server, usa la gistioni dî chiavi di sviluppaturi ntô to cuntu.

Pi àutri cumanni e opzioni avanzati, taliìa la [Guida principali ngrisi](../README.md) e `omi --help`.
