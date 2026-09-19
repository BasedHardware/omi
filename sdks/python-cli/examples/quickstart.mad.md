# Mola\u00ee Gh\u00e2lis ngangghuy omi-cli

Pandhuw\u00e2n pan\u00e8ka ajellas\u00e2ghi par\u00e8ntah-par\u00e8ntah dhasar d\u00e2lem bh\u00e2sa Madhur\u00e2 (Basa Madhur\u00e2). Nyama par\u00e8ntah sareng pessen d\u00e2ri program pagghun ngangghuy bh\u00e2sa \u00c9nggr\u00e8s. Conto par\u00e8ksan (query) \u00e8 b\u00e2b\u00e2 pan\u00e8ka ta' ngob\u00e2 \u00e8ng-gh\u00e9t\u00e9ngan (memories), car\u00e8ta (conversations), lalakon (action items), otab\u00e2 tojjhuw\u00e2n (goals) panjhennengngan.

## Masang program

Saratt\u00e2: Python 3.10 otab\u00e2 v\u00e8rsi s\u00e9 lebbi anyar sareng akun Omi.

Manabi panjhennengngan ampon masang `pipx`:

```sh
pipx install omi-cli
omi --help
```

M\u00e8nangka p\u00e8leyan la\u00e9n, panjhennengngan s\u00e8ksek masang \u00e8 d\u00e2lem virtual environment Python s\u00e9 ghi' aktif:

```sh
python -m pip install omi-cli
omi --help
```

Manabi terminal ta' nemmo `omi`, past\u00e8y\u00e2ghi virtual environment ampon aktif otab\u00e2 folder \u00e9ks\u00e9kusi d\u00e2ri `pipx` ampon maso' d\u00e2lem `$PATH` panjhennengngan.

## Sambhungngaghi akun panjhennengngan

Jalannaghi asisten interaktif:

```sh
omi auth login
```

P\u00e9l\u00e9 maso' l\u00e9b\u00e2t browser otab\u00e2 t\u00e8mp\u00e8l konco' API pamekar Omi. Input interaktif nyamana nyapora konco'; jh\u00e2' noles konco' \u00e8 d\u00e2lem par\u00e8ntah s\u00e9 bh\u00e2kal \u00e9katot d\u00e2lem riw\u00e2y\u00e2t terminal.

Kaangghuy langsung ngangghuy browser:

```sh
omi auth login --browser
```

Maso' \u00e8 komputer s\u00e9 pad\u00e2 sareng terminal s\u00e9 \u00e9jh\u00e2lannaghi: jh\u00e2w\u00e2bh\u00e2n auténtikasi ngangghuy al\u00e2mat lokal. Toro' pitudhuh \u00e8 l\u00e2yar.

Samponna ghen\u00e8ka, par\u00e8ksa konfigurasi sareng aks\u00e8s API:

```sh
omi auth status
omi auth whoami
```

`status` nembh\u00e2ngngaghi kab\u00e2d\u00e2'an lokal sareng nyapora ras\u00e9ya, namong ta' mar\u00e8ksa validitasna \u00e8 server. `whoami` mak\u00e9rem pamondhut s\u00e9 ampon \u00e9aut\u00e9ntikasi; manabi ahas\u00e9l, pan\u00e8ka mukt\u00e8y\u00e2ghi jh\u00e2' kr\u00e9d\u00e9nsial lalakon kalab\u00e2n sa\u00e9 ta' parlo nembh\u00e2ngngaghi nyamana panjhennengngan.

Sacara baku konfigurasi \u00e9simpen \u00e8 `~/.omi/config.toml`. Jh\u00e2' bagi berkas pan\u00e8ka amargi s\u00e8ksek ngandhung kr\u00e9d\u00e9nsial ras\u00e9ya panjhennengngan.

## Mar\u00e8ksa data panjhennengngan

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Daftar s\u00e9 kosong b\u00e9sa mola\u00ee coma artena sobung bh\u00e2rang s\u00e9 cocok sareng panyaring. Angghuy bantoan kaangghuy ngoladi panyaring \u00e8 b\u00e2n-sabb\u00e2n par\u00e8ntah:

```sh
omi memory list --help
omi action-item list --help
```

## Ngall\u00e9 JSON sareng napigasi kacha (Pagination)

Pab\u00e2d\u00e2 p\u00e9l\u00e9yan global `--json` **sabellunna** rombongan par\u00e8ntah:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Par\u00e8ntah kap\u00e8ng s\u00e9ttong mondhut 25 \u00e8ng-gh\u00e9t\u00e9ngan d\u00e2'-ad\u00e2'; par\u00e8ntah kap\u00e8ng dhuw\u00e2', 25 salanjutna. Sakacha b\u00e9n\u00e9' cadhangan s\u00e9 ghenna'. Kaluwaran JSON nahan identifier ghenna', namong tab\u00e8l \u00e8 l\u00e2yar k\u00e9ng\u00e9ng pamondhut k\u00e9n\u00e9' kaangghuy nembh\u00e2ngngaghi.

Kaangghuy nyoppan sakacha d\u00e2lem berkas:

```sh
omi --json memory list --limit 25 --offset 0 > eng-ghetengan-kacha-1.json
```

Parob\u00e2'an pan\u00e8ka agh\u00e2b\u00e2y otab\u00e2 ngall\u00e9 berkas lokal. Past\u00e8y\u00e2ghi par\u00e8ntah ampon mar\u00e8 kalab\u00e2n bh\u00e2ghus sabellunna ngangghuy \u00e9ss\u00e9na. Kasala'an \u00e9toles d\u00e2lem output kasala'an (stderr); berkas s\u00e9 kosong b\u00e9n\u00e9' jaminan jh\u00e2' sobung data. Berkas s\u00e9 \u00e9\u00e9kspor s\u00e8ksek ngandhung katerrangan pribadi: simpen kalab\u00e2n aman.

## Kaluwar d\u00e2ri akun (Logout)

```sh
omi auth logout
```

Par\u00e8ntah pan\u00e8ka mahos kr\u00e9d\u00e9nsial s\u00e9 \u00e9simpen \u00e8 lokal. Kaangghuy mbatalaghi konco' \u00e8 server, angghuy pangaturan konco' pamekar \u00e8 akun panjhennengngan.

Kaangghuy par\u00e8ntah la\u00e9n sareng p\u00e9l\u00e9yan s\u00e9 lebbi ghenna', oladi [pandhuw\u00e2n otama d\u00e2lem bh\u00e2sa \u00c9nggr\u00e8s](../README.md) sareng `omi --help`.
