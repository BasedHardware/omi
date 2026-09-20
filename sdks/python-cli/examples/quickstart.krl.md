# Enzimäzet azkelet omi-clin kera

Tämä opas ozuttau enzimäzet komandot omi-clil karjalan kielel. Komandoloin nimet da programman viestit ollah anglien kielel. Opas ei muuta sinun muistoja (memories), bes'edöjä (conversations), tehtäviä (action items) eigo tavoittehia (goals).

## Asennus

Vaatimukset: Python 3.10 libo uudempi da Omi-konto.

Jos `pipx` on asennettu:

```sh
pipx install omi-cli
omi --help
```

Vaihtoehtosesti voit asendua sen aktiivizeh Python-virtuualiympäristöh:

```sh
python -m pip install omi-cli
omi --help
```

Jos terminal ei löyä `omi`-komanduo, tarkista, ongo virtuualiympäristö aktiivine libo ongo pipx-katalogu `$PATH`:as.

## Kirjautumine

Avua interaktiivine kirjautumisavustaja:

```sh
omi auth login
```

Valitse kirjautumine brauzeran kauti libo liitä Omi-developer-API-avain. Interaktiivine kirjautumine kätkey sinun avaimen; elä jätä sidä terminalan historieh.

Kirjautumine suoraa brauzeran kauti:

```sh
omi auth login --browser
```

Kirjaudu samal kompjuteral, kudamal terminal ruadau: avtorizatsien vastine käyttäy paikallistu adressua. Noudata ekranan instruktsieloi.

Sendäh tarkista konfiguratsie da API-avain:

```sh
omi auth status
omi auth whoami
```

`status` ozuttau paikallizen tilan da kätkey sekretat, ga ei tarkista kelvollisuutta serveril. `whoami` tutkiu avtorizatsijanke; jos se menestyy, se vahvistau, gu sinun kirjautumistiedot ruatah, a ei ozuta sinun nimeä.

Konfiguratsie on tavallizesti tallattuna `~/.omi/config.toml`:ah. Elä anna tädä failua toizile: siel voi olla kirjautumissekretat.

## Dattoin kaččomine

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Tyhjä listu voi merkitä vaiku sidä, gu ei ole dattoja, kuduat vastatah kyzymykseh. Kačo joga komandan apuh, ku tutustuo käytettävissä olevih filtroih:

```sh
omi memory list --help
omi action-item list --help
```

## JSON-ozutus da sivutus

Pane globaline `--json`-optsie **enne** komandogruppua:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Enzimäine komando kyzyy enzimäzet 25 muistuo; toine kyzyy niidy, kuduat tullah peräh. Yksi sivu ei ole kogonaine varmuuskopio. JSON-ozutus säilyttäy kaikki identifikaattorit, a ekranan taulukot voijah lyhendiä niidy kaččomista varte.

Ku tallendua yksi sivu failah:

```sh
omi --json memory list --limit 25 --offset 0 > muistot-sivu-1.json
```

Tämä kirjuttau paikallizen failun libo panou sen uvvelleh. Enne ku käytät sisällystä, tarkista, gu komando loppui onnistumizeh. Viheet kirjutah stderr:ah; tyhjä failu ei anna garantii, gu dattoja ei ole. Eksportatut failut voijah sisältiä personallizie dattoja: pidä niidy salattuna.

## Uloskirjautumine

```sh
omi auth logout
```

Tämä komando hävittäy paikallizesti tallendetut kirjautumistiedot. Ku peruuttua avaimen serveril, käytä developer-avaimen haldivuo sinun kontos.

Toizih komandoih da laajendettuih optsieloih näh kačo [anglienkielistä piäopastu](../README.md) da `omi --help`.
