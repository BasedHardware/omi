# omi-cli untuk ejen

> Panduan praktikal untuk persekitaran dipacu LLM (Claude Code, Cursor, bot binaan anda sendiri).

## Mengapa CLI ini mesra ejen

* **Kontrak JSON yang stabil.** `--json` mengeluarkan dokumen JSON yang sah ke stdout dan
  *hanya* dokumen JSON — tiada mesej kemajuan, tiada animasi pemuat (spinners). Ralat disalurkan ke
  stderr sebagai `{"error": "...", "detail": "..."}`.
* **Kod keluar (exit codes) yang stabil.** `0` berjaya / `1` penggunaan tidak sah / `2` ralat autentikasi / `3` ralat pelayan / `4` had
  kadar dicapai (rate limited) / `5` tidak dijumpai. Ejen boleh mencabang logik berdasarkan kod ini tanpa perlu menghurai
  ralat bahasa semula jadi.
* **Tiada prom interaktif dalam konteks headless.** Sertakan `--yes` (atau `-y`) untuk
  arahan destruktif; sertakan `--api-key` atau tetapkan `OMI_API_KEY` untuk melangkau
  log masuk interaktif.
* **Tingkah laku percubaan semula yang bertolak ansur.** Ralat `429` dan `5xx` dicuba semula secara automatik
  dengan backoff eksponen sebelum dilemparkan.

## Autentikasi (sekali sahaja, dilakukan oleh manusia)

Pengguna mendapatkan kunci API pembangun daripada aplikasi web Omi
(`https://app.omi.me` → Developer → API Keys) dan melaksanakan salah satu daripada:

```bash
omi auth login                          # tampal secara interaktif; kunci tidak tersimpan dalam sejarah shell
# atau
export OMI_API_KEY=omi_dev_...          # efemeral, mesra kontena
```

## Lima perkara yang paling kerap dilakukan oleh ejen

### 1. Membaca memori (memories)

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

### 4. Membaca tindakan terbuka (action items)

```bash
omi action-item list --json --open
```

### 5. Menandakan tindakan sebagai selesai

```bash
omi action-item complete --json a1b2c3d4
```

## API Desktop Tempatan (Local Desktop API)

Apabila Omi Desktop mendedahkan API tempatannya, ejen boleh menyoal sejarah skrin
pada peranti, imbasan semula, SQL, dan tugasan tanpa perlu menggunakan API awan:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# atau, untuk sesi efemeral:
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

Hanya selesaikan atau padam tugasan apabila pengguna meminta secara jelas:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` menulis tangkapan skrin ke cakera
dan masih mencetak JSON ke stdout untuk kegunaan skrip. ID tangkapan skrin lazimnya
diperoleh daripada `local search-screen` atau pertanyaan SQL pada jadual `screenshots`. Jika Desktop
mengembalikan kegagalan berstruktur seperti `screenshot_pending`, `screenshot_file_missing`,
atau `screenshot_chunk_corrupted`, mod JSON mengekalkan medan `reason`, `hint`, dan
`screenshot_id` pada stderr supaya ejen boleh mencuba semula ID terdahulu atau melaporkan
penghalang sebenar. Sahkan output yang berjaya menggunakan `file PATH` sebelum diserahkan
kepada alatan penglihatan (vision tools).

## Contoh amali: Gelung ejen Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Panggil CLI omi dalam mod JSON, lontar ralat jika kod keluar bukan 0."""
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

# Baca semua tugasan terbuka dan tandakan yang melebihi 30 hari sebagai selesai.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Pengendalian had kadar (rate limits)

Memori: 120/jam. Perbualan: 25/jam. Ciptaan kelompok: 15/jam.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # had kadar dicapai
    err = json.loads(result.stderr)
    # err["detail"] berformat seperti: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Tip dan amalan terbaik

* Gunakan `--profile <nama>` jika ejen anda menguruskan pelbagai akaun Omi. Setiap
  profil mempunyai kelayakan dan pangkalan API tersendiri.
* Gunakan `--api-base http://localhost:8080` untuk ujian backend tempatan.
* Gunakan `OMI_LOCAL_API_URL` dan `OMI_LOCAL_TOKEN` untuk mengatasi tetapan profil tempatan
  API Desktop bagi satu larian.
* Gunakan `--verbose` untuk penyahpepijatan — ia mencatat `METHOD path → status (Ns)` ke stderr
  tanpa mengganggu stdout, mengekalkan kesahan mod JSON.
* Untuk menyalurkan kandungan ke dalam perbualan melalui paip (pipe), gunakan `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
