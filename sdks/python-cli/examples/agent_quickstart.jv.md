# omi-cli kanggo agen

> Pandhuan praktis kanggo harness sing dienggo LLM (Claude Code, Cursor, bot dhewe).

## Kenapa CLI iki becik kanggo agen

* **Kontrak JSON stabil.** `--json` ngeluarake dokumen JSON bener ing stdout lan
  *mung* dokumen JSON — ora ana pesen kemajuan, ora ana spinner. Kesalahan menyang
  stderr minangka `{"error": "...", "detail": "..."}`.
* **Kode metu stabil.** `0` bener / `1` panggunaan / `2` auth / `3` server /
  `4` watesan kacepetan / `5` ora ketemu. Agen bisa milih ing ngono tanpa ngurutake
  kesalahan ing basa alami.
* **Ora ana prompt interaktif ing konteks headless.** Kirimake `--yes` (utawa `-y`)
  menyang perintah sing ngrusak; kirimake `--api-key` utawa setel `OMI_API_KEY`
  kanggo skip login interaktif.
* **Perilaku retry sing ngapura.** `429` lan `5xx` dicoba maneh nganggo backoff
  sadurunge muncul.

## Auth (sepisan, dening manungsa)

Panganggo njupuk kunci dev API saka aplikasi web Omi
(`https://app.omi.me` → Developer → API Keys) lan salah siji:

```bash
omi auth login                          # tempel interaktif; kunci ora tetep ing sejarah shell
# utawa
export OMI_API_KEY=omi_dev_...          # sementara, becik kanggo container
```

## Lima perkara sing paling akeh ditindakake agen

### 1. Maca memori

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Nggawe memori

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Maca guneman

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Maca item tumindak sing mbuka

```bash
omi action-item list --json --open
```

### 5. Tandhani item tumindak wis rampung

```bash
omi action-item complete --json a1b2c3d4
```

## API lokal Desktop

Nalika Omi Desktop mbukak API lokal, agen bisa takon babagan sejarah layar
perangkat, rekap, SQL, lan tugas tanpa nggunakake API dev cloud:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# utawa, kanggo sesi sementara:
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

Rampungake utawa busak tugas mung nalika panganggo njaluk kanthi jelas:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` nulis screenshot menyang disk
lan isih nyetak JSON menyang stdout kanggo skrip. ID screenshot biasane teka saka
`local search-screen` utawa SQL ing tabel `screenshots`. Yen Desktop bali kesalahan
terstruktur kayata `screenshot_pending`, `screenshot_file_missing`, utawa
`screenshot_chunk_corrupted`, mode JSON njaga kolom `reason`, `hint`, lan
`screenshot_id` ing stderr supaya agen bisa nyoba maneh ID sing luwih lawas utawa
nglaporake blok sing tepat. Validasi output sing sukses nganggo `file PATH`
sadurunge dikirimake menyang alat penglihatan.

## Conto digarap: loop agen Python

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

## Ngatur watesan kacepetan

Memori: 120/jam. Guneman: 25/jam. Nggawe batch: 15/jam.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Tips

* Gunakake `--profile <name>` yen agen ngatur akun Omi akeh. Saben profil nduweni
  kredensial lan basis API dhewe.
* Gunakake `--api-base http://localhost:8080` kanggo tes backend lokal.
* Gunakake `OMI_LOCAL_API_URL` lan `OMI_LOCAL_TOKEN` kanggo ngalahake setelan
  API lokal Desktop profil kanggo siji eksekusi.
* Gunakake `--verbose` kanggo debug — nyatet `METHOD path → status (Ns)` menyang
  stderr tanpa pengaruhi stdout, dadi mode JSON tetep valid.
* Kanggo ngalihake isi menyang guneman, gunakake `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
