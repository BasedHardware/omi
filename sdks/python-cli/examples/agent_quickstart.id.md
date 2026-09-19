# omi-cli untuk agent

> Panduan praktis untuk sistem berbasis LLM (Claude Code, Cursor, bot kustom Anda).

## Mengapa CLI ini ramah bagi agent

* **Kontrak JSON yang stabil.** `--json` memancarkan dokumen JSON yang valid ke stdout dan
  *hanya* dokumen JSON — tanpa pesan progres, tanpa animasi spinner. Kesalahan dikirim ke
  stderr sebagai `{"error": "...", "detail": "..."}`.
* **Kode keluar yang stabil.** `0` berhasil / `1` kesalahan penggunaan / `2` autentikasi /
  `3` kesalahan server / `4` terkena batas laju / `5` tidak ditemukan. Agent dapat membuat percabangan
  berdasarkan kode ini tanpa perlu mengurai pesan kesalahan bahasa alami.
* **Tidak ada prompt interaktif di lingkungan headless.** Teruskan `--yes` (atau `-y`) untuk perintah
  yang bersifat destruktif; teruskan `--api-key` atau atur `OMI_API_KEY` untuk melewati login interaktif.
* **Perilaku coba ulang yang toleran.** Kesalahan `429` dan `5xx` dicoba ulang secara otomatis dengan
  backoff sebelum ditampilkan.

## Autentikasi (satu kali, oleh manusia)

Pengguna mengambil dev API key dari aplikasi web Omi
(`https://app.omi.me` → Developer → API Keys) lalu memilih salah satu cara:

```bash
omi auth login                          # tempel interaktif; kunci tidak tercatat di riwayat shell
# atau
export OMI_API_KEY=omi_dev_...          # bersifat sementara, ramah kontainer
```

## Lima hal yang paling sering dilakukan agent

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

### 4. Membaca daftar item tindakan terbuka

```bash
omi action-item list --json --open
```

### 5. Menandai item tindakan selesai

```bash
omi action-item complete --json a1b2c3d4
```

## API Desktop Lokal

Ketika Omi Desktop membuka API lokalnya, agent dapat menanyakan riwayat layar perangkat,
rekapitulasi, SQL, dan tugas tanpa perlu menggunakan cloud dev API:

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

Hanya tandai selesai atau hapus tugas ketika pengguna memintanya secara jelas:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` menulis tangkapan layar ke disk dan
tetap mencetak JSON ke stdout untuk konsumsi skrip. ID tangkapan layar biasanya berasal dari
`local search-screen` atau kueri SQL pada tabel `screenshots`. Jika Desktop mengembalikan
kesalahan terstruktur seperti `screenshot_pending`, `screenshot_file_missing`, atau
`screenshot_chunk_corrupted`, mode JSON mempertahankan kolom `reason`, `hint`, dan `screenshot_id`
pada stderr sehingga agent dapat mencoba ulang dengan ID yang lebih lama atau melaporkan kendala
secara tepat. Validasi hasil yang berhasil dengan `file PATH` sebelum meneruskannya ke vision tools.

## Contoh praktis: perulangan agent Python

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

## Menangani batas laju panggilan (rate limits)

Memori: 120/jam. Percakapan: 25/jam. Pembuatan batch: 15/jam.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Tips

* Gunakan `--profile <nama>` jika agent Anda mengelola beberapa akun Omi sekaligus.
  Setiap profil memiliki kredensial dan basis API tersendiri.
* Gunakan `--api-base http://localhost:8080` untuk pengujian backend lokal.
* Gunakan `OMI_LOCAL_API_URL` dan `OMI_LOCAL_TOKEN` untuk menimpa setelan Desktop API
  lokal profil untuk satu kali eksekusi.
* Gunakan `--verbose` untuk debugging — ini mencatat `METHOD path → status (Ns)` ke stderr
  tanpa mempengaruhi stdout, sehingga mode JSON tetap valid.
* Untuk mengalirkan (pipe) konten ke dalam percakapan, gunakan `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
