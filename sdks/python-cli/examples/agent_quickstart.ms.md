# omi-cli untuk agen

> Panduan praktikal untuk persekitaran yang dipacu LLM (Claude Code, Cursor, bot anda sendiri).

## Mengapa CLI mesra agen

* **Kontrak JSON yang stabil.** `--json` mengeluarkan dokumen JSON yang sah ke stdout dan *hanya* dokumen itu — tiada mesej kemajuan atau spinner. Ralat ditulis ke stderr sebagai `{"error": "...", "detail": "..."}`.
* **Kod keluar yang stabil.** `0` ok / `1` ralat penggunaan / `2` ralat kebenaran / `3` ralat pelayan / `4` had kadar / `5` tidak dijumpai. Agen boleh bercabang pada kod-kod ini tanpa menghurai bahasa semula jadi dalam mesej ralat.
* **Tiada gesaan interaktif dalam konteks headless.** Hantar `--yes` (atau `-y`) untuk arahan yang merosakkan; hantar `--api-key` atau tetapkan `OMI_API_KEY` untuk melangkau log masuk interaktif.
* **Logik cuba semula yang pemaaf.** `429` dan `5xx` dicuba semula dengan backoff eksponen sebelum dilaporkan.

## Pengesahan (sekali, oleh manusia)

Pengguna mendapatkan kunci API pembangun dari aplikasi web Omi (`https://app.omi.me` → Developer → API Keys) dan menjalankan salah satu daripada:

```bash
omi auth login                          # tampal interaktif; kunci tidak masuk ke sejarah shell
# oder / ou / ili / or / ή / veya / või / o / ale /
export OMI_API_KEY=omi_dev_...          # sementara, mesra kontena
```

## Lima perkara yang paling kerap dilakukan oleh agen

### 1. Baca kenangan

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Cipta kenangan

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Baca perbualan

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Baca item tindakan yang terbuka

```bash
omi action-item list --json --open
```

### 5. Tandakan item tindakan sebagai selesai

```bash
omi action-item complete --json a1b2c3d4
```

## API Desktop Tempatan

Apabila Omi Desktop mendedahkan API tempatannya, agen boleh membuat pertanyaan sejarah skrin pada peranti, ringkasan, SQL dan tugasan tanpa menggunakan API dev awan:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# sementara, mesra kontena:
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

Selesaikan atau padam tugasan hanya apabila pengguna meminta secara eksplisit:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` menyimpan tangkapan skrin ke cakera dan masih menulis JSON ke stdout untuk skrip. ID tangkapan skrin biasanya datang daripada `local search-screen` atau SQL pada jadual `screenshots`. Jika Desktop mengembalikan ralat berstruktur seperti `screenshot_pending`, `screenshot_file_missing` atau `screenshot_chunk_corrupted`, mod JSON memelihara medan `reason`, `hint` dan `screenshot_id` pada stderr supaya agen boleh mencuba semula dengan ID yang lebih lama atau melaporkan halangan yang tepat. Sahkan keputusan yang berjaya dengan `file PATH` sebelum menyerahkannya kepada alat penglihatan.

## Contoh praktikal: gelung agen Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Jalankan CLI omi dalam mod JSON dan lemparkan pengecualian pada kod keluar yang buruk."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI menulis ralat berstruktur ke stderr dalam mod JSON:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi keluar dengan kod {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Baca semua item tindakan yang terbuka dan tandakan yang lebih daripada 30 hari sebagai selesai.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Pengendalian had kadar

Kenangan: 120/jam. Perbualan: 25/jam. Penciptaan kelompok: 15/jam.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # had kadar
    err = json.loads(result.stderr)
    # err["detail"] kelihatan seperti: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Petua

* Gunakan `--profile <nama>` jika agen anda mengurus berbilang akaun Omi. Setiap profil mempunyai kelayakan dan pangkalan API tersendiri.
* Gunakan `--api-base http://localhost:8080` untuk ujian backend tempatan.
* Gunakan `OMI_LOCAL_API_URL` dan `OMI_LOCAL_TOKEN` untuk mengatasi tetapan API Desktop profil untuk satu pelaksanaan.
* Gunakan `--verbose` untuk penyahpepijatan — merekodkan `METHOD path → status (Ns)` ke stderr tanpa menjejaskan stdout, jadi mod JSON kekal sah.
* Untuk mengepam kandungan ke dalam perbualan, gunakan `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
