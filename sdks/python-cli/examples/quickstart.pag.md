# Saray Unonan Kundang ed omi-cli

Ipaliwawa na sayan panangiwanwan iray unonan gangan (commands) ed salitan Pangasinan. Saray ngaran na gangan tan mensahe na programa so maniansia ed Ingles. Saray alimbawa na pantepet (query) ya nipapanengneng dia et ag manguman ed saray memorya (memories), pitongtong (conversations), gawaen (action items), odino saray gagala (goals).

## Pang-instalar ed programa

Saray Nakaukolan: Python 3.10 odino mas balon bersyon tan sakey ya Omi account.

No walay `pipx` ya aka-instalar:

```sh
pipx install omi-cli
omi --help
```

Bilang alternatibo, sarag mon i-instalar iya ed loob na aktibon Python virtual environment:

```sh
python -m pip install omi-cli
omi --help
```

No ag naromog na terminal so `omi`, seguraen ya aktibo so virtual environment odino say direktorio ya pangiikana na `pipx` ed saray executable files et walad `$PATH` mo.

## Pikiarap ed account mo

Gapoan so interactive assistant:

```sh
omi auth login
```

Manpili ed baetan na pan-log in panamegley na browser odino say opsyon ya i-paste so sakey ya Omi developer API key. Yamot na interactive input so key; paliisan so pansulat ed saya ed sakey ya gangan ya manansia ed awaran (history) na terminal.

Piyan direktan onla ed browser:

```sh
omi auth login --browser
```

Man-log in ed parehon kompyuter ya pambabatikay terminal: manguusar so ebat na authentication na lokal ya address. Tumboken iray instruksyon ed screen.

Kayari to ya, usisaen so configuration tan access ed API:

```sh
omi auth status
omi auth whoami
```

Ipapanengneng na `status` so lokal ya kipapasen tan iyamot toy sekreto, balet agto uusisaen so validity ed server. Say `whoami` et manggagawa na sakey ya authenticated ya kerew; no maong so pansumpal, papaneknekan toy pambatik na saray kredensyal, ya ag kaukolan ya ipanengneng so ngaran mo.

Aka-save so configuration bilang default ed `~/.omi/config.toml`. Ag-ipupusay odino ipapasa iyan file: nayarin walay karga ton kompidensyal ya kredensyal mo.

## Pangusisa ed saray datam

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Say andiay-kargan listaan et nayarin mankabaliksan labat ya anggapoy bengatlan mitunos ed tepet. Usaren so tulong piyan naamtaan iray filter na balang gangan:

```sh
omi memory list --help
omi action-item list --help
```

## Pakaala na JSON tan pan-navigate ed saray bolong (Pagination)

Iyan so sankamundoan ya opsyon ya `--json` **sakbay** na grupo na gangan:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Kerewen na unonan gangan so unonan 25 ya memorya; say mikadua, say ontumbok ya 25. Say sakey ya bolong et aliwan sigpot ya backup. Titiponen na output na JSON so interon identifiers, legan ya nayarin pakitien na saray lamisaan ed screen iraya piyan nipanengneng.

Piyan i-save so sakey ya bolong diad sakey ya file:

```sh
omi --json memory list --limit 25 --offset 0 > saray-memorya-bolong-1.json
```

Iyan panangipawil et manggagawa odino mangisalalat ed lokal ya file. Seguraen ya maong so pansumpal na gangan sakbay ya usaren so karga to. Saray lingo (errors) et nisusulat ed error output (stderr); say andiay-kargan file et aliwan garantiya ya anggapoy data. Say na-export ya file et nayarin walay karga ton personal ya impormasyon: tiponan iyan pribado.

## Pan-logout ed account (Logout)

```sh
omi auth logout
```

Ekalen na sayan gangan iray kredensyal ya aka-save diad lokal ya paraan. Piyan paandien so bili na sakey ya key ed server, usaren so panangimaton na developer key ed account mo.

Para ed arom nran gangan tan mas aralem ya opsyon, nengnengen so [manunan panangiwanwan ed Ingles](../README.md) tan `omi --help`.
