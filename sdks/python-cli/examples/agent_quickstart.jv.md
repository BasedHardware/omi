# omi-cli kanggo agen

> Pandhuan praktis kanggo harness sing dipandu LLM (Claude Code, Cursor, bot-bot panjenengan dhéwé).

## Apa sebabé CLI iki ramah kanggo agen

* **Kontrak JSON stabil.** `--json` ngetokaké dokumèn JSON sing sah menyang stdout lan
  *mung* dokumèn JSON — ora ana pesen progres, ora ana spinner. Kasalahan dikirim menyang
  stderr kanthi wujud `{"error": "...", "detail": "..."}`.
* **Kodhe metu stabil.** `0` suksès / `1` panggunaan / `2` otentikasi / `3` server / `4`
  kena watesan rate / `5` ora ditemokaké. Agen bisa nyabang adhedhasar iki tanpa
  mbedhah kasalahan basa alam.
* **Ora ana pituduh interaktif ing konteks headless.** Tambahna `--yes` (utawa `-y`) kanggo
  printah sing ngrusak; tambahna `--api-key` utawa set `OMI_API_KEY` kanggo ngliwati
  login interaktif.
* **Prilaku nyoba manèh sing sabar.** `429` lan `5xx` dicoba manèh nganggo backoff
  sadurungé metu.

## Otentikasi (sepisan, déning manungsa)

Pangguna njupuk kunci API dev saka aplikasi web Omi
(`https://app.omi.me` → Developer → API Keys) banjur milih salah siji:

```bash
omi auth login                          # tempelan interaktif; kunci ora mlebu riwayat shell
# utawa
export OMI_API_KEY=omi_dev_...          # sauntara, cocog kanggo kontainer
```

## Lima perkara sing paling kerep dilakoni agen

### 1. Maca memori

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Nggawé memori

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Maca obrolan

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Maca item tumindak sing isih mbukak

```bash
omi action-item list --json --open
```

### 5. Nandhani item tumindak wis rampung

```bash
omi action-item complete --json a1b2c3d4
```

## API Desktop Lokal

Nalika Omi Desktop mbukak API lokalé, agen bisa takon riwayat layar ing piranti,
rekap, SQL, lan tugas tanpa nganggo API dev cloud:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# utawa, kanggo sesi sauntara:
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

Rampungna utawa busakna tugas mung nalika pangguna kanthi cetha njaluk:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` nulis gambar layar menyang
disk lan tetep nyithak JSON menyang stdout kanggo skrip. ID gambar layar biasané
teka saka `local search-screen` utawa SQL ing tabel `screenshots`. Yèn Desktop
mbalèkaké gagal terstruktur kayata `screenshot_pending`, `screenshot_file_missing`,
utawa `screenshot_chunk_corrupted`, mode JSON njaga kolom `reason`, `hint`, lan
`screenshot_id` ing stderr supaya agen bisa nyoba manèh nganggo ID sing luwih
lawas utawa nglapuraké alangan sing tepat. Validasi output sing suksès nganggo
`file PATH` sadurungé dikirim menyang piranti vision.

## Conto nyata: loop agen Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Nelukake CLI omi ing mode JSON, mbuwang pangecualian nalika kodhe metu ora suksès."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI nyithak kasalahan terstruktur menyang stderr ing mode JSON:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Maca kabèh item tumindak sing mbukak lan tandhani sing luwih saka 30 dina wis rampung.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Nangani watesan rate

Memori: 120/jam. Obrolan: 25/jam. Gawé massal: 15/jam.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # kena watesan rate
    err = json.loads(result.stderr)
    # err["detail"] katon kaya: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Tip

* Gunakna `--profile <name>` yèn agen panjenengan ngatur sawetara akun Omi. Saben
  profil nduwé kredensial lan API base dhéwé.
* Gunakna `--api-base http://localhost:8080` kanggo uji coba backend lokal.
* Gunakna `OMI_LOCAL_API_URL` lan `OMI_LOCAL_TOKEN` kanggo ngganti setelan
  API Desktop profil kanggo sepisan jalan.
* Gunakna `--verbose` kanggo debugging — iki nyathet `METHOD path → status (Ns)` menyang stderr
  tanpa ngganggu stdout, dadi mode JSON tetep sah.
* Kanggo nglebokaké konten menyang obrolan nganggo pipe, gunakna `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
