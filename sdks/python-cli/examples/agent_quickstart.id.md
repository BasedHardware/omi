# omi-cli untuk agen

> Panduan praktis untuk harness berbasis LLM (Claude Code, Cursor, bot Anda sendiri).

## Mengapa CLI ramah agen

* **Kontrak JSON yang stabil.** `--json` mengeluarkan dokumen JSON valid ke stdout dan *hanya* JSON — tanpa pesan kemajuan atau spinner. Error masuk ke stderr sebagai `{"error": "...", "detail": "..."}`.
* **Kode keluar yang stabil.** `0` ok / `1` penggunaan / `2` auth / `3` server / `4` rate limited / `5` tidak ditemukan. Agen dapat bercabang pada kode ini tanpa memparsing error bahasa alami.
* **Tanpa prompt interaktif di konteks headless.** Berikan `--yes` (atau `-y`) ke perintah destruktif; berikan `--api-key` atau setel `OMI_API_KEY` untuk melewati login interaktif.
* **Perilaku retry yang toleran.** `429` dan `5xx` dicoba ulang dengan backoff sebelum muncul.

## Autentikasi (sekali, oleh manusia)

Pengguna mendapatkan dev API key dari aplikasi web Omi
(`https://app.omi.me` → Developer → API Keys) lalu:

```bash
omi auth login                          # tempel interaktif; key tidak masuk riwayat shell
# # atau
export OMI_API_KEY=omi_dev_...          # sementara, ramah kontainer
```

## Lima hal yang paling sering dilakukan agen

### 1. Membaca memories

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Membuat memory

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Membaca conversations

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Membaca action item yang terbuka

```bash
omi action-item list --json --open
```

### 5. Menandai action item selesai

```bash
omi action-item complete --json a1b2c3d4
```

## API Desktop lokal

Ketika Omi Desktop membuka API lokalnya, agen dapat mengkueri riwayat
layar on-device, recap, SQL, dan task tanpa dev API cloud:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# # atau, untuk sesi singkat:
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

Selesaikan atau hapus task hanya saat pengguna meminta dengan jelas:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` menulis screenshot ke
disk dan tetap mencetak JSON ke stdout untuk skrip. Screenshot ID biasanya berasal
dari `local search-screen` atau SQL pada tabel `screenshots`. Jika Desktop
mengembalikan kegagalan terstruktur seperti `screenshot_pending`,
`screenshot_file_missing`, atau `screenshot_chunk_corrupted`, mode JSON mempertahankan
`reason`, `hint`, dan `screenshot_id` di stderr sehingga agen dapat mencoba ID
lama atau melaporkan penghalang yang tepat. Validasi output yang berhasil dengan
`file PATH` sebelum meneruskan ke alat visi.

## Contoh lengkap: loop agen Python

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

# Baca semua action item terbuka dan tandai selesai yang lebih tua dari 30 hari.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Menangani rate limit

Memories: 120/jam. Conversations: 25/jam. Pembuatan batch: 15/jam.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] berbentuk: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Tips

* Gunakan `--profile <name>` jika agen Anda menangani beberapa akun Omi. Setiap
  profil memiliki credential dan API base sendiri.
* Gunakan `--api-base http://localhost:8080` untuk pengujian backend lokal.
* Gunakan `OMI_LOCAL_API_URL` dan `OMI_LOCAL_TOKEN` untuk menimpa pengaturan
  Desktop API profil-lokal untuk satu proses.
* Gunakan `--verbose` untuk debugging — mencatat `METHOD path → status (Ns)`
  ke stderr tanpa memengaruhi stdout, sehingga mode JSON tetap valid.
* Untuk mem-pipe konten ke conversation, gunakan `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
