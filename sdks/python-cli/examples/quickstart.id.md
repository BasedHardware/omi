# Memulai omi-cli

Panduan ini menjelaskan perintah-perintah pertama dalam bahasa Indonesia. Nama
perintah dan pesan dari program tetap dalam bahasa Inggris. Contoh kueri di
sini hanya membaca data: memory, conversation, action item, dan goal milikmu
tidak akan berubah.

## Memasang program

Prasyarat: Python 3.10 atau versi yang lebih baru, dan sebuah akun Omi.

Jika `pipx` sudah terpasang:

```sh
pipx install omi-cli
omi --help
```

Sebagai alternatif, pasang di dalam virtual environment Python yang sedang
aktif:

```sh
python -m pip install omi-cli
omi --help
```

Perhatikan bahwa nama paketnya `omi-cli`, sedangkan perintah yang dijalankan
bernama `omi`. Jika terminal tidak menemukan `omi`, pastikan virtual
environment sudah aktif, atau direktori tempat `pipx` memasang program sudah
ada di `PATH`.

## Menghubungkan akun

Jalankan pemandu interaktif:

```sh
omi auth login
```

Pilih masuk lewat peramban, atau tempelkan API key developer Omi. Masukan
interaktif menyembunyikan key tersebut; hindari mengetikkannya langsung di
dalam perintah karena akan tersimpan di riwayat terminal.

Untuk langsung lewat peramban:

```sh
omi auth login --browser
```

Masuklah dari komputer yang sama dengan terminal, karena respons autentikasi
memakai alamat lokal. Ikuti petunjuk yang muncul di layar.

Setelah itu, periksa konfigurasi dan akses API:

```sh
omi auth status
omi auth whoami
```

`status` menampilkan keadaan di sisi lokal dan menyembunyikan kredensialnya,
tetapi tidak memeriksa keabsahannya ke server. `whoami` mengirim permintaan
terautentikasi; kalau berhasil, berarti kredensialmu memang bekerja, meski
belum tentu menampilkan namamu.

Konfigurasi tersimpan di `~/.omi/config.toml` secara bawaan. Jangan bagikan
berkas ini karena dapat memuat kredensialmu.

## Melihat datamu

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Daftar yang kosong belum tentu berarti datamu hilang — bisa saja memang tidak
ada yang cocok dengan kueri tersebut. Gunakan bantuan bawaan untuk menemukan
filter tiap perintah:

```sh
omi memory list --help
omi action-item list --help
```

## Mengambil JSON dan menelusuri halaman

Letakkan opsi global `--json` **sebelum** grup perintahnya:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Perintah pertama meminta 25 memory pertama, yang kedua meminta 25 berikutnya.
Jadi satu halaman saja bukan cadangan data yang utuh. Keluaran JSON
mempertahankan identifier secara penuh, sedangkan tampilan tabel bisa
memendekkannya agar muat di layar.

Untuk menyimpan satu halaman ke berkas:

```sh
omi --json memory list --limit 25 --offset 0 > memory-halaman-1.json
```

Pengalihan ini membuat berkas baru atau menimpa yang sudah ada. Pastikan
perintahnya selesai tanpa galat sebelum kamu memakai isinya. Pesan galat
ditulis ke saluran error, sehingga berkas yang kosong tidak menjamin bahwa
datanya memang tidak ada. Berkas hasil ekspor dapat memuat informasi pribadi,
jadi simpan secara tertutup.

## Keluar

```sh
omi auth logout
```

Perintah ini menghapus kredensial yang tersimpan di komputermu. Untuk mencabut
sebuah key di sisi server, gunakan pengaturan developer key di akunmu.

Untuk perintah lain dan opsi lanjutan, lihat
[panduan utama dalam bahasa Inggris](../README.md) dan `omi --help`.
