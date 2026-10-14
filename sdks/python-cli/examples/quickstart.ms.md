# omi-cli — panduan mula pantas Bahasa Melayu

> Panduan praktikal untuk bekerja dengan Omi dari terminal. Sesuai untuk manusia mahupun ejen AI.

`omi-cli` ialah klien baris perintah rasmi untuk API pembangun [Omi](https://omi.me).
Ia memberikan akses pantas dan boleh-diskrip kepada empat entiti utama Omi:
memori, perbualan, item tindakan dan matlamat.

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Dokumentasi:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Kod sumber:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Pemasangan

Kaedah yang disyorkan ialah `pipx`: ia memasang alat dalam persekitaran terasing,
supaya kebergantungannya tidak bercanggah dengan projek anda.

```bash
# disyorkan: pasang dengan pipx
pipx install omi-cli

# atau dengan pip
pip install omi-cli
```

> **Penting: nama pakej dan nama perintah berbeza.**
> * Pakej yang dipasang ialah **`omi-cli`** (pakej berasingan `omi` ialah projek lain yang tidak berkaitan).
> * Selepas pemasangan, perintah yang dijalankan ialah **`omi`**.

Pastikan semuanya berfungsi:

```bash
omi --version
omi --help
```

---

## 2. Pengesahan

`omi-cli` menyokong dua cara log masuk.

| Kaedah | Sesuai untuk | Perintah |
| :--- | :--- | :--- |
| **Kunci pembangun (`omi_dev_*`)** | CI/CD, skrip, ejen AI | `omi auth login --api-key ...` atau pemboleh ubah persekitaran |
| **Log masuk pelayar (Google/Apple)** | Kerja pada komputer sendiri | `omi auth login --browser` |

### Log masuk interaktif

Jalankan tanpa pilihan dan ia akan bertanya kaedah yang mahu digunakan.

```bash
omi auth login
# 1) Browser — log masuk dengan Google atau Apple (untuk manusia)
# 2) API key — tampal kunci pembangun dari app.omi.me (untuk ejen/CI)
```

Jika anda memilih kunci, input disembunyikan supaya kunci tidak kekal dalam sejarah terminal.

### Log masuk terus melalui pelayar

```bash
omi auth login --browser
```

### Log masuk dengan kunci pembangun

Kunci diperoleh di [app.omi.me](https://app.omi.me) di bawah **Developer → API Keys**.

```bash
# simpan kunci dalam konfigurasi
omi auth login --api-key omi_dev_...

# atau hantar melalui persekitaran — lebih sesuai untuk CI/CD dan kontena
export OMI_API_KEY=omi_dev_...
```

Pemboleh ubah persekitaran `OMI_API_KEY` digunakan apabila tiada kunci disimpan
dalam profil aktif, jadi dalam kontena tiada apa perlu ditulis ke cakera. Jika profil
sudah ada kunci, kunci itu didahulukan daripada pemboleh ubah persekitaran.

### Sahkan akses

Dua perintah menjawab soalan berbeza dan jangan dikelirukan:

* `omi auth status` — apa yang disimpan **secara tempatan**: profil, kunci tersembunyi, tarikh luput.
  Berfungsi tanpa rangkaian.
* `omi auth whoami` — permintaan **ke pelayan Omi**: mengesahkan kunci benar-benar diterima.
  Memerlukan rangkaian.

```bash
omi auth status    # semakan tempatan, luar talian
omi auth whoami    # semakan pada pelayan
```

Memperbaharui token yang hampir luput tanpa log masuk semula — perintah ini hanya
untuk sesi pelayar/OAuth. Untuk profil yang disahkan dengan kunci API (`omi_dev_*`),
`omi auth refresh` gagal dengan ralat penggunaan (kod 1): tiada token untuk dibaharui —
tukar kunci dalam apl web Omi jika perlu:

```bash
omi auth refresh
```

Log keluar:

```bash
omi auth logout
```

---

## 3. Perintah asas

### Memori (memories)

Fakta dan pengetahuan yang sistem simpan tentang anda.

```bash
# senarai memori
omi memory list

# buat yang baharu
omi memory create "Pengguna lebih suka mod gelap" --category lifestyle

# lihat satu tertentu
omi memory get <MEMORY_ID>
```

### Perbualan (conversations)

Sejarah suara dan teks daripada peranti atau aplikasi.

```bash
# 5 perbualan terkini
omi conversation list --limit 5

# perbualan lengkap dengan transkrip
omi conversation get <CONVERSATION_ID> --include-transcript
```

### Item tindakan (action items)

Tugas yang Omi simpulkan daripada perbualan.

```bash
# hanya yang belum selesai
omi action-item list --open

# tanda sebagai selesai
omi action-item complete <ACTION_ITEM_ID>
```

### Matlamat (goals)

```bash
# senarai matlamat
omi goal list

# rekod nilai kemajuan baharu (memerlukan KEDUA-DUA argumen: matlamat dan nilai)
omi goal progress <GOAL_ID> 25

# sejarah perubahan
omi goal history <GOAL_ID>
```

---

## Bertanya dengan kata semula jadi (`ask`)

Perintah peringkat-atas berasingan: ia menerima soalan dalam bahasa biasa,
dan jawapan dibina daripada perbualan anda.

```bash
omi ask "apa yang saya putuskan tentang perpindahan itu"
omi --json ask "item tindakan mana yang saya janji untuk selesaikan minggu ini"
```

---

## 4. JSON dan skrip (`--json`)

`omi-cli` boleh menghasilkan JSON yang boleh dibaca mesin. Pilihan `--json` ialah
**global**, jadi ia mesti diletakkan **sebelum** sub-perintah.

```bash
# memori: ambil id, teks dan kategori
omi --json memory list | jq '.[] | {id, content, category}'

# tajuk perbualan terkini
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# item tindakan belum selesai
omi --json action-item list --open | jq '.'
```

> **Kesalahan biasa.** `--json` diletakkan sebelum sub-perintah, bukan selepasnya.
> * Betul: `omi --json memory list`
> * Salah: `omi memory list --json`

Dalam mod `--json`, mesej kemajuan dan pemutar untuk manusia hilang —
stdout hanya mengandungi satu dokumen JSON yang sah. Ralat pergi ke stderr
dalam bentuk `{"error": "...", "detail": "..."}`.

---

## 5. Kod keluar

Kod keluar yang stabil untuk pembuatan keputusan dalam skrip.

| Kod | Maksud |
| :--- | :--- |
| `0` | Berjaya |
| `1` | Ralat penggunaan (bendera salah, argumen wajib tiada) |
| `2` | Pengesahan gagal — log masuk diperlukan |
| `3` | Ralat pelayan/rangkaian |
| `4` | Had kadar — cuba semula sebentar lagi |
| `5` | Sumber tidak dijumpai |

```bash
if ! omi memory get "$MEMO_ID" --json > /tmp/m.json; then
  code=$?
  case $code in
    2) omi auth login --browser ;;
    5) echo "memori itu tiada" ;;
    *) echo "ralat $code" ;;
  esac
fi
```

---

## 6. Profil dan konfigurasi

Jika anda ada beberapa akaun atau persekitaran, asingkan dengan profil.
Tetapan disimpan dalam `~/.omi/config.toml`.

```bash
# log masuk ke profil peribadi
omi --profile personal auth login

# log masuk ke profil kerja
omi --profile work auth login

# jalankan perintah dalam profil tertentu
omi --profile work memory list
```

Profil yang digunakan ditentukan dalam susunan ini: pilihan `--profile` (atau `-p`)
diutamakan atas segalanya; kemudian pemboleh ubah persekitaran `OMI_PROFILE`;
kemudian profil aktif dalam `~/.omi/config.toml`; dan akhirnya profil `default` sebagai sandaran.

Lihat dan ubah konfigurasi itu sendiri:

```bash
# apa yang disediakan sekarang
omi config show

# di mana fail konfigurasi berada
omi config path

# ubah nilai
omi config set api_base https://api.omi.me
```

---

## 7. Langkah seterusnya

* [`agent_quickstart.md`](./agent_quickstart.md) — cara menyambung `omi-cli` kepada ejen AI.
* [`shell_examples.sh`](./shell_examples.sh) — contoh shell sedia guna.
* [Dokumentasi Omi](https://docs.omi.me/doc/developer/cli/introduction) — rujukan perintah penuh.
