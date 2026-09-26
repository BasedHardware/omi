# Memulai dengan omi-cli (Indonesian Quickstart)

Panduan ini memperkenalkan perintah dasar `omi-cli` dalam Bahasa Indonesia. Nama perintah dan pesan sistem tetap dalam Bahasa Inggris. Contoh pembacaan di sini hanya membaca data tanpa mengubah memori, percakapan, daftar tugas, atau tujuan Anda.

## 1. Memasang Program (Installation)

**Persyaratan:** Python 3.10 atau versi lebih baru dan akun Omi.

> **Catatan Penting:** Nama paket di PyPI adalah **`omi-cli`**, sedangkan perintah yang dijalankan di terminal setelah instalasi adalah **`omi`**. Ada paket lain yang tidak terkait bernama `omi` di PyPI — jangan memasangnya.

Jika Anda memiliki `pipx`:

```sh
pipx install omi-cli
omi --help
```

Atau, di dalam lingkungan virtual Python (virtualenv) yang aktif:

```sh
python -m pip install omi-cli
omi --help
```

Jika terminal tidak menemukan perintah `omi`, pastikan lingkungan virtual sudah aktif atau direktori `pipx` ada di dalam variabel `PATH` Anda.

## 2. Menghubungkan Akun Anda (Authentication)

Mulai proses masuk interaktif:

```sh
omi auth login
```

Pilih masuk melalui peramban (browser) atau tempelkan Omi Developer API Key Anda. Untuk masuk langsung melalui peramban:

```sh
omi auth login --browser
```

Lakukan proses masuk di komputer yang sama dengan tempat terminal berjalan, karena autentikasi dialihkan kembali ke alamat lokal (localhost).

Kemudian periksa status koneksi dan akses API:

```sh
omi auth status
omi auth whoami
```

`status` menampilkan status konfigurasi lokal dan menyembunyikan kunci rahasia. `whoami` mengirimkan permintaan ke server untuk memastikan kredensial berfungsi dengan benar.

Konfigurasi disimpan secara default di `~/.omi/config.toml`. Jaga keamanan berkas ini karena berisi kunci akses Anda.

## 3. Melihat Data Anda

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Untuk melihat transkrip lengkap dari percakapan tertentu:

```sh
omi conversation get <CONVERSATION_ID> --include-transcript
```

Daftar yang kosong hanya berarti tidak ada data yang cocok dengan kriteria pencarian. Untuk melihat filter dan opsi dari perintah apa pun, gunakan `--help`:

```sh
omi memory list --help
omi conversation list --help
omi goal list --help
```

## 4. Format JSON dan Paginasi (Pagination)

Selalu letakkan opsi global `--json` **sebelum** kelompok perintah:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Perintah pertama meminta 25 catatan pertama; perintah kedua meminta 25 catatan berikutnya.

Untuk menyimpan halaman ke dalam berkas (Export):

```sh
omi --json memory list --limit 25 --offset 0 > memori-halaman-1.json
```

## 5. Keluar (Logout)

Untuk menghapus kredensial dari sistem lokal:

```sh
omi auth logout
```

Perintah ini hanya menghapus informasi masuk dari komputer lokal Anda. Untuk mencabut kunci sepenuhnya dari server, gunakan dasbor pengembang Omi.

Untuk informasi lebih lanjut dan opsi lanjutan, lihat panduan referensi utama dalam Bahasa Inggris: [../README.md](../README.md) dan [agent_quickstart.md](agent_quickstart.md).
