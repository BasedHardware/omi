# omi-cli untuk Agen AI

> Panduan praktis untuk lingkungan berbasis LLM (Claude Code, Cursor, bot khusus).

## Mengapa CLI Ramah untuk Agen

* **Kontrak JSON Stabil.** Flag `--json` mengeluarkan dokumen JSON valid ke stdout dan *hanya* JSON — tanpa log status atau spinner. Kesalahan dikirim ke stderr sebagai `{"error": "...", "detail": "..."}`.
* **Kode Keluar Stabil.** `0` ok / `1` kesalahan penggunaan / `2` kesalahan autentikasi / `3` kesalahan server / `4` batas kecepatan terlampaui / `5` tidak ditemukan. Agen dapat melakukan percabangan berdasarkan kode keluar tanpa penguraian regex pada teks kesalahan.
* **Tanpa Perintah Interaktif dalam Mode Headless.** Gunakan `--yes` (atau `-y`) untuk perintah destruktif; gunakan `--api-key` atau setel `OMI_API_KEY` untuk melewati alur login interaktif browser.
* **Pencobaan Ulang Otomatis.** Respons `429` dan `5xx` dicoba ulang secara otomatis dengan backoff eksponensial sebelum mengembalikan kegagalan.

## Autentikasi (Langkah Sekali oleh Manusia)

Pengguna mengambil kunci API pengembang dari aplikasi web Omi
(`https://app.omi.me` → Developer → API Keys), lalu menjalankan:

```bash
omi auth login                          # tempel interaktif; kunci tidak masuk ke riwayat shell
# atau
export OMI_API_KEY=omi_dev_...          # efemeral, cocok untuk kontainer dan CI/CD
```

## Lima Tindakan Paling Umum oleh Agen

### 1. Membaca Memori (Memories)

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Membuat Memori

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Membaca Percakapan

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Membaca Item Tindakan Terbuka (Action Items)

```bash
omi action-item list --json --open
```

### 5. Menyelesaikan Item Tindakan

```bash
omi action-item complete --json a1b2c3d4
```

## API Desktop Lokal (Local Desktop API)

Ketika Omi Desktop mengekspos API lokalnya, agen dapat menanyakan riwayat layar perangkat, ringkasan, SQL, dan tugas tanpa menggunakan cloud dev API:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# atau untuk sesi efemeral:
export OMI_LOCAL_API_URL=http://127.0.0.1:47778
export OMI_LOCAL_TOKEN=...

omi --json local status
omi --json local tools
omi --json local call search_screen_history --args-json '{"query":"pricing page","days":7}'
omi --json local search-screen "pricing page" --days 7 --app Safari
omi --json local screenshot 123 --output /tmp/omi-shot.jpg
omi --json local sql "SELECT COUNT(*) AS screenshots FROM screenshots"
omi --json local task search "taxes" --include-completed
```

Selesaikan atau hapus tugas hanya ketika diminta secara eksplisit oleh pengguna:

```bash
omi --json local task complete task_1
```
