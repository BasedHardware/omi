# Panduan Permulaan Cepat omi-cli (Bahasa Melayu)

> Panduan praktikal untuk berinteraksi dengan Omi daripada terminal. Sesuai untuk manusia dan ejen AI.

`omi-cli` ialah antara muka baris perintah rasmi untuk berinteraksi dengan API pembangun [Omi](https://omi.me). Ia mengendalikan empat sumber teras Omi — **memori, perbualan, item tindakan, dan matlamat** — secara cekap dan boleh di-skrip.

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Dokumentasi rasmi:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Sumber kod:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Pemasangan

Cara pemasangan yang disyorkan ialah menggunakan `pipx` supaya kebergantungan diasingkan dengan baik.

```bash
# Disyorkan: pasang menggunakan pipx
pipx install omi-cli

# Atau gunakan pip
pip install omi-cli
```

> **Penting: Perbezaan nama pakej dan nama perintah**
> * Nama pakej Python yang dipasang ialah **`omi-cli`** (pakej `omi` yang berdiri sendiri adalah pakej lain yang tidak berkaitan).
> * Nama perintah yang dijalankan di terminal selepas pemasangan ialah **`omi`**.

Selepas pemasangan, sahkan versi dan bantuan.

```bash
omi --version
omi --help
```

---

## 2. Pengesahan (Authentication)

`omi-cli` menyokong dua cara pengesahan.

| Kaedah | Tujuan | Contoh perintah |
| :--- | :--- | :--- |
| **Kunci API pembangun (`omi_dev_*`)** | CI/CD, skrip automatik, ejen AI | `omi auth login --api-key ...` atau pembolehubah persekitaran |
| **OAuth pelayar (Google/Apple)** | PC / komputer riba pembangun | `omi auth login --browser` |

### Log masuk interaktif
Tanpa pilihan, anda akan ditanya untuk memilih antara log masuk pelayar atau输入 kunci API.

```bash
omi auth login
# 1) Browser — log masuk dengan akaun Google atau Apple (untuk manusia)
# 2) API key — tampal kunci pembangun daripada app.omi.me (untuk ejen/CI)
```

### Log masuk terus melalui pelayar
```bash
omi auth login --browser
```

### Menggunakan kunci API
Dapatkan kunci pembangun daripada **Developer → API Keys** di [app.omi.me](https://app.omi.me), kemudian tetapkannya.

```bash
# Tetap melalui perintah
omi auth login --api-key omi_dev_...

# Atau tetap melalui pembolehubah persekitaran (sesuai untuk CI/CD atau kontena)
export OMI_API_KEY=omi_dev_...
```

### Sahkan status pengesahan
* `omi auth status`: paparkan profil pengesahan tempatan, token bertopeng, dan tarikh tamat (berfungsi di luar talian).
* `omi auth whoami`: hantar permintaan pengesahan sebenar ke pelayan Omi (memerlukan sambungan rangkaian).

```bash
omi auth status
omi auth whoami
```

Untuk log keluar, jalankan:
```bash
omi auth logout
```

---

## 3. Penggunaan Asas

Anda boleh menyenaraikan dan mengendalikan empat sumber teras Omi.

### Memori (Memories)
Urus fakta dan pengetahuan yang dipelajari oleh sistem.

```bash
# Senarai semua memori
omi memory list

# Cipta memori baharu
omi memory create "Pengguna lebih suka mod gelap" --category lifestyle

# Papar butiran memori tertentu
omi memory get <MEMORY_ID>
```

### Perbualan (Conversations)
Sejarah audio atau teks perbualan yang diambil daripada peranti boleh dipakai atau aplikasi.

```bash
# Dapatkan 5 perbualan terkini
omi conversation list --limit 5

# Papar butiran perbualan dan transkrip
omi conversation get <CONVERSATION_ID> --include-transcript
```

### Item Tindakan (Action Items)
Tugas atau item susulan yang diekstrak secara automatik daripada perbualan.

```bash
# Senarai item tindakan yang belum selesai sahaja
omi action-item list --open

# Tandakan item tindakan sebagai selesai
omi action-item complete <ACTION_ITEM_ID>
```

### Matlamat (Goals)
Urus matlamat yang dijejaki kemajuannya.

```bash
# Senarai semua matlamat
omi goal list
```

---

## 4. Pemprosesan Skrip dan Output JSON (`--json`)

`omi-cli` menyokong output JSON secara natif. Apabila digandingkan dengan `jq` atau skrip Python, **pilihan global** `--json` mesti diletakkan sebelum sub-perintah.

```bash
# Dapatkan senarai memori dalam JSON dan ekstrak ID serta kandungannya
omi --json memory list | jq '.[] | {id, content, category}'

# Dapatkan tajuk 5 perbualan terkini
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# Senarai item tindakan yang belum selesai
omi --json action-item list --open | jq '.[] | {id, title, due_at}'

# Senarai matlamat
omi --json goal list | jq '.[] | {id, title, progress: .progress_percent}'
```

---

## 5. Diagnostik Sesi

Gunakan kedua-dua perintah ini secara berpasangan untuk menyelesaikan masalah dengan cepat.

```bash
# 1) Periksa konfigurasi tempatan dahulu
omi auth status

# 2) Sahkan dengan pelayan Omi
omi auth whoami

# 3) Jika perlu, mulakan semula log masuk
omi auth login
```

---

## 6. Amalan Terbaik

* **Gunakan `--json` dalam skrip:** Elakkan parsing teks bebas; sentiasa andalkan output JSON berstruktur.
* **Pisahkan persekitaran dengan `pipx`:** Ini mengelakkan konflik kebergantungan dengan pakej Python lain.
* **Jangan kongsi kunci API:** Kunci `omi_dev_*` membuka akses akaun penuh — simpan dalam pengurus rahsia atau pembolehubah persekitaran.
* **Log keluar dari peranti yang dipinjamkan:** Gunakan `omi auth logout` selepas sesi pada mesin bersama.

---

## 7. Penyelesaian Masalah

| Simptom | Kemungkinan punca | Penyelesaian |
| :--- | :--- | :--- |
| `command not found: omi` | PATH tidak mengandungi direktori bin pipx | Jalankan `pipx ensurepath` dan mulakan semula terminal |
| `401 Unauthorized` | Kunci API tidak sah atau tamat tempoh | Jana kunci baharu di app.omi.me dan kemas kini |
| `connection refused` | Tiada akses rangkaian ke pelayan Omi | Sahkan sambungan internet dan tetapan proksi |
| `permission denied` pada fail konfigurasi | Direktori konfigurasi tidak boleh ditulis | Periksa kebenaran `~/.config/omi` |

---

## 8. Pautan Pantas

* Repositori sumber: [github.com/BasedHardware/omi](https://github.com/BasedHardware/omi)
* Dokumentasi lengkap: [docs.omi.me](https://docs.omi.me)
* Isu dan sokongan: [github.com/BasedHardware/omi/issues](https://github.com/BasedHardware/omi/issues)
* Komuniti Discord: Jemputan tersedia melalui halaman utama Omi