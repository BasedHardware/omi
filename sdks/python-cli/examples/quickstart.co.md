# I primi passi cù omi-cli

Sta guida spiega i primi cumandi (commands) di omi-cli in corsu. I nomi di i cumandi è i messaghji di u prugramma fermanu in inglese. L'esempii di ricerca mustrati quì ùn cambianu micca e vostre memorie (memories), e vostre conversazioni (conversations), e vostre azzioni (action items) o i vostri scopi (goals).

## Installazione

Ci vole: Python 3.10 o più recente, è un contu Omi.

S'è voi avete `pipx`:

```sh
pipx install omi-cli
omi --help
```

Pudete ancu installallu in un ambiente virtuale Python attivu:

```sh
python -m pip install omi-cli
omi --help
```

S'è u terminale ùn trova micca `omi`, assicuratevi chì l'ambiente virtuale sia attivu o chì a cartella di `pipx` sia in `$PATH`.

## Cunnette u vostru contu

Cuminciate l'assistente interattivu:

```sh
omi auth login
```

Sceglite d'entrà per u navigatore o d'incollà una chjave API di sviluppatore Omi. L'input interattivu piatta a chjave; evitate di a scrive in un cumandu chì serà guardatu in a storia di u terminale.

Per andà direttamente à u navigatore:

```sh
omi auth login --browser
```

Entrate nant'à u listessu urdinatore ch'è u terminale: a risposta d'autenticazione và à l'indirizzu locale. Seguì l'istruzzioni nant'à u screnu.

Dopu, verificate a cunfigurazione è l'accessu API:

```sh
omi auth status
omi auth whoami
```

`status` mostra u statu locale è piatta u sicretu, ma ùn verifica micca a validità nant'à u servitore. `whoami` face una richiesta autenticata; s'è funziona, hè chjaru chì e credenziale funzionanu, senza mustrà u vostru nome.

A cunfigurazione hè salvata per difettu in `~/.omi/config.toml`. Ùn sparte micca stu fugliale: pò cuntene credenziale private.

## Esplurà i vostri dati

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Una lista viota significa spessu solu chì nunda currisponde à a ricerca. Aduprate l'aiutu per truvà i filtri di ogni cumandu:

```sh
omi memory list --help
omi action-item list --help
```

## JSON è pagine

Mettite l'opzione globale `--json` **nanzu** à u gruppu di cumandi:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

U primu cumandu dumanda e prime 25 memorie; u secondu e 25 chì seguitanu. Una pagina sola ùn hè micca una copia cumpleta. L'output JSON cunserva i numeri interi, mentre chì e tavule nant'à u screnu ponu accurscià li.

Per salvà una pagina in un fugliale:

```sh
omi --json memory list --limit 25 --offset 0 > memorie-pagina-1.json
```

Sta ridirezione crea o riscrive un fugliale locale. Assicuratevi chì u cumandu sia finitu nanzu d'utilizà u cuntenutu. L'errori sò scritti in l'output d'errone (stderr); un fugliale viotu ùn hè micca una prova chì ùn ci sia dati. Un fugliale esportatu pò cuntene infurmazioni persunale: guardate lu privatu.

## Disconnettesi

```sh
omi auth logout
```

Stu cumandu cancella e credenziale salvate in locale. Per invalidà una chjave nant'à u servitore, aduprate a gestione di e chjave di sviluppatore in u vostru contu.

Per più cumandi è opzioni, fighjate a [guida principale in inglese](../README.md) è `omi --help`.
