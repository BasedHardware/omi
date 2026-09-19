# Mappammula Masitta' meggunakai omi-cli

Pannawa-nawaé iyyé mappaissengeng parénta-parénta maraja ri lalen Basa Ugi (Buginese). Aseng parénta sibawa pasenna program tette' makkéguna Basa Inggiris. Conto papparéksang (query) ri yawa dé' na-pinra ingngerangeng (memories), bicara-bicara (conversations), jamang-jamang (action items), iyyaré'ga tujuang (goals) idi'.

## Mappasang program

Syaratna: Python 3.10 iyyaré'ga versi madoro kaminang baru sibawa akun Omi.

Rékko purani idi' mappasang `pipx`:

```sh
pipx install omi-cli
omi --help
```

Mancaji sella' laing, idi' wedding mappasang ri lalen virtual environment Python iya engkaé aktif:

```sh
python -m pip install omi-cli
omi --help
```

Rékko terminal dé' na-runtu' `omi`, téntukangi virtual environment engka aktif iyyaré'ga folder eksekusi polé ri `pipx` pura engkani ri `$PATH` idi'.

## Pasituju akun idi'

Jalangkangi asisten interaktif:

```sh
omi auth login
```

Péléki muttama' ri laleng browser iyyaré'ga péléki nempeleng kuncinna API pappa'déce' Omi. Input interaktif massubbuang kuncinna; aja' mu-tulis kuncinna ri parénta iya weddingngé tassimpng ri laleng riwayat terminal.

Mancaji langsungngi makkégunang browser:

```sh
omi auth login --browser
```

Muttama'ki ri komputera iya padaé sibawa onrong terminal majjama: appalireng autentikasi makkégunang alamat lokal. Turu'i petunjukka ri layara.

Puranaro, paréksai konfigurasi sibawa akses API:

```sh
omi auth status
omi auth whoami
```

`status` mappaitang kahanan lokal sibawa massubbu rahasia, tapi dé' na-paréksa sah-na ri laleng server. `whoami` massuro parénta iya puraé ri-autentikasi; rékko makessing jamangna, iyyé mappatette' makkeda kredensial majjamai tépu tanra napallaloang mappaitang aseng idi'.

Ripattentuangngi makkeda konfigurasi tassimpen ri `~/.omi/config.toml`. Aja' mu-bagekangi file iyyé nasaba' weddingngi engka lalenna kredensial rahasianna idi'.

## Mapparéksa data idi'

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Daftara iya kosongngé weddingngi makkeda dé' gaga barang iya situjué sibawa panyarinna. Pakei tulungngé untu' mitai panyaring ri tungke' parénta:

```sh
omi memory list --help
omi action-item list --help
```

## Mala JSON sibawa lalla'ki leppa' (Pagination)

Pataroi piliang global `--json` **ri yolo'na** kalompo' parénta:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Parénta mamulangngé méllau 25 ingngerangeng mamulang; parénta maduanna, 25 settumannaro. Seleppa' tenniyai cadangan iya massulappangngé. Kaluaran JSON nallaloi identifier massulappang, na tabél ri layara weddingngi maponco' untu' paitangngi.

Untu' passimpen seleppa' ri lalen sewwa file:

```sh
omi --json memory list --limit 25 --offset 0 > ingngerangeng-leppa-1.json
```

Pinrangngé iyyé mappancaji iyyaré'ga massella' file lokal. Téntukangi parénta pura pusa manengngi ri yolo'na makkégunang lalenna. Sala-salaé ritulis ri kaluaran sala (stderr); file iya kosongngé tenniya jaminan makkeda dé' gaga data. File iya nallasukengngé weddingngi engka lalenna informasi pribadi: simpengngi maraja.

## Massu' polé ri akun (Logout)

```sh
omi auth logout
```

Parénta iyyé massui kredensial iya tassimpengngé ri lokal. Untu' mabbatalang kuncinna ri laleng server, pakei pangatorang kuncinna pappa'déce' ri akun idi'.

Untu' parénta laingngé sibawa piliang kaminang massulappang, itai [pannawa-nawa maraja ri lalen Basa Inggiris](../README.md) sibawa `omi --help`.
