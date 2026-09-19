# Phau Ntawv Qhia Sai txog omi-cli

Phau ntawv qhia no piav qhia txog cov lus txib (commands) thawj zaug ua lus Hmoob (Hmong) rau `omi-cli`. Cov npe lus txib thiab cov lus qhia los ntawm software tseem yuav yog lus Askiv. Cov qauv tshuaj xyuas uas qhia hauv no yuav tsis hloov koj cov kev nco (memories), kev sib tham (conversations), tej yam yuav tsum tau ua (action items), lossis cov hom phiaj (goals).

## Kev teeb tsa software (Installation)

Yam yuav tsum muaj: Python 3.10 lossis tshiab dua thiab ib tus as-khauj Omi.

Yog tias koj twb muaj `pipx`:

```sh
pipx install omi-cli
omi --help
```

Koj tseem tuaj yeem nruab nws rau hauv ib qho chaw ua haujlwm Python (virtual environment):

```sh
python -m pip install omi-cli
omi --help
```

Yog tias lub davhlau ya nyob twg (terminal) tsis pom cov lus txib `omi`, nco ntsoov xyuas seb lub virtual environment puas tab tom ua haujlwm lossis `pipx` txoj kev puas nyob hauv koj lub `$PATH`.

## Txuas koj tus as-khauj (Authentication)

Pib tus pab cuam sib tham:

```sh
omi auth login
```

Xaiv nkag mus siv lub browser lossis muab koj tus Omi developer API key tso rau hauv. Qhov kev tawm tswv yim no zais tus yuam sij; tsis txhob sau nws rau hauv cov lus txib uas yuav nyob hauv keeb kwm ntawm lub davhlau ya nyob twg.

Mus ncaj nraim rau lub browser:

```sh
omi auth login --browser
```

Nkag mus rau hauv tib lub computer uas lub davhlau ya nyob twg tab tom khiav: cov lus teb txheeb xyuas siv lub chaw nyob hauv zos. Ua raws li cov lus qhia ntawm qhov screen.

Tom qab ntawd, tshawb xyuas qhov teeb tsa thiab kev nkag mus rau API:

```sh
omi auth status
omi auth whoami
```

`status` qhia txog qhov xwm txheej hauv zos thiab zais cov lus zais, tab sis tsis kuaj xyuas nws qhov tseeb ntawm lub server. `whoami` xa ib qho kev thov uas tau lees paub; yog tias ua tiav, nws paub meej tias cov ntaub ntawv pov thawj ua haujlwm yam tsis tas yuav qhia koj lub npe.

Kev teeb tsa feem ntau khaws cia hauv `~/.omi/config.toml`. Tsis txhob faib cov ntaub ntawv no: nws yuav muaj cov ntaub ntawv zais cia.

## Tshuaj xyuas koj cov ntaub ntawv (Inspection)

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Cov npe khoob tsuas yog txhais tau hais tias tsis muaj cov ntaub ntawv phim rau kev tshawb nrhiav. Siv kev pab kom nrhiav tau cov kev xaiv hauv txhua cov lus txib:

```sh
omi memory list --help
omi action-item list --help
```

## Txais JSON thiab Kev Faib Nplooj Ntawv (Pagination)

Tso qhov kev xaiv thoob ntiaj teb `--json` **ua ntej** cov pab pawg lus txib:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Thawj cov lus txib thov thawj 25 lub cim xeeb; qhov thib ob thov 25 tom ntej. Ib nplooj ntawv tsis yog tag nrho cov ntaub ntawv khaws cia (backup). Cov zis JSON khaws tag nrho cov cim npe, txawm hais tias cov lus qhia ntawm lub screen yuav txo qis kom pom tseeb.

Khaws ib nplooj ntawv rau hauv cov ntaub ntawv:

```sh
omi --json memory list --limit 25 --offset 0 > nco-nplooj-1.json
```

Qhov kev hloov pauv no tsim lossis hloov kho cov ntaub ntawv hauv zos. Xyuas kom meej tias cov lus txib ua tiav ua ntej siv cov ntsiab lus. Cov teeb meem raug sau rau hauv cov zis yuam kev (stderr); cov ntaub ntawv khoob tsis txhais hais tias tsis muaj ntaub ntawv. Cov ntaub ntawv xa tawm yuav muaj cov ntaub ntawv ntiag tug: khaws cia kom zoo.

## Tawm ntawm tus as-khauj (Logout)

```sh
omi auth logout
```

Cov lus txib no tshem tawm cov ntaub ntawv pov thawj uas khaws cia hauv zos. Yuav rho tawm tus yuam sij ntawm lub server, siv kev tswj hwm developer key hauv koj tus as-khauj.

Rau lwm cov lus txib thiab cov kev xaiv ntxiv, mus saib [phau ntawv qhia lus Askiv loj](../README.md) thiab `omi --help`.
