# Ding Mumunang Hakbang gamit ing omi-cli

Ipalino na ning gabay a ini ding mumunang utus (commands) king amanu Kapampangan. Ding lagyu da ring utus ampo ding mensahi ning programa manatili lang king Ingles. Ding alimbawa ning pamanyaliksik (query) a makabili keti ela magbayu kareng kekang kaganapan (memories), pami-sabi (conversations), dapat gawan (action items), o ding banta (goals).

## Pamag-instala king programa

Ding Kaylangan: Python 3.10 o mas bayung bersyon ampo metung a Omi account.

Nung atin kang `pipx` a maka-instala:

```sh
pipx install omi-cli
omi --help
```

Malyari mu mu naman i-instala ini kilub ning metung a aktibung Python virtual environment:

```sh
python -m pip install omi-cli
omi --help
```

Nung eya ayakit ning terminal ing `omi`, siguradwan mung aktibu ya ing virtual environment o ing direktoryu nung nukarin bibili ning `pipx` ding executable files atyu king kekang `$PATH`.

## Pamituglung king kekang account

Umpisan ya ing interactive assistant:

```sh
omi auth login
```

Mamili king pilatan ning pamag-login kapamilatan ning browser o ing opsyon a i-paste ing metung a Omi developer API key. Isinup ne ning interactive input ing key; ilagan ing pamanyulat kaniti king utus a mitagan king amlat (history) ning terminal.

Ban taglus-taglus mung munta king browser:

```sh
omi auth login --browser
```

Mag-login king parehung kompyuter nung nukarin ya tatagal ing terminal: gagamit ya ing pakibat ning authentication king metung a lokal a address. Tukyan ding tula king screen.

Kaybat na nini, suryan ing configuration ampo ing pamag-access king API:

```sh
omi auth status
omi auth whoami
```

Ipabalu na ning `status` ing lokal a kabilian at isinup ne ing lihim, oneng eya magsuri king katutwan king server. Ing `whoami` gagawa yang metung a authenticated a pamanyad; nung migtagumpe ya, patutwan na a gagana la ring kredensyal, a alang pamangaylangan a ipakit ing kekang lagyu.

Maka-save ya ing configuration antimong default king `~/.omi/config.toml`. Eme pamye o ipamahagi ing file a ini: mapalyaring atin yang laman a kompidensyal a kredensyal.

## Pamagsuri kareng kekang data

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Ing metung a alang-laman a listahan mapalyaring mangabaldugan ya mu a alang bage a tutugma king pamanyaliksik. Gamitan ing saup ban abalu ding filter ning balang utus:

```sh
omi memory list --help
omi action-item list --help
```

## Pamagkwa king JSON ampo pamag-navigate kareng bulung (Pagination)

Ibili ing pangmalawakang opsyon a `--json` **bayu** ing grupu da ring utus:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Yaduan na ning mumunang utus ding mumunang 25 a kaganapan; ing kadwa, ding tutuking 25. Ing metung a bulung aliwa ya ganap a backup. Sesesen na ning output ning JSON ding mabilug a identifiers, kabang malyari dong pakuyaran da ring lamesa king screen deti para king pamipakit.

Ban mag-save metung a bulung papunta king metung a file:

```sh
omi --json memory list --limit 25 --offset 0 > ding-kaganapan-bulung-1.json
```

Ining pamamilugus maglalang o mamalit yang lokal a file. Siguradwan a tagumpe yang miyari ing utus bayu gamitan ing laman na nini. Ding pamagkamali (errors) masusulat la king error output (stderr); ing metung a alang-laman a file aliwa yang garantiya a alang data. Ing me-export a file mapalyaring atin yang personal a impormasyon: isinup yang pribadu.

## Pamag-logout king account (Logout)

```sh
omi auth logout
```

Lalako na ning utus a ini ding kredensyal a makasimpan king lokal a paralan. Ban ipawalang-bisa ing metung a key king server, gamitan ing pamamahala king developer key king kekang account.

Para kareng aliwang utus ampo mas malalam a opsyon, lawan ing [pun a gabay king Ingles](../README.md) ampo `omi --help`.
