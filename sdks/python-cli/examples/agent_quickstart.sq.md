# omi-cli për agjentët

> Udhëzues praktik për sisteme të drejtuara nga LLM (Claude Code, Cursor, bot-et tuaja).

## Pse CLI është miqësor për agjentët

* **Kontratë e qëndrueshme JSON.** `--json` lëshon një dokument të vlefshëm JSON në stdout dhe
  *vetëm* një dokument JSON — pa mesazhe progresi, pa rrotullues (spinners). Gabimet shkojnë në
  stderr si `{"error": "...", "detail": "..."}`.
* **Kode dalëse të qëndrueshme (Exit Codes).** `0` në rregull / `1` përdorim / `2` autentikim / `3` server / `4` kufi
  shpejtësie / `5` nuk u gjet. Agjentët mund të degëzohen mbi këto pa analizuar
  gabime të gjuhës natyrore.
* **Pa pyetje ndërvepruese në kontekste pa ekran (headless).** Kaloni `--yes` (ose `-y`) te
  komandat shkatërruese; kaloni `--api-key` ose vendosni `OMI_API_KEY` për të kapërcyer
  hyrjen ndërvepruese.
* **Sjellje ripërsëritëse falëse.** Gabimet `429` dhe `5xx` ripërsëriten me vonesë
  eksponenciale para se të shfaqen.

## Autentikimi (një herë, nga njeriu)

Përdoruesi merr një çelës API zhvilluesi nga aplikacioni në internet i Omi
(`https://app.omi.me` → Developer → API Keys) dhe ose:

```bash
omi auth login                          # ngjitje ndërvepruese; çelësi nuk mbetet në historikun e terminalit
# ose
export OMI_API_KEY=omi_dev_...          # i përkohshëm, miqësor për kontejnerë
```

## Pesë veprimet që agjentët bëjnë më shumë

### 1. Lexoni kujtimet

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Krijoni një kujtim

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Lexoni bisedat

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Lexoni veprimet e hapura

```bash
omi action-item list --json --open
```

### 5. Shënoni një veprim si të përfunduar

```bash
omi action-item complete --json a1b2c3d4
```

## API Lokale e Desktopit

Kur Omi Desktop ekspozon API-në e tij lokale, agjentët mund të kërkojnë historikun e ekranit
në pajisje, përmbledhjet, SQL dhe detyrat pa përdorur API-në e cloud-it:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# ose, për seanca të përkohshme:
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

Përfundoni ose fshini detyrat vetëm kur përdoruesi e kërkon qartë:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` shkruan pamjen e ekranit në
disk dhe përsëri printon JSON në stdout për skriptet. ID e pamjes së ekranit zakonisht
vjen nga `local search-screen` ose SQL mbi tabelën `screenshots`. Nëse Desktop
kthen një dështim të strukturuar si `screenshot_pending`, `screenshot_file_missing`,
ose `screenshot_chunk_corrupted`, modaliteti JSON ruan fushat `reason`, `hint` dhe
`screenshot_id` në stderr në mënyrë që agjentët të mund të riprovojnë një ID më të vjetër ose të raportojnë
pengesën e saktë. Vërtetoni daljet e suksesshme me `file PATH` përpara se t'i kaloni
te mjetet e vizionit.

## Shembull praktik: cikli i agjentit në Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Thirrni CLI omi në modalitetin JSON, duke ngritur gabim në kodet jo të suksesshme të daljes."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI printon gabime të strukturuara në stderr në modalitetin JSON:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Lexoni të gjitha veprimet e hapura dhe shënoni çdo gjë më të vjetër se 30 ditë si të përfunduar.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Menaxhimi i kufijve të kërkesave (Rate limits)

Kujtimet: 120/orë. Bisedat: 25/orë. Krijimet në grup: 15/orë.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # kufiri i kërkesave u arrit
    err = json.loads(result.stderr)
    # err["detail"] duket si: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Këshilla

* Përdorni `--profile <emri>` nëse agjenti juaj menaxhon disa llogari Omi. Çdo
  profil ka kredencialet dhe bazën e tij API.
* Përdorni `--api-base http://localhost:8080` për testimin e backend-it lokal.
* Përdorni `OMI_LOCAL_API_URL` dhe `OMI_LOCAL_TOKEN` për të anashkaluar cilësimet e Desktop API
  lokale të profilit për një ekzekutim.
* Përdorni `--verbose` për korrigjim gabimesh — regjistron `METHOD path → status (Ns)` në stderr
  pa ndikuar në stdout, kështu që modaliteti JSON mbetet i vlefshëm.
* Për të kaluar përmbajtje në një bisedë, përdorni `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
