# Panduan Memulai Cepat omi-cli (Indonesian Quickstart Guide)

> Panduan praktis untuk berinteraksi dengan Omi melalui terminal — dirancang untuk pengguna manusia maupun agen AI.

`omi-cli` adalah antarmuka baris perintah (CLI) resmi untuk berinteraksi dengan API Pengembang [Omi](https://omi.me).
Alat ini memungkinkan Anda mengelola empat sumber daya utama Omi secara efisien dan dapat diskrip: memori (*memories*), percakapan (*conversations*), butir tindakan (*action items*), dan target (*goals*).

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Dokumentasi Resmi:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Kode Sumber:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Instalasi

Metode instalasi yang direkomendasikan adalah menggunakan `pipx`, yang mengisolasi dependensi dalam lingkungan mandiri:

```bash
# Direkomendasikan: instalasi dengan pipx
pipx install omi-cli

# Atau gunakan pip standar
pip install omi-cli
```

> **Penting: Perbedaan nama paket dan nama perintah**
> * Nama paket Python yang diinstal adalah **`omi-cli`** (nama `omi` tanpa imbuhan dimiliki oleh paket lain yang tidak terkait).
> * Perintah terminal yang dijalankan setelah instalasi adalah **`omi`**.

Setelah instalasi, pastikan perintah berfungsi dengan benar:

```bash
omi --version
omi --help
```

---

## 2. Autentikasi (Authentication)

`omi-cli` mendukung dua metode autentikasi utama:

| Metode Autentikasi | Penggunaan Utama | Contoh Perintah |
| :--- | :--- | :--- |
| **Kunci API Pengembang (`omi_dev_*`)** | CI/CD, skrip otomatisasi, dan agen AI | `omi auth login --api-key ...` atau variabel lingkungan |
| **OAuth Browser (Google/Apple)** | Komputer pengembangan lokal pribadi | `omi auth login --browser` |

### Masuk Interaktif
Menjalankan perintah tanpa parameter akan menampilkan menu pilihan:

```bash
omi auth login
# 1) Browser — Masuk dengan akun Google atau Apple (direkomendasikan untuk manusia)
# 2) API key — Tempel kunci pengembang dari app.omi.me (direkomendasikan untuk agen/CI)
```

### Masuk Langsung Melalui Browser
```bash
omi auth login --browser
```

### Menggunakan Kunci API Pengembang
Buat kunci API di konsol [app.omi.me](https://app.omi.me) pada menu Developer → API Keys:

```bash
# Mengonfigurasi langsung via perintah
omi auth login --api-key omi_dev_...

# Atau atur variabel lingkungan (ideal untuk CI/CD dan kontainer)
export OMI_API_KEY=omi_dev_...
```

### Memeriksa Status Autentikasi
* `omi auth status`: Menampilkan profil aktif, token tersamarkan, dan masa berlaku secara lokal (bekerja luring/offline).
* `omi auth whoami`: Mengirim permintaan verifikasi ke server Omi untuk memastikan kredensial valid (membutuhkan koneksi internet).

```bash
omi auth status
omi auth whoami
```

Untuk keluar dan menghapus token tersimpan:
```bash
omi auth logout
```

---

## 3. Penggunaan Dasar

Anda dapat melihat dan mengelola empat sumber daya utama Omi:

### Memori (Memories)
Fakta, preferensi, dan wawasan yang dipelajari dan disimpan oleh sistem:

```bash
# Menampilkan daftar memori
omi memory list

# Membuat memori baru
omi memory create "Pengguna lebih menyukai mode gelap" --category lifestyle

# Melihat detail memori tertentu berdasarkan ID
omi memory get <MEMORY_ID>
```

### Percakapan (Conversations)
Riwayat percakapan suara dan teks yang ditangkap dari perangkat Omi atau aplikasi:

```bash
# Menampilkan 5 percakapan terbaru
omi conversation list --limit 5

# Melihat detail percakapan beserta transkrip lengkap
omi conversation get <CONVERSATION_ID> --include-transcript
```

### Butir Tindakan (Action Items)
Tugas dan tindak lanjut yang diekstraksi secara otomatis dari percakapan:

```bash
# Menampilkan hanya butir tindakan yang masih terbuka
omi action-item list --open

# Menandai butir tindakan sebagai selesai
omi action-item complete <ACTION_ITEM_ID>
```

### Target (Goals)
Pelacakan target dan sasaran yang sedang berlangsung:

```bash
# Menampilkan daftar target
omi goal list
```

---

## 4. Pembuatan Skrip dan Output JSON (`--json`)

`omi-cli` mendukung output JSON asli untuk semua perintah. Saat mengintegrasikan dengan `jq` atau skrip otomatisasi, cantumkan opsi `--json` sebagai **opsi global sebelum sub-perintah**:

```bash
# Mengambil memori dalam format JSON lalu mengekstrak id dan konten
omi --json memory list | jq '.[] | {id, content, category}'

# Mengambil judul 5 percakapan terakhir
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# Mengambil butir tindakan yang belum selesai
omi --json action-item list --open | jq '.'
```

> **Catatan Penting:** Opsi `--json` harus diletakkan **sebelum** kata kerja sub-perintah (seperti `memory` atau `conversation`):
> * Benar: `omi --json memory list`
> * Salah: `omi memory list --json`

---

## 5. Kode Keluar (Exit Codes)

Untuk penanganan galat yang andal pada skrip otomatisasi dan alur CI, perintah mengembalikan kode keluar yang terstandar:

| Kode Keluar | Arti | Keterangan |
| :---: | :--- | :--- |
| `0` | Sukses (*Success*) | Perintah berhasil diselesaikan |
| `1` | Kesalahan Penggunaan (*Usage Error*) | Parameter salah atau argumen wajib tidak diberikan |
| `2` | Kesalahan Autentikasi (*Auth Error*) | Belum masuk, kunci API tidak valid, atau sesi kedaluwarsa |
| `3` | Kesalahan Server (*Server Error*) | Respon 5xx, batas waktu habis, atau kegagalan jaringan |
| `4` | Batas Permintaan (*Rate Limited*) | Kode status HTTP 429 Terlalu Banyak Permintaan |
| `5` | Tidak Ditemukan (*Not Found*) | Kode status HTTP 404 (ID sumber daya tidak ditemukan) |

---

## 6. Contoh Skrip Shell

### Bash / Zsh (Linux / macOS)
```bash
# Menyetel kunci API
export OMI_API_KEY="omi_dev_kunci_anda_di_sini"

# Mengambil 10 memori terbaru dan memeriksa status keberhasilan
if omi --json memory list --limit 10 > memori.json; then
  echo "Berhasil mengambil data memori"
else
  echo "Gagal mengambil data, kode keluar: $?"
fi
```

### PowerShell (Windows)
```powershell
# Menyetel kunci API
$env:OMI_API_KEY = "omi_dev_kunci_anda_di_sini"

# Mengurai data JSON langsung di PowerShell
try {
    $memories = omi --json memory list | ConvertFrom-Json
    $memories | Select-Object id, content
} catch {
    Write-Error "Terjadi kesalahan saat memproses data: $_"
}
```

---

## 7. Integrasi dengan Desktop API Lokal

Di lingkungan tempat aplikasi Omi Desktop berjalan, Anda dapat berinteraksi langsung dengan riwayat layar dan basis data lokal tanpa melalui server awan:

```bash
# Konfigurasi alamat dan token desktop lokal
omi local configure --url http://127.0.0.1:47778 --token TOKEN_DESKTOP_ANDA

# Cek status koneksi lokal
omi --json local status

# Cari tangkapan layar lokal
omi --json local search-screen "paket harga" --days 7 --app Safari
```

---

## 8. Profil Konfigurasi (Profiles)

Jika Anda mengelola beberapa akun atau memisahkan lingkungan pengujian dan produksi, gunakan opsi `--profile`. Konfigurasi disimpan di `~/.omi/config.toml`:

```bash
# Masuk ke profil pribadi
omi --profile personal auth login

# Masuk ke profil kerja/kantor
omi --profile work auth login

# Menjalankan perintah dengan profil tertentu
omi --profile work memory list
```
