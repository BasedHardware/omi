# Panduan Pantas omi-cli dalam Bahasa Melayu

> Panduan praktikal untuk berinteraksi dengan Omi dari terminal. Sesuai untuk manusia dan juga agen AI.

`omi-cli` ialah antara muka baris arahan rasmi untuk [Omi Developer API](https://docs.omi.me/doc/developer/cli/introduction).
Ia membolehkan anda mengurus empat sumber utama Omi — memori (memories), perbualan (conversations), item tindakan (action items) dan matlamat (goals) — dengan cekap dan boleh diskrip.

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Dokumentasi rasmi:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Kod sumber:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

> **Nota:** README bahasa Inggeris di [examples/README.md](README.md) kekal sebagai rujukan utama (authoritative). Panduan ini adalah terjemahan editorial dalam Bahasa Melayu.

---

## 1. Pemasangan

Kaedah pemasangan yang disyorkan ialah `pipx`, kerana ia mengasingkan kebergantungan.

```bash
# Disyorkan: pasang menggunakan pipx
pipx install omi-cli

# atau gunakan pip
pip install omi-cli
```

> **Penting: perbezaan nama pakej dan nama arahan**
> * Nama pakej Python yang dipasang ialah **`omi-cli`** (pakej `omi` sahaja ialah pakej lain yang tidak berkaitan).
> * Nama arahan yang dijalankan dalam terminal selepas pemasangan ialah **`omi`**.

Selepas pemasangan, semak versi dan bantuan:

```bash
omi --version
omi --help
```

---

## 2. Pengesahan (Authentication)

`omi-cli` menyokong dua kaedah pengesahan.

| Kaedah | Kegunaan utama | Contoh arahan |
| :--- | :--- | :--- |
| **Kunci API pembangun (`omi_dev_*`)** | CI/CD, skrip automasi, agen AI | `omi auth login --api-key ...` atau pembolehubah persekitaran |
| **OAuth pelayar (Google/Apple)** | PC / komputer riba pembangun | `omi auth login --browser` |

### Log masuk interaktif
Jalankan tanpa sebarang pilihan untuk memilih log masuk pelayar atau kemasukan kunci API:

```bash
omi auth login
# 1) Browser — log masuk dengan akaun Google atau Apple (untuk manusia)
# 2) API key — tampal kunci pembangun dari app.omi.me (untuk agen/CI)
```

### Log masuk terus melalui pelayar
```bash
omi auth login --browser
```

### Menggunakan kunci API
Dapatkan kunci pembangun daripada [app.omi.me](https://app.omi.me) di bahagian "Developer → API Keys", kemudian tetapkannya:

```bash
# Tetapkan melalui arahan
omi auth login --api-key omi_dev_...

# atau melalui pembolehubah persekitaran (terbaik untuk CI/CD dan kontena)
export OMI_API_KEY=omi_dev_...
```

### Menyemak status pengesahan
* `omi auth status`: memaparkan profil pengesahan yang disimpan secara setempat, token tersamar dan tarikh luput (berfungsi luar talian).
* `omi auth whoami`: menghantar permintaan pengesahan sebenar ke pelayan Omi untuk memastikan kredensial sah (perlukan sambungan rangkaian).

```bash
omi auth status
omi auth whoami
```

Untuk log keluar:
```bash
omi auth logout
```

---

## 3. Penggunaan asas

Anda boleh menyenaraikan dan mengurus empat sumber teras Omi.

### Memori (Memories)
Urus fakta dan pengetahuan yang dipelajari oleh sistem.

```bash
# Senaraikan memori
omi memory list

# Cipta memori baharu
omi memory create "Pengguna lebih suka mod gelap" --category lifestyle

# Papar butiran memori tertentu
omi memory get <MEMORY_ID>
```

### Perbualan (Conversations)
Sejarah perbualan audio/teks daripada peranti wearable atau aplikasi.

```bash
# Dapatkan 5 perbualan terkini
omi conversation list --limit 5

# Papar butiran dan transkrip sesuatu perbualan
omi conversation get <CONVERSATION_ID> --include-transcript
```

### Item Tindakan (Action Items)
Tugasan dan item susulan yang diekstrak secara automatik daripada perbualan.

```bash
# Senaraikan hanya item tindakan yang belum selesai
omi action-item list --open

# Tanda item tindakan sebagai selesai
omi action-item complete <ACTION_ITEM_ID>
```

### Matlamat (Goals)
Jejaki matlamat dan kemajuan anda.

```bash
# Senaraikan matlamat
omi goal list
```

---

## 4. Penskripan dan output JSON (`--json`)

`omi-cli` menyokong output JSON secara natif. Apabila menggunakannya dengan `jq` atau skrip Python, letakkan `--json` sebagai **pilihan global** — iaitu **sebelum** subarahan.

```bash
# Dapatkan senarai memori dalam JSON dan ekstrak id serta kandungan
omi --json memory list | jq '.[] | {id, content, category}'

# Dapatkan tajuk 5 perbualan terkini
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# Senarai item tindakan yang belum selesai
omi --json action-item list --open | jq '.'
```

> **Penting:** `--json` mesti diletakkan **sebelum** subarahan seperti `memory` atau `conversation`.
> * Betul: `omi --json memory list`
> * Salah: `omi memory list --json`

---

## 5. Kod Keluar (Exit Codes)

Kod keluar yang jelas memudahkan pengendalian ralat dalam skrip dan CI.

| Kod Keluar | Maksud | Perincian |
| :---: | :--- | :--- |
| `0` | Berjaya | Arahan selesai tanpa ralat |
| `1` | Ralat penggunaan | Bendera tidak sah, argumen tidak lengkap, dll. |
| `2` | Ralat pengesahan | Belum log masuk, kunci API tidak sah atau token luput |
| `3` | Ralat pelayan | Respons 5xx, tamat masa sambungan, kegagalan rangkaian |
| `4` | Had kadar | 429 Too Many Requests |
| `5` | Sumber tidak dijumpai | 404 Not Found (ID yang diberikan tidak wujud) |

---

## 6. Contoh persediaan pembolehubah persekitaran mengikut shell

### Bash / Zsh (Linux / macOS)
```bash
# Tetapkan kunci API
export OMI_API_KEY="omi_dev_kunci_sebenar_anda_di_sini"

# Dapatkan senarai
omi --json memory list --limit 10
```

### PowerShell (Windows)
```powershell
# Tetapkan kunci API
$env:OMI_API_KEY = "omi_dev_kunci_sebenar_anda_di_sini"

# Contoh penghuraian JSON dalam PowerShell
(omi --json memory list | ConvertFrom-Json) | Select-Object id, content
```

---

## 7. Integrasi dengan Desktop API setempat

Jika aplikasi Omi Desktop sedang berjalan, anda boleh menyoal sejarah skrin setempat dan pangkalan data SQL secara terus tanpa melalui API awan.

```bash
# Tetapkan destinasi API setempat
omi local configure --url http://127.0.0.1:47778 --token TOKEN_DESKTOP_ANDA

# Semak status sambungan
omi --json local status

# Carian sejarah skrin
omi --json local search-screen "pelan harga" --days 7 --app Safari
```

---

## 8. Fungsi Profil (Profiles)

Untuk menggunakan berbilang akaun atau persekitaran (contohnya produksi dan ujian), gunakan pilihan `--profile`. Tetapan disimpan dalam `~/.omi/config.toml`.

```bash
# Log masuk untuk profil peribadi
omi --profile personal auth login

# Log masuk untuk profil kerja/pembangunan
omi --profile work auth login

# Jalankan arahan dengan profil tertentu
omi --profile work memory list
```
