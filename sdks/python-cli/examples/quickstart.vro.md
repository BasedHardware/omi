# Edimädseq sammuq omi-cli-gaq

Seo opus seletäs, kuis omi-cli-gaq edimädseq käske tetäq võro keelen. Käske nimed ja programmi teadaandõq jääseq inglüse keelen. Opusõn olõvaq näütüseq ei muudaq su mälehtüisi (memories), vestlusi (conversations), ülesannit (action items) ega eesmärke (goals).

## Paigaldaminõ

Nõudmisõq: Python 3.10 vai vahtsõmb ja Omi konto.

Kui `pipx` om paigaldõt:

```sh
pipx install omi-cli
omi --help
```

Või ka paigaldõq tuu aktiivsõ Pythoni virtuaalitsõ keskkunda:

```sh
python -m pip install omi-cli
omi --help
```

Kui terminal ei löüdäq `omi`, kaeq üle, kas virtuaalnõ keskkund om aktiivnõ vai kas pipx-i kataloog om `$PATH`-in.

## Konto ühendäminõ

Käivüq interaktiivnõ sisselogimisavustaja:

```sh
omi auth login
```

Valiq sisselogiminõ brauserigaq vai liitüq Omi arendaja API-võtme. Interaktiivnõ sisselogiminõ peidäs su võtme; es jätäq tuud terminali aolun.

Otse brauserigaq sisselogimisõs:

```sh
omi auth login --browser
```

Logiq sisse samal puutril, kon terminal tüütäq: autorisatsiooni vastus pruukvaq paigalpäälitsit aadrõssit. Toimiq ekraani juhatuisõ perrä.

Peräst tuud kaeq üle konfiguratsioon ja API-võti:

```sh
omi auth status
omi auth whoami
```

`status` näütäs paigalpäälitsõ olukorra ja peidäs salasõnaq, a ei kontrolli kehtivüst serverin. `whoami` tüütäs autoriseeritü päringu; kui tuu kõrda lätt, kinnütäs tuu, et su sisselogimisandmõq tüütäseq, a ei näütäq su nime.

Konfiguratsioon om hariligult `~/.omi/config.toml`-in. Es jagaq tuud faili edesi: tuun võivaq ollaq sisselogimissalasõnaq.

## Andmitõ kaeminõ

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Tühi nimekiri või tähendäq õks tuud, et andmit ei olõq, miä pängäga kokku lätsüq. Et nätäq, miä filtriq olõmas ommaq, kaeq abi:

```sh
omi memory list --help
omi action-item list --help
```

## JSON-väländ ja lehekülitsemine

Pandaq üldine `--json`-valik **inne** käsürühmä:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Edimäne käsk küsüs edimädseq 25 mälehtüst; tõõnõ küsüs järgmädseq 25. Üts lehekülg ei olõq terve varukoopia. JSON-väländ hoitas kõik identifikaatoriq, a ekraani tabõliq võivaq noid lühendäq kaemise jaos.

Et tallõq üts lehekülg faili:

```sh
omi --json memory list --limit 25 --offset 0 > mälehtüseq-lehekülg-1.json
```

Seo ümbrejuhtiminõ tege üte paigalpäälidse faili vai kirjota tuu üle. Inne ku sisu pruukit, kaeq üle, kas käsk õnnistu. Vead kirotõdas stderr-i; tühi fail ei anna kinnitüst, et andmit olõ-õi. Väljäveetüq failiq võivaq sisaldõq erälelist teedüst: hoiaq nuuq salajan.

## Väljälogiminõ

```sh
omi auth logout
```

Seo käsk kistutas paigalpäälidseq sisselogimisandmõq. Et võtme serverin tühistäq, pruukiq uma konto arendaja-võtmi haldamist.

Tõisi käskö ja laembit valikidõ jaos kaeq [inglüsekiilset pääopust](../README.md) ja `omi --help`.
