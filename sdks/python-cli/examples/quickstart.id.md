# Mulai cepat dengan omi-cli

Panduan ini menjelaskan perintah dasar dalam bahasa Indonesia. Nama perintah
dan pesan program tetap dalam bahasa Inggris. Contoh perintah di bawah tidak
mengubah memori, percakapan, item tindakan, atau sasaran Anda.

## Memasang program

Syarat: Python 3.10 atau versi yang lebih baru dan akun Omi.

Jika `pipx` sudah terpasang:

```sh
pipx install omi-cli
omi --help
```

Sebagai alternatif, pasang program di lingkungan virtual Python yang sudah
diaktifkan:

```sh
python -m pip install omi-cli
omi --help
```

Jika terminal tidak menemukan `omi`, pastikan lingkungan virtual aktif atau
direktori tempat `pipx` memasang executable sudah ada di `PATH`.

## Menghubungkan akun

Jalankan panduan interaktif:

```sh
omi auth login
```

Pilih login melalui browser atau tempelkan API key developer Omi. Input
interaktif menyembunyikan key tersebut; jangan menuliskannya dalam perintah
yang akan tersimpan di riwayat terminal.

Untuk langsung memakai browser:

```sh
omi auth login --browser
```

Login pada komputer yang sama dengan terminal karena hasil autentikasi memakai
alamat callback lokal. Ikuti instruksi yang tampil di layar.

Setelah login, periksa konfigurasi dan akses API:

```sh
omi auth status
omi auth whoami
```

`status` menampilkan keadaan lokal dan menyamarkan rahasia, tetapi tidak
memeriksa validitasnya di server. `whoami` melakukan permintaan terautentikasi;
jika berhasil, kredensial Anda berfungsi tanpa harus menampilkan nama Anda.

Konfigurasi disimpan di `~/.omi/config.toml` secara default. Jangan membagikan
file ini karena dapat berisi kredensial.

## Membaca data Anda

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Daftar kosong bisa berarti tidak ada item yang cocok dengan filter. Gunakan
bantuan untuk melihat opsi setiap perintah:

```sh
omi memory list --help
omi action-item list --help
```

## Mendapatkan JSON dan menelusuri halaman

Letakkan opsi global `--json` **sebelum** kelompok perintah:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Perintah pertama meminta 25 memori pertama; perintah kedua meminta 25 memori
berikutnya. Satu halaman bukan cadangan lengkap. Output JSON mempertahankan ID
lengkap, sedangkan tabel dapat memendekkan ID untuk tampilan.

Untuk menyimpan satu halaman ke file:

```sh
omi --json memory list --limit 25 --offset 0 > memori-halaman-1.json
```

Pengalihan ini membuat atau mengganti file lokal. Pastikan perintah selesai
dengan sukses sebelum memakai isinya. Error ditulis ke output error; file
kosong tidak membuktikan bahwa tidak ada data. File ekspor mungkin berisi
informasi pribadi, jadi simpan secara privat.

## Memakai profil

State disimpan di `~/.omi/config.toml` (dapat diganti dengan `$OMI_CONFIG`).
Setiap profil memiliki metode autentikasi dan alamat API sendiri. Beralih
profil dengan `--profile`:

```sh
omi config profile use kerja
omi auth login
omi --profile pribadi memory list
```

Perintah konfigurasi yang umum:

```sh
omi config show
omi config path
omi config profile list
```

## Kode keluar

Kode keluar ini stabil dan berguna untuk skrip atau agen:

| Kode | Arti | Contoh kondisi |
| ---: | --- | --- |
| 0 | berhasil | Perintah selesai |
| 1 | error penggunaan | Flag salah, argumen kurang, atau validasi gagal |
| 2 | error autentikasi | Kredensial tidak ada, token kedaluwarsa, atau izin kurang |
| 3 | error server | Server 5xx atau koneksi gagal |
| 4 | terkena pembatasan laju | Server mengembalikan HTTP 429 |
| 5 | tidak ditemukan | Server mengembalikan HTTP 404 |

## Keluar dari akun

```sh
omi auth logout
```

Perintah ini menghapus kredensial yang tersimpan secara lokal. Untuk mencabut
key di server, gunakan pengelolaan developer key pada akun Anda.

Untuk perintah dan opsi lanjutan, lihat [README utama dalam bahasa
Inggris](../README.md) dan jalankan `omi --help`.
