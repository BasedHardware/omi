# Umuna a Gabay iti omi-cli

Ipalawag daytoy a gabay dagiti umuna a bilin (commands) iti pagsasao nga Ilokano (Ilocano). Dagiti nagan ti bilin ken mensahe ti programa ket agtalinaed iti Ingles. Dagiti pagarigan ti panagsukisok a naipakita ditoy ket saan a mangbaliw kadagiti lagipmo (memories), saritaan (conversations), aramiden (action items), wenno dagiti gannuat (goals).

## Panang-instalar iti programa

Dagiti Kasapulan: Python 3.10 wenno mas baro a bersion ken maysa nga Omi account.

No adda `pipx` a na-instalar:

```sh
pipx install omi-cli
omi --help
```

Mabalin pay nga i-instalar daytoy iti uneg ti maysa nga aktibo a Python virtual environment:

```sh
python -m pip install omi-cli
omi --help
```

No saan a masarakan ti terminal ti `omi`, siguraduen nga aktibo ti virtual environment wenno ti direktorio a pagikabilan ti `pipx` ket adda iti `$PATH` mo.

## Panangikonektar iti account-mo

Irugi ti interactive assistant:

```sh
omi auth login
```

Agpili iti panag-login babaen ti browser wenno ti opsion nga i-paste ti Omi developer API key. Ilemmeng ti interactive input ti key; liklikan ti panangisurat iti daytoy iti bilin a mabati iti pakasaritaan ti terminal.

Tapno mapan a direkta iti browser:

```sh
omi auth login --browser
```

Ag-login iti isu met laeng a kompiuter a pagtartarayen ti terminal: agus-usar ti sungbat ti authentication iti lokal nga address. Sumurot kadagiti pammilin iti iskrin.

Kalpasan dayta, pasingkedan ti configuration ken panag-access iti API:

```sh
omi auth status
omi auth whoami
```

Ipakita ti `status` ti lokal a kasasaad ken ilemmengna ti sekreto, ngem saan nga amirisenda ti validity iti server. Ti `whoami` ket mangaramid iti authenticated a kiddaw; no naballigi, patalgedanna nga agtigtignay dagiti kredensial, a saan a kasapulan nga iparang ti naganmo.

Nakaisagana ti configuration kas default iti `~/.omi/config.toml`. Saan nga ibinglay daytoy a file: mabalin nga adda linaon daytoy a kompidensial a kredensial.

## Panangsukimat kadagiti datam

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Ti awan linaonna a listaan ket mabalin a kayatna laeng sawen nga awan dagiti banag a maitunos iti panagsukisok. Usaren ti tulong tapno maduktalan dagiti filter iti tunggal bilin:

```sh
omi memory list --help
omi action-item list --help
```

## Panangala iti JSON ken panag-navigate kadagiti panid (Pagination)

Ikabil ti sangalubongan nga opsion a `--json` **sakbay** ti grupo ti bilin:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Kiddawen ti umuna a bilin ti umuna a 25 a lagip; ti maikadua, ti sumaruno a 25. Ti maysa a panid ket saan a kompleto a backup. Ipreserba ti output ti JSON dagiti intero nga identifier, idinto a mabalin a pabassiten dagiti lamisaan iti iskrin daytoy para iti panangiparang.

Tapno maidulin ti maysa a panid iti maysa a file:

```sh
omi --json memory list --limit 25 --offset 0 > dagiti-lagip-panid-1.json
```

Daytoy a panangiturong ket mangpartuat wenno mangsukat iti lokal a file. Siguraduen a naballigi a nalpas ti bilin sakbay nga usaren ti linaonna. Dagiti biddut (errors) ket maisurat iti error output (stderr); ti awan linaonna a file ket saan a pammaneknek nga awan ti data. Ti na-export a file ket mabalin nga addaan personal nga impormasion: pagtalinaeden a pribado.

## Panag-logout iti account

```sh
omi auth logout
```

Ikkaten daytoy a bilin dagiti kredensial a naidulin iti lokal a wagas. Tapno pawangwangen ti maysa a key iti server, usaren ti panagtarawidwid iti developer key iti bukodmo nga account.

Para iti dadduma pay a bilin ken ad-adu pay nga opsion, kitaen ti [kangrunaan a pammilin iti Ingles](../README.md) ken `omi --help`.
