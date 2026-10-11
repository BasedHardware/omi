# Edimädseq sammuq omi-cli-ga

Seo oppus seletäs omi-cli edimädseq käskyq (commands) võro keelen. Käsküde nimeq ja programmi teedüsseq jääväq inglüse keelen. Siin näüdätüq otsmisnäütüseq ei muuda su mälu (memories), vestluisi (conversations), tallitusi (action items) ega sihtmärke (goals).

## Paigaldaminõ

Tarvilinõ: Python 3.10 vai vahtsõmb, ja Omi konto.

Ku sul om `pipx`:

```sh
pipx install omi-cli
omi --help
```

Võit paigaldadaq tuu ka aktiivsõhe Python-virtuaalümbrehe:

```sh
python -m pip install omi-cli
omi --help
```

Ku terminal ei löüdäq `omi`, tõista, et virtuaalümbreq om tüün vai et `pipx` kaust om `$PATH`-in.

## Konto ühendämine

Alostaq interaktiivnõ abimees:

```sh
omi auth login
```

Valiq sisseminek brauseri kaudu vai Omi developer API võtmõ liimitsemise vaihõl. Interaktiivnõ sisestus peidäq võtmõ ärq; vältäq tuu kirjutamist käske, miä jääs terminali aoluu.

Mineq otse brauserihe:

```sh
omi auth login --browser
```

Logiq sisse samal huunõl ku terminal: autentimiisvastus lätt paigalidsõhe aadressihe. Järgi ekraani pääl olõvit juhatuisi.

Päält tuud tõistaq konfiguratsiooni ja API pääsü:

```sh
omi auth status
omi auth whoami
```

`status` näütäs paigalist saisu ja peidäq salajatsu, a ei tõistaq kehtüvüst serverin. `whoami` tege autenditü küsümüse; ku tuu läts kõrda, om selge, et tunnusõq töütäseq, nime näütämildäq.

Konfiguratsioon pandaq perisväärtüse perrä `~/.omi/config.toml`-i. Ärq jagaq tuud faili: tuun või ollaq peidetüq tunnusõq.

## Oma andmitõ kaeminõ

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Tühi nimekiri tähendäs hariligult lihtsäq tuud, et midäki ei vasta otsmisõlõ. Pruugi abi, et löüdäq egä käsu filtreq:

```sh
omi memory list --help
omi action-item list --help
```

## JSON ja leheq

Pandaq ülene opitsioon `--json` **innembide** käsküq rühmäst:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Edimäne käsk küsüs edimäist 25 mälestä; tõõnõ küsüs 25, miä tulõvaq perrä. Üts leht olõ-õi täüstelik kopio. JSON-väländ pruuk hoidaq terviknumbriq, a ekraani pääl olevaq tabõliq võivaq nuuq lühendäq.

Lehe tallitaminõ faili:

```sh
omi --json memory list --limit 25 --offset 0 > mälu-leht-1.json
```

Seo ümbrejuhtminõ luu vai kirjotas üle paigalidsõ faili. Tõistaq, et käsk om lõpõtõt, inne ku sisu pruugit. Vead kirjotõdasõq viga-väländihe (stderr); tühi fail olõ-õi tõõstus, et andmit ei olõq. Ekspordit failin või ollaq erälelist teedüst: hoiaq tuud privat.

## Väljaminek

```sh
omi auth logout
```

Seo käsk kistutas paigalidsõhe tallitõduq tunnusõq. Et võtmõt serverin kehtüstüs ärq tetäq, pruugiq developer-võtmiõ haldamist uman konton.

Inämbüisi käskü ja opitsioonõ kotsilõ kae [pääoppust inglüse keelen](../README.md) ja `omi --help`.
