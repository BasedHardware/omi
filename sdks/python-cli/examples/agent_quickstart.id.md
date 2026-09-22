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

Selesaikan atau hapus tugas hanya jika pengguna memintanya secara eksplisit:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` menyimpan tangkapan layar ke disk dan tetap mencetak JSON ke stdout untuk skrip. ID tangkapan layar biasanya diperoleh dari `local search-screen` atau kueri SQL pada tabel `screenshots`. Jika Desktop mengembalikan kegagalan terstruktur seperti `screenshot_pending`, `screenshot_file_missing`, atau `screenshot_chunk_corrupted`, mode JSON mempertahankan bidang `reason`, `hint`, dan `screenshot_id` di stderr sehingga agen dapat mencoba lagi dengan ID yang lebih lama atau melaporkan kendala yang tepat. Validasi output yang berhasil dengan `file PATH` sebelum meneruskannya ke alat visual.

## Contoh Praktis: Loop Agen Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Invoke the omi CLI in JSON mode, raising on non-success exit codes."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # The CLI prints structured errors to stderr in JSON mode:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Read all open action items and mark anything older than 30 days complete.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Menangani Batas Kecepatan (Handling rate limits)

Memori: 120/jam. Percakapan: 25/jam. Pembuatan batch: 15/jam.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Tips (Tips)

* Gunakan `--profile <nama>` jika agen Anda mengelola beberapa akun Omi. Setiap profil memiliki kredensial dan basis API sendiri.
* Gunakan `--api-base http://localhost:8080` untuk pengujian backend lokal.
* Gunakan `OMI_LOCAL_API_URL` dan `OMI_LOCAL_TOKEN` untuk mengganti pengaturan Desktop API lokal profil untuk satu kali eksekusi.
* Gunakan `--verbose` untuk debugging — mencatat `METHOD path → status (Ns)` ke stderr tanpa memengaruhi stdout, sehingga mode JSON tetap valid.
* Untuk menyalurkan konten ke dalam percakapan melalui pipe, gunakan `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
