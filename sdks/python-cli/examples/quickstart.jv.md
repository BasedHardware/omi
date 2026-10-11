# Miwiti cepet nganggo omi-cli

Pandhuan iki nerangake prentah dhasar ing basa Jawa. Jeneng prentah lan
pesen saka program tetep nganggo basa Inggris. Conto pitakon ing ngisor iki
ora ngowahi memori, obrolan, tugas, utawa tujuan sampeyan.

## Nginstal program

Syarat: Python 3.10 utawa versi luwih anyar lan akun Omi.

Yen `pipx` wis diinstal:

```sh
pipx install omi-cli
omi --help
```

Utawa, instal ing lingkungan virtual Python sing wis diaktifake:

```sh
python -m pip install omi-cli
omi --help
```

Yen terminal ora nemokake `omi`, priksa manawa lingkungan virtual wis aktif
utawa folder eksekutabel saka `pipx` wis ana ing `PATH`.

## Nyambungake akun

Jalanake tuntunan interaktif:

```sh
omi auth login
```

Pilih mlebu nganggo browser utawa nempelake kunci API pangembang Omi.
Input interaktif ndhelikake kunci; aja nulis kunci ing prentah sing bakal
katon ing riwayat terminal.

Kanggo langsung nggunakake browser:

```sh
omi auth login --browser
```

Mlebu ing komputer sing padha karo terminal amarga asil otentikasi nggunakake
alamat lokal. Tindakake pandhuan sing katon ing layar.

Sawise kuwi, priksa konfigurasi lan akses API:

```sh
omi auth status
omi auth whoami
```

`status` nuduhake kahanan lokal lan nutupi rahasia, nanging ora mriksa
validitasé ing server. `whoami` nindakake panjalukan sing wis diautentikasi;
yen kasil, iku mbuktekake kredensial bisa digunakake tanpa kudu nampilake
jeneng sampeyan.

Sacara baku konfigurasi disimpen ing `~/.omi/config.toml`. Aja nuduhake file
iki amarga bisa ngemot kredensial.

## Ndeleng data sampeyan

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Dhaptar kosong bisa uga mung ateges ora ana item sing cocog karo panyaring.
Gunakake pitulung kanggo ndeleng panyaring saben prentah:

```sh
omi memory list --help
omi action-item list --help
```

## Njupuk JSON lan ngliwati kaca

Lebokake opsi global `--json` **sadurunge** klompok prentah:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Prentah kapisan njaluk 25 memori pisanan lan prentah kapindho njaluk 25
memori sabanjure. Dadi, siji kaca dudu cadangan lengkap. Output JSON njaga
ID sakabehe, dene tabel bisa nyepetake ID supaya gampang diwaca.

Kanggo nyimpen siji kaca ing file:

```sh
omi --json memory list --limit 25 --offset 0 > memori-kaca-1.json
```

Pangalihan iki nggawe utawa ngganti file lokal. Priksa manawa prentah rampung
karo sukses sadurunge nggunakake isiné. Error ditulis menyang output error;
file kosong ora njamin ora ana data. File ekspor bisa ngemot informasi pribadi,
dadi simpen ing panggonan sing aman.

## Ngganti profil

State ana ing `~/.omi/config.toml` (bisa diganti nganggo `$OMI_CONFIG`). Saben
profil nduwèni metode otentikasi lan alamat API dhewe. Gunakake `--profile`
kanggo milih profil:

```sh
omi config profile use kerja
omi auth login
omi --profile pribadi memory list
```

Prentah konfigurasi sing umum:

```sh
omi config show
omi config path
omi config profile list
```

## Kode metu

Kode iki stabil lan migunani kanggo skrip utawa agen:

| Kode | Teges | Kahanan umum |
| ---: | --- | --- |
| 0 | sukses | Prentah rampung |
| 1 | error panggunaan | Flag salah, argumen ilang, utawa validasi gagal |
| 2 | error otentikasi | Kredensial ora ana, token kadaluwarsa, utawa izin kurang |
| 3 | error server | Server 5xx utawa sambungan gagal |
| 4 | diwatesi laju | Server ngasilake HTTP 429 |
| 5 | ora ditemokake | Server ngasilake HTTP 404 |

## Metu saka akun

```sh
omi auth logout
```

Prentah iki mbusak kredensial sing disimpen sacara lokal. Kanggo mbatalake
kunci ing server, gunakake pangaturan kunci pangembang ing akun sampeyan.

Kanggo prentah lan opsi liyane, delengen [pandhuan utama ing basa
Inggris](../README.md) lan jalanake `omi --help`.
