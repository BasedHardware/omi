# Kobanda Noki na omi-cli

Mokanda oyo ya litambwisi elimboli mitindo ya yambo na monoko ya Lingála. Bakombo ya mitindo mpe basango ya manaka etikalaka na Lingelesi. Bandakisa ya mituna (query) oyo ezali awa ebongolaka te makanisi na yo (memories), masolo (conversations), misala ya kosala (action items), to mikano na yo (goals).

## Kotia manaka na ordinatere (Installation)

Masengami: Python 3.10 to version ya sika koleka elongo na konte ya Omi.

Soki osili kotia `pipx`:

```sh
pipx install omi-cli
omi --help
```

Na lolenge mosusu, okoki kotia yango na kati ya virtual environment ya Python oyo ezali kosala:

```sh
python -m pip install omi-cli
omi --help
```

Soki terminal ezali komona `omi` te, tala malamu soki virtual environment ezali kosala to soki dosiye epai wapi `pipx` ebiisaka bafayilo na yango ezali na kati ya `$PATH` na yo.

## Kokangisa konte na yo (Authentication)

Banda mosungi ya kosolola (interactive assistant):

```sh
omi auth login
```

Pona kokota na nzela ya navigateur (browser) to kopakola fungola ya developer API ya Omi. Lolenge oyo ebombaka fungola; kokoma fungola te na motindo oyo ekotikala na lisolo ya terminal.

Mpo na kokende mbala moko na navigateur:

```sh
omi auth login --browser
```

Kota na ordinatere ya ndenge moko na oyo terminal ezali kosala: eyano ya ndingisa esalelaka adresi ya mboka (local address). Landa malako oyo ezali komonana na ecran.

Na nsima, tala lolenge ya kobongisa mpe bokoti na API:

```sh
omi auth status
omi auth whoami
```

`status` ezali komonisa ezalela ya esika mpe ebombaka sekele, kasi etalaka te bosembo na yango na sevele. `whoami` etindaka esengi oyo endimami; soki elongi, endimisaka ete mikanda mizali kosala malamu kozanga kosenga komonisa kombo na yo.

Bongiseli ebombamaka mbala mingi na `~/.omi/config.toml`. Kokabola fayilo oyo te mpo ekoki kozala na basekele na yo ya mosala.

## Kotala makambo na yo (Data)

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Molongo oyo ezangi eloko ekoki kolimbola kaka ete eloko moko te ekokani na motuna na yo. Salela lisungi mpo na komona biponeli na motindo moko na moko:

```sh
omi memory list --help
omi action-item list --help
```

## Kozwa JSON mpe kotambola na nkasa (Pagination)

Tia eponeli ya mokili mobimba `--json` **liboso** ya etuluku ya motindo:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Motindo ya yambo esengaka makanisi 25 ya yambo; ya mibale, 25 oyo elandi. Lokasa moko ezali te mobeko mobimba (backup). Ebimeli ya JSON ebatelaka banzela nyonso ya bilembo, nzokande bamesa na ecran ekoki kokata yango mikuse mpo na komonana malamu.

Mpo na kobomba lokasa moko na fayilo:

```sh
omi --json memory list --limit 25 --offset 0 > makanisi-lokasa-1.json
```

Bobongoli oyo esalaka to ezwaka esika ya fayilo ya mboka. Yeba malamu soki motindo esili malamu liboso ya kosalela makambo ezali na kati. Mabunga ekomamaka na esika ya kobimisa mabunga (stderr); fayilo ya pamba ezali te elembo ete makambo ezali te. Fayilo oyo ebimisami ekoki kozala na bansango ya yo moko: batela yango na kimia mpe sekele.

## Kobima na konte (Logout)

```sh
omi auth logout
```

Motindo oyo elongolaka mikanda oyo ebombami na esika oyo ozali. Mpo na kolongola fungola na sevele, salela botambwisi ya bafungola ya developer na konte na yo.

Mpo na mitindo misusu mpe maponi ya mozindo, tala [litambwisi monene na Lingelesi](../README.md) mpe `omi --help`.
