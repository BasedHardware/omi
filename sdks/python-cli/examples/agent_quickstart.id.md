# omi-cli untuk Agen

> Panduan praktis untuk harness berbasis LLM (Claude Code, Cursor, bot kustom Anda).

## Mengapa CLI ini ramah bagi agen

* **Kontrak JSON yang stabil.** Opsi `--json` memancarkan dokumen JSON yang valid ke stdout dan *hanya* dokumen JSON — tanpa pesan progres, tanpa animasi pemuatan (spinner). Kesalahan dikirim ke stderr sebagai `{"error": "...", "detail": "..."}`.
* **Kode keluar (exit codes) yang stabil.** `0` berhasil / `1` kesalahan penggunaan / `2` autentikasi / `3` kesalahan server / `4` pembatasan laju (rate limited) / `5` tidak ditemukan. Agen dapat melakukan percabangan logis pada kode-kode ini tanpa perlu mengurai kesalahan bahasa alami.
* **Tidak ada konfirmasi interaktif dalam konteks headless.** Teruskan `--yes` (atau `-y`) untuk perintah destruktif; teruskan `--api-key` atau tetapkan variabel lingkungan `OMI_API_KEY` untuk melewati proses login interaktif.
* **Perilaku coba ulang (retry) yang pemaaf.** Kesalahan `429` dan `5xx` dicoba ulang secara otomatis dengan backoff sebelum dimunculkan ke permukaan.

## Autentikasi (satu kali, oleh manusia)

Pengguna mendapatkan kunci API pengembang dari aplikasi web Omi (`https://app.omi.me` → Developer → API Keys) dan memilih salah satu langkah berikut:

```bash
omi auth login                          # tempel interaktif; kunci tidak tersimpan di riwayat shell
# atau
export OMI_API_KEY=omi_dev_...          # bersifat sementara, ramah kontainer
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

### 4. Membaca butir tindakan yang terbuka

```bash
omi action-item list --json --open
```

### 5. Menandai butir tindakan selesai

```bash
omi action-item complete --json a1b2c3d4
```

## API Desktop Lokal

Ketika Omi Desktop mengekspos API lokalnya, agen dapat menanyakan riwayat layar di perangkat, rekap, SQL, dan tugas tanpa menggunakan API dev cloud:

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

Hanya selesaikan atau hapus tugas ketika pengguna secara eksplisit memintanya:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

Perintah `omi local screenshot SCREENSHOT_ID --output PATH` menulis tangkapan layar ke disk dan tetap mencetak JSON ke stdout untuk skrip. ID tangkapan layar biasanya diperoleh dari `local search-screen` atau kueri SQL pada tabel `screenshots`. Jika Desktop mengembalikan kegagalan terstruktur seperti `screenshot_pending`, `screenshot_file_missing`, atau `screenshot_chunk_corrupted`, mode JSON mempertahankan bidang `reason`, `hint`, dan `screenshot_id` pada stderr sehingga agen dapat mencoba kembali dengan ID sebelumnya atau melaporkan kendala secara tepat. Validasi keluaran yang berhasil dengan `file PATH` sebelum meneruskannya ke alat visual.

## Contoh penerapan: Loop agen Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Memanggil omi CLI dalam mode JSON, memunculkan exception pada kode keluar yang tidak berhasil."""
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
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Membaca semua butir tindakan yang terbuka dan menandai butir yang lebih lama dari 30 hari sebagai selesai.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Menangani batas laju

Memori: 120/jam. Percakapan: 25/jam. Pembuatan batch: 15/jam.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # batas laju tercapai
    err = json.loads(result.stderr)
    # err["detail"] terlihat seperti: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Tips praktis

* Gunakan `--profile <name>` jika agen Anda mengelola beberapa akun Omi. Setiap profil memiliki kredensial dan basis API sendiri.
* Gunakan `--api-base http://localhost:8080` untuk pengujian backend lokal.
* Gunakan `OMI_LOCAL_API_URL` dan `OMI_LOCAL_TOKEN` untuk mengganti pengaturan Desktop API lokal profil dalam satu eksekusi.
* Gunakan `--verbose` untuk debugging — ini mencatat `METHOD path → status (Ns)` ke stderr tanpa memengaruhi stdout, sehingga mode JSON tetap valid.
* Untuk menyalurkan konten ke dalam percakapan, gunakan `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
