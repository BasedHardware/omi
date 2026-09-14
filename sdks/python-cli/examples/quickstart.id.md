# Panduan Memulai Cepat omi-cli (Indonesian Quickstart)

> Panduan praktis berinteraksi dengan Omi langsung dari terminal Anda — dirancang untuk pengguna manusia maupun AI agent otonom.

`omi-cli` adalah antarmuka baris perintah (CLI) resmi untuk berinteraksi dengan API pengembang [Omi](https://omi.me). Alat ini menyediakan akses terstruktur dan cepat ke 4 entitas data utama yang dikelola Omi:
* **Memori (*memories*)** — fakta, konteks, dan preferensi yang dipelajari sistem tentang Anda
* **Percakapan (*conversations*)** — rekaman suara dan teks yang telah diproses
* **Daftar Tugas (*action items*)** — tindak lanjut dan tugas yang perlu diselesaikan
* **Sasaran (*goals*)** — metrik pencapaian yang sedang Anda lacak

Dokumentasi ini menyajikan instruksi dalam Bahasa Indonesia, sementara nama perintah CLI, parameter flags, dan keluaran baku sistem tetap menggunakan Bahasa Inggris teknis.

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Dokumentasi Resmi:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Kode Sumber:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Persyaratan & Instalasi

Dibutuhkan **Python 3.10 atau versi yang lebih baru** serta akun aktif di platform Omi.

Sangat disarankan menggunakan `pipx` agar CLI terisolasi secara bersih tanpa mengganggu paket Python global sistem Anda:

```bash
# Metode rekomendasi: instalasi terisolasi via pipx
pipx install omi-cli

# Periksa instalasi
omi --version
omi --help
```

Atau instal ke dalam *virtual environment* Python yang sedang aktif:

```bash
# Metode alternatif via pip
python -m pip install omi-cli
omi --help
```

> **Catatan Penting: Nama Paket vs Nama Perintah:**
> * Nama paket resmi di PyPI adalah **`omi-cli`** (jangan pasang paket bernama `omi`, karena itu adalah paket lain yang tidak berhubungan).
> * Perintah biner eksekusi di terminal adalah langsung: **`omi`**.
> Jika terminal tidak menemukan perintah `omi`, pastikan virtual environment Anda aktif atau direktori instalasi `pipx` sudah terdaftar di variabel sistem `$PATH`.

---

## 2. Autentikasi (`omi auth`)

`omi-cli` mendukung dua mekanisme login utama:

| Metode | Penggunaan Terbaik | Contoh Perintah |
| :--- | :--- | :--- |
| **OAuth Browser (Google/Apple)** | Pengguna personal di komputer lokal | `omi auth login --browser` |
| **API Key Pengembang (`omi_dev_*`)** | AI Agent, Skrip Bash, CI/CD, Server Headless | `omi auth login --api-key ...` atau `OMI_API_KEY` |

### A. Login Interaktif
Jalankan perintah login tanpa flags untuk membuka menu interaktif:

```bash
omi auth login
# → 1) Browser — Masuk via akun Google/Apple (direkomendasikan untuk manusia)
# → 2) API key — Tempel token kunci dari app.omi.me (direkomendasikan untuk AI/CI)
```
Input terminal interaktif secara otomatis menyamarkan karakter kunci rahasia Anda agar tidak tersimpan di histori shell.

### B. Login Langsung via Browser
```bash
omi auth login --browser
```
Buka peramban pada komputer yang sama dengan terminal karena proses *callback* lokal akan menerima token secara otomatis. Ikuti petunjuk otorisasi di layar hingga muncul konfirmasi sukses.

### C. Verifikasi Status Autentikasi
Setelah berhasil masuk, verifikasi status profil dan konektivitas API:

```bash
# Melihat status konfigurasi lokal (kunci rahasia disamarkan dengan aman)
omi auth status

# Memverifikasi validitas token ke server Omi secara langsung
omi auth whoami
```

* `omi auth status` menampilkan konfigurasi lokal tanpa menghubungi server.
* `omi auth whoami` mengirim permintaan terotentikasi ke server untuk mengonfirmasi bahwa kredensial Anda benar-benar valid dan aktif.

Secara default, file konfigurasi disimpan pada `~/.omi/config.toml`. Jaga kerahasiaan file ini dan jangan pernah mengunggahnya ke repositori publik.

### D. Menggunakan Environment Variable (Headless / Agent)
Untuk lingkungan otomatis seperti GitHub Actions, container Docker, atau server tanpa antarmuka grafis:

```bash
export OMI_API_KEY="omi_dev_xxxxxxxxxxxxxxxxxxxx"
omi memory list
```
Jika `OMI_API_KEY` diatur, CLI akan memprioritaskannya saat profil aktif belum memiliki token tersimpan.

### E. Logout / Keluar
```bash
omi auth logout
```
Perintah ini menghapus kredensial yang tersimpan di disk lokal komputer Anda. Untuk mencabut token dari sisi server, kelola melalui dashboard akun pengembang Anda di [app.omi.me](https://app.omi.me).

---

## 3. Menjelajahi Data Anda

Contoh-contoh di bawah ini bersifat *read-only* (hanya membaca data) dan tidak akan mengubah atau menghapus data pribadi Anda:

```bash
# Melihat daftar 5 memori terbaru
omi memory list --limit 5

# Melihat daftar 5 percakapan terbaru
omi conversation list --limit 5

# Menampilkan tugas atau tindak lanjut yang masih terbuka
omi action-item list --open

# Melihat daftar sasaran / progress metrics yang dilacak
omi goal list
```

Jika keluaran berupa daftar kosong, itu berarti belum ada data yang cocok dengan kriteria filter. Gunakan flag `--help` pada setiap sub-perintah untuk melihat filter yang tersedia:

```bash
omi memory list --help
omi conversation list --help
omi action-item list --help
```

---

## 4. Format JSON & Paginasi

Letakkan opsi global `--json` **sebelum** kata kerja perintah utama untuk menghasilkan keluaran terstruktur yang siap diproses oleh `jq`, skrip otomatis, atau AI agent:

```bash
# Mengambil halaman pertama (25 item pertama)
omi --json memory list --limit 25 --offset 0

# Mengambil halaman kedua (25 item berikutnya)
omi --json memory list --limit 25 --offset 25
```

### Menyaring Keluaran dengan `jq`
Format JSON mempertahankan pengidentifikasi lengkap (`id` penuh), berbeda dengan tabel visual terminal yang mungkin memendekkan ID demi kerapian:

```bash
# Menampilkan ID dan isi teks memori saja
omi --json memory list | jq '.[] | {id, content}'

# Menyaring percakapan yang berlangsung lebih dari 60 detik
omi --json conversation list | jq '.[] | select(.duration_seconds > 60)'
```

### Menyimpan Halaman Data ke File Lokal
```bash
omi --json memory list --limit 50 --offset 0 > memori-halaman-1.json
```
Periksa kode keluar perintah (*exit code*) sebelum mengolah file hasil pengalihan. File berukuran kosong tidak selalu menandakan ketiadaan data, melainkan bisa disebabkan oleh kendala jaringan atau kesalahan parameter.

---

## 5. Manajemen Multi-Profil

Jika Anda mengelola beberapa akun (misalnya akun kantor vs akun pribadi), gunakan opsi `--profile` (atau `-p`):

```bash
# Login ke profil khusus 'kantor'
omi --profile kantor auth login

# Membaca data menggunakan profil 'kantor'
omi --profile kantor memory list
```

Variabel lingkungan `OMI_PROFILE` juga dapat digunakan untuk menetapkan profil aktif sesi shell saat ini:

```bash
export OMI_PROFILE=kantor
omi memory list
```
Daftar seluruh profil tersimpan secara rapi di dalam file `~/.omi/config.toml`.

---

## 6. Format Tanggal & Waktu (Datetime Options)
Perintah yang mendukung parameter rentang tanggal menerima format standar ISO 8601 dengan penanda `Z` (UTC) atau *numeric offset*:

```bash
# Contoh dengan offset UTC
omi conversation list --start-date 2026-09-01T00:00:00Z

# Contoh pencarian tugas berdasarkan tenggat waktu
omi action-item list --due-at 2026-09-30T17:00:00+07:00
```

---

## 7. Kode Keluar (*Exit Codes*)

Untuk skrip bash dan integrasi CI/CD, `omi-cli` mengembalikan kode keluar standar berikut:

| Kode | Kategori | Penjelasan & Tindakan Solusi |
| :--- | :--- | :--- |
| `0` | **Sukses** | Perintah berhasil diselesaikan tanpa kendala. |
| `1` | **Kesalahan Penggunaan CLI** | Terjadi kesalahan sintaks perintah atau flag yang saling bertentangan. |
| `2` | **Kredensial / Argumen Tidak Valid** | Token kedaluwarsa, belum login (`omi auth login`), atau argumen parameter tidak dikenal/di luar rentang. |
| `3` | **Kendala Jaringan / Server** | Terjadi respons 5xx dari server atau koneksi jaringan terputus. Pada operasi tulis (*write*), periksa sumber daya terlebih dahulu sebelum mengulang. |
| `4` | **Pembatasan Laju Panggilan (*Rate Limit*)** | Respons `429 Too Many Requests`. CLI akan otomatis mematuhi header `Retry-After`. Tunggu sejenak sebelum mencoba kembali. |
| `5` | **Data Tidak Ditemukan** | Respons `404 Not Found` (ID memori, percakapan, atau tugas tidak ditemukan). |

---

## 8. Referensi Lanjutan

Untuk melihat seluruh kapabilitas dan daftar perintah tingkat lanjut:
* Lihat panduan induk dalam Bahasa Inggris di [`README.md`](../README.md)
* Jalankan `omi --help` untuk panduan kontekstual langsung di terminal Anda.
