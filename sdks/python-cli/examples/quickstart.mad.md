# Molaî Ghâlis ngangghuy omi-cli

Pandhuwân panèka ajellasâghi parèntah-parèntah dhasar dâlem bhâsa Madhurâ (Basa Madhurâ). Nyama parèntah sareng pessen dâri program pagghun ngangghuy bhâsa Énggrès. Conto parèksan (query) è bâbâ panèka ta' ngobâ èng-ghéténgan (memories), carèta (conversations), lalakon (action items), otabâ tojjhuwân (goals) panjhennengngan.

## Masang program

Sarattâ: Python 3.10 otabâ vèrsi sé lebbi anyar sareng akun Omi.

Manabi panjhennengngan ampon masang `pipx`:

```sh
pipx install omi-cli
omi --help
```

Mènangka pèleyan laén, panjhennengngan sèksek masang è dâlem virtual environment Python sé ghi' aktif:

```sh
python -m pip install omi-cli
omi --help
```

Manabi terminal ta' nemmo `omi`, pastèyâghi virtual environment ampon aktif otabâ folder éksékusi dâri `pipx` ampon maso' dâlem `$PATH` panjhennengngan.

## Sambhungngaghi akun panjhennengngan

Jalannaghi asisten interaktif:

```sh
omi auth login
```

Pélé maso' lébât browser otabâ tèmpèl konco' API pamekar Omi. Input interaktif nyamana nyapora konco'; jhâ' noles konco' è dâlem parèntah sé bhâkal ékatot dâlem riwâyât terminal.

Kaangghuy langsung ngangghuy browser:

```sh
omi auth login --browser
```

Maso' è komputer sé padâ sareng terminal sé éjhâlannaghi: jhâwâbhân auténtikasi ngangghuy alâmat lokal. Toro' pitudhuh è lâyar.

Samponna ghenèka, parèksa konfigurasi sareng aksès API:

```sh
omi auth status
omi auth whoami
```

`status` nembhângngaghi kabâdâ'an lokal sareng nyapora raséya, namong ta' marèksa validitasna è server. `whoami` makérem pamondhut sé ampon éauténtikasi; manabi ahasél, panèka muktèyâghi jhâ' krédénsial lalakon kalabân saé ta' parlo nembhângngaghi nyamana panjhennengngan.

Sacara baku konfigurasi ésimpen è `~/.omi/config.toml`. Jhâ' bagi berkas panèka amargi sèksek ngandhung krédénsial raséya panjhennengngan.

## Marèksa data panjhennengngan

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Daftar sé kosong bésa molaî coma artena sobung bhârang sé cocok sareng panyaring. Angghuy bantoan kaangghuy ngoladi panyaring è bân-sabbân parèntah:

```sh
omi memory list --help
omi action-item list --help
```

## Ngallé JSON sareng napigasi kacha (Pagination)

Pabâdâ péléyan global `--json` **sabellunna** rombongan parèntah:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Parèntah kapèng séttong mondhut 25 èng-ghéténgan dâ'-adâ'; parèntah kapèng dhuwâ', 25 salanjutna. Sakacha béné' cadhangan sé ghenna'. Kaluwaran JSON nahan identifier ghenna', namong tabèl è lâyar kéngéng pamondhut kéné' kaangghuy nembhângngaghi.

Kaangghuy nyoppan sakacha dâlem berkas:

```sh
omi --json memory list --limit 25 --offset 0 > eng-ghetengan-kacha-1.json
```

Parobâ'an panèka aghâbây otabâ ngallé berkas lokal. Pastèyâghi parèntah ampon marè kalabân bhâghus sabellunna ngangghuy ésséna. Kasala'an étoles dâlem output kasala'an (stderr); berkas sé kosong béné' jaminan jhâ' sobung data. Berkas sé éékspor sèksek ngandhung katerrangan pribadi: simpen kalabân aman.

## Kaluwar dâri akun (Logout)

```sh
omi auth logout
```

Parèntah panèka mahos krédénsial sé ésimpen è lokal. Kaangghuy mbatalaghi konco' è server, angghuy pangaturan konco' pamekar è akun panjhennengngan.

Kaangghuy parèntah laén sareng péléyan sé lebbi ghenna', oladi [pandhuwân otama dâlem bhâsa Énggrès](../README.md) sareng `omi --help`.
