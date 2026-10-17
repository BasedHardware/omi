# Bermula pantas dengan omi-cli

Panduan ini menerangkan arahan asas dalam bahasa Melayu. Nama arahan dan
mesej program kekal dalam bahasa Inggeris. Arahan contoh di bawah tidak
mengubah memori, perbualan, item tindakan atau matlamat anda.

## Memasang program

Keperluan: Python 3.10 atau lebih baharu dan akaun Omi.

Jika `pipx` sudah dipasang:

```sh
pipx install omi-cli
omi --help
```

Sebagai alternatif, pasang dalam persekitaran maya Python yang telah
diaktifkan:

```sh
python -m pip install omi-cli
omi --help
```

Jika terminal tidak menemui `omi`, pastikan persekitaran maya aktif atau
direktori tempat `pipx` memasang executable sudah ada dalam `PATH`.

## Menyambungkan akaun

Jalankan panduan interaktif:

```sh
omi auth login
```

Pilih log masuk melalui pelayar atau tampal kunci API pembangun Omi. Input
interaktif menyembunyikan kunci itu; jangan tulisnya dalam arahan yang
disimpan dalam sejarah terminal.

Untuk terus menggunakan pelayar:

```sh
omi auth login --browser
```

Log masuk pada komputer yang sama dengan terminal kerana pengesahan
menggunakan alamat panggil balik tempatan. Ikut arahan yang tertera di skrin.

Selepas log masuk, periksa konfigurasi dan akses API:

```sh
omi auth status
omi auth whoami
```

`status` memaparkan keadaan tempatan dan menyamarkan rahsia, tetapi tidak
menyemak kesahihannya di pelayan. `whoami` menghantar permintaan
berpengesahan; jika berjaya, kelayakan anda berfungsi tanpa memaparkan nama
anda.

Konfigurasi disimpan dalam `~/.omi/config.toml` secara lalai. Jangan kongsikan
fail ini kerana ia boleh mengandungi kelayakan.

## Membaca data anda

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Senarai kosong mungkin bermakna tiada item yang sepadan dengan penapis. Lihat
pilihan setiap arahan dalam bantuan:

```sh
omi memory list --help
omi action-item list --help
```

## Mendapatkan JSON dan menyusuri halaman

Letakkan pilihan global `--json` **sebelum** kumpulan arahan:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Arahan pertama meminta 25 memori pertama; arahan kedua meminta 25 berikutnya.
Satu halaman bukan sandaran penuh. Output JSON mengekalkan ID penuh, manakala
jadual boleh memendekkan ID untuk paparan.

Untuk menyimpan satu halaman ke fail:

```sh
omi --json memory list --limit 25 --offset 0 > memori-halaman-1.json
```

Pengalihan ini mewujudkan atau menggantikan fail tempatan. Pastikan arahan
selesai dengan jayanya sebelum menggunakan kandungannya. Ralat ditulis ke
stderr; fail kosong tidak membuktikan tiada data. Fail eksport mungkin
mengandungi maklumat peribadi — simpan secara peribadi.

## Menggunakan profil

Keadaan disimpan dalam `~/.omi/config.toml` (boleh diganti dengan
`$OMI_CONFIG`). Setiap profil mempunyai kaedah pengesahan dan alamat API
tersendiri. Tukar profil dengan `--profile`:

```sh
omi config profile use kerja
omi auth login
omi --profile peribadi memory list
```

Arahan konfigurasi biasa:

```sh
omi config show
omi config path
omi config profile list
```

## Kod keluar

Kod keluar ini stabil dan berguna untuk skrip atau ejen:

| Kod | Maksud | Contoh keadaan |
| ---: | --- | --- |
| 0 | berjaya | Arahan selesai |
| 1 | ralat penggunaan | Flag salah, argumen kurang atau pengesahan gagal |
| 2 | ralat pengesahan | Kelayakan tiada, token tamat tempoh atau keizinan kurang |
| 3 | ralat pelayan | Pelayan 5xx atau sambungan gagal |
| 4 | terhad kadar | Pelayan mengembalikan HTTP 429 |
| 5 | tidak ditemui | Pelayan mengembalikan HTTP 404 |

## Log keluar

```sh
omi auth logout
```

Ini membuang kelayakan yang disimpan secara tempatan. Untuk membatalkan kunci
di pelayan, gunakan pengurusan kunci pembangun pada akaun anda.

Untuk arahan dan pilihan lanjutan, lihat [README utama dalam bahasa
Inggeris](../README.md) dan jalankan `omi --help`.
