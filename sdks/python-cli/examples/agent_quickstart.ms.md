# omi-cli untuk agen AI

> Panduan praktikal untuk persekitaran dipacu LLM (Claude Code, Cursor, bot tersuai anda sendiri).

## Mengapa CLI mesra agen

* **Kontrak JSON stabil.** Bendera `--json` mengeluarkan dokumen JSON yang sah ke stdout dan
  *hanya* dokumen JSON — tiada mesej kemajuan, tiada pemutar pemuatan. Ralat dihantar ke
  stderr sebagai `{"error": "...", "detail": "..."}`.
* **Kod keluar stabil.** `0` ok / `1` penggunaan salah / `2` pengesahan / `3` pelayan /
  `4` had kadar melebihi / `5` tidak dijumpai. Agen boleh mencabang secara langsung berdasarkan
  kod ini tanpa menghuraikan mesej ralat bahasa tabii.
* **Tiada gesaan interaktif dalam konteks headless.** Hantar `--yes` (atau `-y`) untuk perintah
  pemusnah; hantar `--api-key` atau tetapkan `OMI_API_KEY` untuk melangkau log masuk interaktif.
* **Tingkah laku percubaan semula yang bertolak ansur.** Ralat jenis `429` dan `5xx` dicuba semula
  secara automatik dengan penangguhan eksponen (backoff) sebelum dilaporkan.

## Pengesahan (sekali sahaja, oleh manusia)

Pengguna mendapatkan kunci API pembangun daripada aplikasi web Omi
(`https://app.omi.me` → Developer → API Keys) dan melaksanakan salah satu daripada:

```bash
omi auth login                          # tampal interaktif; kunci tidak disimpan dalam sejarah shell
# atau
export OMI_API_KEY=omi_dev_...          # efemer, mesra kontena
```

## Lima perkara yang paling kerap dilakukan oleh agen

### 1. Membaca ingatan

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Mencipta ingatan

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Membaca perbualan

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Membaca item tindakan terbuka

```bash
omi action-item list --json --open
```

### 5. Menandakan item tindakan selesai

```bash
omi action-item complete --json a1b2c3d4
```

## API Desktop Tempatan

Apabila Omi Desktop mendedahkan API tempatannya, agen boleh menyoal sejarah skrin peranti,
ringkasan, SQL dan tugas tanpa menggunakan API dev awan:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# atau untuk sesi sementara:
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

Hanya selesaikan atau padamkan tugas apabila pengguna memintanya secara jelas:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

Perintah `omi local screenshot SCREENSHOT_ID --output PATH` menyimpan tangkapan skrin ke cakera
dan masih mencetak JSON ke stdout untuk skrip. ID tangkapan skrin biasanya diperoleh daripada
`local search-screen` atau pertanyaan SQL pada jadual `screenshots`. Jika Desktop mengembalikan
kegagalan berstruktur seperti `screenshot_pending`, `screenshot_file_missing` atau
`screenshot_chunk_corrupted`, mod JSON mengekalkan medan `reason`, `hint` dan `screenshot_id`
pada stderr supaya agen boleh mencuba ID yang lebih lama atau melaporkan halangan yang tepat.
Sahkan output yang berjaya dengan perintah `file PATH` sebelum menyerahkannya kepada alat penglihatan.

## Contoh praktikal: Gelung agen Python

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

## Mengendalikan had kadar (Rate Limits)

Ingatan: 120/jam. Perbualan: 25/jam. Penciptaan berkelompok: 15/jam.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Petua

* Gunakan `--profile <name>` jika agen anda menguruskan beberapa akaun Omi. Setiap
  profil mempunyai kelayakan dan pangkalan API tersendiri.
* Gunakan `--api-base http://localhost:8080` untuk ujian backend tempatan.
* Gunakan pemboleh ubah persekitaran `OMI_LOCAL_API_URL` dan `OMI_LOCAL_TOKEN` untuk mengatasi
  tetapan API Desktop profil tempatan untuk satu larian.
* Gunakan `--verbose` untuk penyahpepijatan — ia mencatat `METHOD path → status (Ns)` ke stderr
  tanpa mempengaruhi stdout, jadi mod JSON kekal sah.
* Untuk menyalurkan kandungan ke dalam perbualan, gunakan `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
