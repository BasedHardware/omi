# omi-cli untuk ejen

> Panduan praktikal untuk persekitaran dipacu LLM (Claude Code, Cursor, bot anda sendiri).

## Mengapa CLI mesra ejen

* **Kontrak JSON yang stabil.** `--json` mengeluarkan dokumen JSON yang sah ke stdout dan
  *hanya* dokumen JSON — tiada mesej kemajuan, tiada animasi pemutar (spinners). Ralat dihantar ke
  stderr sebagai `{"error": "...", "detail": "..."}`.
* **Kod keluar yang stabil.** `0` ok / `1` penggunaan / `2` pengesahan / `3` pelayan / `4` had
  kadar / `5` tidak dijumpai. Ejen boleh membuat percabangan berdasarkan kod ini tanpa perlu menghuraikan
  ralat bahasa semula jadi.
* **Tiada gesaan interaktif dalam konteks headless.** Sertakan `--yes` (atau `-y`) untuk
  arahan pemusnah; sertakan `--api-key` atau tetapkan `OMI_API_KEY` untuk melangkau
  log masuk interaktif.
* **Tingkah laku percubaan semula yang bertoleransi.** Ralat `429` dan `5xx` dicuba semula secara automatik dengan undur masa (backoff)
  sebelum dikembalikan.

## Pengesahan (sekali sahaja, oleh manusia)

Pengguna mendapatkan kunci API pembangun daripada aplikasi web Omi
(`https://app.omi.me` → Developer → API Keys) dan memilih salah satu:

```bash
omi auth login                          # tampalan interaktif; kunci tidak disimpan dalam sejarah shell
# atau
export OMI_API_KEY=omi_dev_...          # bersifat sementara, mesra bekas (container)
```

## Lima tindakan yang paling kerap dilakukan oleh ejen

### 1. Membaca memori

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Mencipta memori

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

### 5. Menandakan item tindakan sebagai selesai

```bash
omi action-item complete --json a1b2c3d4
```

## API Desktop Tempatan

Apabila Omi Desktop mendedahkan API tempatannya, ejen boleh menanyakan sejarah
skrin pada peranti, rumusan, SQL dan tugasan tanpa menggunakan API pembangun awan:

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

Hanya selesaikan atau padamkan tugasan apabila diminta secara jelas oleh pengguna:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` menulis tangkapan skrin ke
cakera dan masih mencetak JSON ke stdout untuk skrip. ID tangkapan skrin biasanya
diperoleh daripada `local search-screen` atau pertanyaan SQL pada jadual `screenshots`. Jika Desktop
mengembalikan kegagalan berstruktur seperti `screenshot_pending`, `screenshot_file_missing`
atau `screenshot_chunk_corrupted`, mod JSON mengekalkan medan `reason`, `hint` dan
`screenshot_id` pada stderr supaya ejen boleh mencuba semula dengan ID yang lebih lama atau melaporkan
halangan sebenar. Sahkan output yang berjaya menggunakan `file PATH` sebelum menyerahkannya
kepada alat penglihatan (vision tools).

## Contoh praktikal: Gelung ejen Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Panggil omi CLI dalam mod JSON, mencetuskan pengecualian bagi kod keluar bukan sifar."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI mencetak ralat berstruktur ke stderr dalam mod JSON:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi keluar dengan kod {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Baca semua item tindakan terbuka dan tandakan mana-mana yang berusia lebih daripada 30 hari sebagai selesai.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Mengendalikan had kadar (rate limits)

Memori: 120/jam. Perbualan: 25/jam. Cipta kelompok: 15/jam.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # had kadar dicapai
    err = json.loads(result.stderr)
    # err["detail"] kelihatan seperti: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Petua berguna

* Gunakan `--profile <nama>` jika ejen anda menguruskan beberapa akaun Omi. Setiap
  profil mempunyai kelayakan dan pangkalan API sendiri.
* Gunakan `--api-base http://localhost:8080` untuk ujian backend tempatan.
* Gunakan `OMI_LOCAL_API_URL` dan `OMI_LOCAL_TOKEN` untuk mengatasi tetapan
  API Desktop profil tempatan bagi satu larian.
* Gunakan `--verbose` untuk penyahpepijatan — ia melog `METHOD path → status (Ns)` ke stderr
  tanpa menjejaskan stdout, memastikan mod JSON kekal sah.
* Untuk menyalurkan (pipe) kandungan ke dalam perbualan, gunakan `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
