# omi-cli untuk agen

> Panduan praktis untuk harness berbasis LLM (Claude Code, Cursor, bot kustom Anda).

## Mengapa CLI ini ramah agen

* **Kontrak JSON yang stabil.** `--json` memancarkan dokumen JSON yang valid ke stdout dan
  *hanya* dokumen JSON — tanpa pesan progres, tanpa animasi pemuatan. Kesalahan diarahkan ke
  stderr sebagai `{"error": "...", "detail": "..."}`.
* **Kode keluar yang stabil.** `0` ok / `1` penggunaan salah / `2` autentikasi gagal / `3` kesalahan server / `4` batas
  kecepatan terlampaui (rate limited) / `5` tidak ditemukan. Agen dapat melakukan percabangan logika pada kode-kode ini tanpa perlu mengurai kesalahan bahasa alami.
* **Tanpa prompt interaktif dalam konteks headless.** Teruskan `--yes` (atau `-y`) untuk
  perintah destruktif; teruskan `--api-key` atau atur `OMI_API_KEY` untuk melewati
  masuk interaktif.
* **Perilaku coba ulang yang toleran.** Kesalahan `429` dan `5xx` dicoba ulang secara otomatis dengan backoff eksponensial
  sebelum dimunculkan ke permukaan.

## Autentikasi (sekali saja, oleh pengguna)

Pengguna mendapatkan kunci API pengembang dari aplikasi web Omi
(`https://app.omi.me` → Developer → API Keys) dan memilih salah satu:

```bash
omi auth login                          # penempelan interaktif; kunci tidak tersimpan di riwayat shell
# atau
export OMI_API_KEY=omi_dev_...          # efemeral, cocok untuk kontainer
```

## Lima hal yang paling sering dilakukan agen

### 1. Membaca memori

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Membuat memori

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Membaca percakapan

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Membaca item tindakan terbuka

```bash
omi action-item list --json --open
```

### 5. Menandai item tindakan selesai

```bash
omi action-item complete --json a1b2c3d4
```

## API Desktop Lokal

Saat Omi Desktop mengekspos API lokalnya, agen dapat menanyakan riwayat layar
di perangkat, rekap, SQL, dan tugas tanpa menggunakan API pengembang cloud:

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

Hanya selesaikan atau hapus tugas jika pengguna memintanya secara jelas:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` menulis tangkapan layar ke
disk dan tetap mencetak JSON ke stdout untuk skrip. ID tangkapan layar biasanya
berasal dari `local search-screen` atau query SQL pada tabel `screenshots`. Jika Desktop
mengembalikan kegagalan terstruktur seperti `screenshot_pending`, `screenshot_file_missing`,
atau `screenshot_chunk_corrupted`, mode JSON mempertahankan bidang `reason`, `hint`, dan
`screenshot_id` pada stderr sehingga agen dapat mencoba kembali ID yang lebih lama atau melaporkan
penyebab pastinya. Validasi output yang berhasil dengan `file PATH` sebelum meneruskannya
ke alat penglihatan (vision tools).

## Contoh penerapan: Loop agen Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Memanggil CLI omi dalam mode JSON, menimbulkan exception jika kode keluar bukan nol."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI mencetak kesalahan terstruktur ke stderr dalam mode JSON:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi keluar dengan kode {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Membaca semua item tindakan yang terbuka dan menandai selesai yang lebih lama dari 30 hari.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Menangani batas kecepatan (rate limits)

Memori: 120/jam. Percakapan: 25/jam. Pembuatan batch: 15/jam.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # batas kecepatan terlampaui
    err = json.loads(result.stderr)
    # err["detail"] terlihat seperti: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Tips

* Gunakan `--profile <name>` jika agen Anda mengelola beberapa akun Omi. Setiap
  profil memiliki kredensial dan basis API masing-masing.
* Gunakan `--api-base http://localhost:8080` untuk pengujian backend lokal.
* Gunakan `OMI_LOCAL_API_URL` dan `OMI_LOCAL_TOKEN` untuk menimpa pengaturan
  API Desktop lokal profil untuk satu kali eksekusi.
* Gunakan `--verbose` untuk debugging — mencatat `METHOD path → status (Ns)` ke stderr
  tanpa memengaruhi stdout, sehingga mode JSON tetap valid.
* Untuk menyalurkan konten ke dalam percakapan menggunakan pipe, gunakan `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
