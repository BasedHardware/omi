# omi-cli kanggo agen

> Pandhuan praktis kanggo sistem sing digerakake LLM (Claude Code, Cursor, bot sampeyan dhewe).

## Apa sebab CLI iki ramah kanggo agen

* **Kontrak JSON sing stabil.** `--json` ngetokake dokumen JSON sing valid menyang stdout
  lan *mung* dokumen JSON — ora ana pesen kemajuan, ora ana spinner. Kesalahan menyang
  stderr minangka `{"error": "...", "detail": "..."}`.
* **Kode metu sing stabil.** `0` sukses / `1` panggunaan / `2` otentikasi /
  `3` server / `4` watesan kacepetan / `5` ora ketemu. Agen bisa nggawe cabang
  saka kode kasebut tanpa ngurai kesalahan basa alami.
* **Ora ana pituduh interaktif ing konteks headless.** Wenehake `--yes` (utawa `-y`)
  kanggo perintah sing ngrusak; wenehake `--api-key` utawa setel `OMI_API_KEY`
  kanggo ngliwati mlebu interaktif.
* **Prilaku nyoba maneh sing sabar.** `429` lan `5xx` dicoba maneh kanthi backoff
  sadurunge ditampilake.

## Otentikasi (sepisan, dening manungsa)

Pangguna entuk kunci API pangembang saka aplikasi web Omi
(`https://app.omi.me` → Developer → API Keys) lan banjur:

```bash
omi auth login                          # tempel interaktif; kunci ora ana ing riwayat shell
# utawa
export OMI_API_KEY=omi_dev_...          # ephemeral, cocok kanggo kontainer
```

## Lima perkara sing paling kerep ditindakake agen

### 1. Maca memori

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Nggawe memori

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Maca obrolan

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Maca item tumindak sing mbukak

```bash
omi action-item list --json --open
```

### 5. Nandai item tumindak rampung

```bash
omi action-item complete --json a1b2c3d4
```

## Local Desktop API

Nalika Omi Desktop mbukak API lokal, agen bisa takon riwayat layar ing piranti,
rekap, SQL, lan tugas tanpa nggunakake cloud dev API:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# utawa, kanggo sesi ephemeral:
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

Rampungake utawa busak tugas mung nalika pangguna kanthi jelas njaluk:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` nulis gambar layar menyang disk lan
tetep nyetak JSON menyang stdout kanggo skrip. ID gambar layar biasane asale saka
`local search-screen` utawa SQL liwat tabel `screenshots`. Yen Desktop ngasilake
kegagalan terstruktur kayata `screenshot_pending`, `screenshot_file_missing`, utawa
`screenshot_chunk_corrupted`, mode JSON njaga kolom `reason`, `hint`, lan `screenshot_id`
ing stderr supaya agen bisa nyoba ID sing luwih lawas utawa nglaporake blokir sing
persis. Validasi output sing sukses nganggo `file PATH` sadurunge dikirim menyang
alat visi.

## Conto kerja: loop agen Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Nglebokake CLI omi ing mode JSON, ngunggahake exception yen kode metu ora sukses."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI nyetak kesalahan terstruktur menyang stderr ing mode JSON:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Waca kabeh item tumindak sing mbukak lan tandai sing luwih lawas tinimbang 30 dina rampung.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Nangani watesan kacepetan

Memori: 120/jam. Obrolan: 25/jam. Nggawe batch: 15/jam.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # watesan kacepetan
    err = json.loads(result.stderr)
    # err["detail"] katon kaya: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Tips

* Gunakake `--profile <name>` yen agen sampeyan ngatur akeh akun Omi. Saben profil
  duwe kredensial lan basis API dhewe.
* Gunakake `--api-base http://localhost:8080` kanggo nguji backend lokal.
* Gunakake `OMI_LOCAL_API_URL` lan `OMI_LOCAL_TOKEN` kanggo ngatasi setelan Desktop API
  khusus profil kanggo siji wacana.
* Gunakake `--verbose` kanggo debugging — nyathet `METHOD path → status (Ns)` menyang
  stderr tanpa mengaruhi stdout, supaya mode JSON tetep valid.
* Kanggo nyalurake konten menyang obrolan, gunakake `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```