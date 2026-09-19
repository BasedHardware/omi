# Primi passi cù omi-cli

Sta guida spiega i primi cumandi in lingua corsa. I nomi di i cumandi è i missaghji
di u prugramma fermanu in inglesu. L'esempii di dumande quì ùn mudificheranu micca
i vostri ricordi, e vostre cunversazione, i vostri compiti o i vostri scopi.

## Stallazione di u prugramma

Requisiti: Python 3.10 o più recente è un contu Omi.

S'è vo avete `pipx` stallatu:

```sh
pipx install omi-cli
omi --help
```

Hè ancu pussibule di stallallu in un ambiente virtuale (virtual environment) attivu
in Python:

```sh
python -m pip install omi-cli
omi --help
```

S'è u terminale ùn trova micca `omi`, verificate chì l'ambiente virtuale sia attivu
o chì u cartulare induve `pipx` mette i fugliali eseguibili sia in a vostra variabile `PATH`.

## Cunnette u vostru contu

Lanciate l'assistente interattivu:

```sh
omi auth login
```

Sceglite d'identificavvi via u navigatore (browser) o incollate una chjave API di
sviluppatore Omi. L'inserimentu interattivu piatta a chjave; evitate di scriveila
in un cumandu chì fermerebbe in a storia di u terminale.

Per andà direttamente à u navigatore:

```sh
omi auth login --browser
```

Cunnettatevi annantu à u listessu urdinatore induve u terminale hè in funzione: a
risposta d'autentificazione usa un indirizzu lucale. Seguitate l'istruzzioni nantu à u screnu.

Dopu, verificate a cunfigurazione è l'accessu à l'API:

```sh
omi auth status
omi auth whoami
```

`status` mostra u statu lucale è piatta u secretu, ma ùn verifica micca a validità
nantu à u servitore. `whoami` manda una dumanda autentificata; s'ella riesce,
cunferma chì e credenziali funzionanu, senza mustrà per forza u vostru nome.

A cunfigurazione hè salvata di regula in `~/.omi/config.toml`. Ùn sparte micca stu
fugliale: pò cuntene i vostri dati d'accessu secreti.

## Esplurà i vostri dati

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Una lista viota pò significà simpliciamente chì nisun elementu currisponde à a ricerca.
Aduprate l'aiutu per vede i filtri dispunibili per ogni cumandu:

```sh
omi memory list --help
omi action-item list --help
```

## Scaricà JSON è navigà trà e pagine

Mettite l'opzione glubale `--json` **davanti** à u gruppu di cumandi:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

U primu cumandu dumanda i primi 25 ricordi; u sicondu i 25 seguenti. Una sola pagina
ùn hè micca una copia di salvezza cumpleta (backup). U furmatu JSON cunserva l'identificatori
cumpleti, mentre chì e tavule nantu à u screnu ponu accurtalli.

Per salvà una pagina in un fugliale:

```sh
omi --json memory list --limit 25 --offset 0 > ricordi-pagina-1.json
```

Sta ridirezzione crea o rimpiazza u fugliale lucale. Assicuratevi chì u cumandu
sia compiu senza errori prima d'aduprà u cuntenutu. L'errori sò scritti in u flussu
d'errore (stderr); un fugliale viotu ùn garantisce micca chì ùn ci sia micca dati. U fugliale
esportatu pò cuntene infurmazioni persunali: tenitelu cunfidenziale.

## Scunnessione (Logout)

```sh
omi auth logout
```

Stu cumandu cancella e credenziali salvate lucalmente. Per revocà una chjave annantu
à u servitore, aduprate a gestione di e chjave di sviluppatore nantu à u vostru contu.

Per altri cumandi è più opzioni, cunsultate
[a guida principale in inglesu](../README.md) è `omi --help`.
