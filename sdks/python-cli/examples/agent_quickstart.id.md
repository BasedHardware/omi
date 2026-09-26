# omi-cli untuk AI Agent

> Panduan praktis untuk lingkungan yang dikendalikan oleh LLM (Claude Code, Cursor, atau bot otomasi kustom).

## Mengapa CLI ini ramah bagi Agent

* **Protokol JSON yang stabil.** Flag `--json` mengeluarkan satu dokumen JSON yang valid ke stdout dan *hanya* dokumen JSON — tanpa pesan progres, tanpa spinner. Kesalahan dicetak ke stderr sebagai `{"error": "...", "detail": "..."}`.
* **Kode keluar yang dapat diprediksi.** `0` sukses / `1` kesalahan penggunaan / `2` kesalahan autentikasi / `3` kesalahan server / `4` dibatasi frekuensi (rate limited) / `5` sumber daya tidak ditemukan. Agent dapat membuat percabangan logika langsung berdasarkan kode keluar tanpa perlu mem-parsing bahasa alami.
* **Non-interaktif secara default di lingkungan headless.** Teruskan cờ `--yes` (atau `-y`) untuk perintah yang bersifat destruktif; teruskan `--api-key` atau setel `OMI_API_KEY` untuk melewati alur login interaktif.
* **Dukungan coba ulang bawaan.** Kode kesalahan `429` dan `5xx` dicoba ulang secara otomatis dengan backoff sebelum melaporkan kegagalan ke pemanggil.

## Autentikasi (Satu kali, oleh manusia)

Pengguna mendapatkan kunci API pengembang dari web app Omi (`https://app.omi.me` → Developer → API Keys) dan melakukan salah satu dari dua cara berikut:

```bash
omi auth login                          # penempelan interaktif; kunci tidak tersimpan dalam riwayat shell
# atau
export OMI_API_KEY=omi_dev_...          # sementara, ramah kontainer
```

## Lima hal yang paling sering dilakukan Agent

### 1. Membaca memori

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Membuat memori baru

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Membaca percakapan

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Membaca item tindakan yang masih terbuka

```bash
omi action-item list --json --open
```

### 5. Menandai item tindakan selesai

```bash
omi action-item complete --json a1b2c3d4
```

## Local Desktop API (API Desktop Lokal)

Ketika aplikasi Omi Desktop mengekspos API lokal, Agent dapat membaca riwayat layar, rekap harian, basis data SQL lokal, dan item tugas langsung di perangkat tanpa perlu menyentuh cloud dev API:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# atau, untuk sesi sementara:
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

Mutasi lokal (tugas):

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

## Contoh alur kerja: Loop Agent Python

```python
import json
import subprocess
import sys

def run_omi(*args: str) -> dict | list:
    """Jalankan omi CLI dalam mode JSON, lempar pengecualian jika kode keluar bukan 0."""
    cmd = ["omi", "--json", *args]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        # CLI mencetak kesalahan terstruktur ke stderr dalam mode JSON:
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"raw": result.stderr}
        raise RuntimeError(f"omi gagal (exit {result.returncode}): {err}")
    return json.loads(result.stdout)

# Baca semua item tindakan yang terbuka dan tandai selesai jika lebih dari 30 hari.
from datetime import datetime, timezone, timedelta

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = run_omi("action-item", "list", "--open")
for item in items:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        print(f"Menyelesaikan item lama: {item['id']} ({item['description']})")
        run_omi("action-item", "complete", item["id"])
```

## Menangani pembatasan frekuensi (Rate Limits)

```python
if result.returncode == 4:                             # dibatasi frekuensi
    err = json.loads(result.stderr)
    # err["detail"] terlihat seperti: "Retry in 12s. ..."
    # omi CLI sudah mencoba ulang 3 kali secara internal; jika Anda tetap
    # melihat kode 4, hentikan panggilan selama cooldown yang ditentukan.
```

Batas frekuensi cloud saat ini untuk dev API keys:
* Baca (GET): 120 permintaan / menit
* Tulis (POST/PUT/DELETE): 25 permintaan / menit
* Pencarian semantik: 15 permintaan / menit

Batas lokal (jika menggunakan Desktop API): tanpa batas frekuensi buatan; terikat oleh performa perangkat keras host.

## Tips

* Gunakan `--profile <name>` jika agent Anda beralih di antara beberapa akun Omi (misalnya, pengujian vs produksi). Kredensial disimpan secara terpisah di `~/.config/omi/profiles/<name>.json`.
* Untuk pengujian unit terhadap mock server: teruskan `--api-base http://localhost:8080`.
* Jangan mem-parsing stdout dalam format teks biasa — tata letak teks ditujukan untuk kenyamanan mata manusia dan dapat berubah antar rilis. Selalu gunakan `--json` dalam skrip otomatis.
