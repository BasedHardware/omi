# omi-cli don Agent

> Jagora mai amfani don tsarin da LLM ke jagoranta (Claude Code, Cursor, bots ɗinka na kanka).

## Me yasa CLI ke da sauƙi ga Agent

* **Yarjejeniyar JSON mai karko.** `--json` yana fitar da ingantaccen daftarin JSON zuwa stdout
  kuma daftarin JSON *kaɗai* — babu saƙonnin ci gaba, babu raye-rayen lodi. Kurakurai suna zuwa
  stderr a matsayin `{"error": "...", "detail": "..."}`.
* **Lambar fita (exit codes) mai karko.** `0` lafiya / `1` kuskuren amfani / `2` tabbatarwa /
  `3` kuskuren uwar garke / `4` an iyakance ƙimar buƙata (rate limited) / `5` ba a samu ba.
  Agent na iya yanke shawara kai tsaye akan waɗannan lambobi ba tare da buƙatar fassara
  kurakurai a cikin yaren halitta ba.
* **Babu tambayoyi a cikin mahallin da ba shi da allo (headless).** Sanya `--yes` (ko `-y`)
  zuwa umarnin da ke yin canje-canje; sanya `--api-key` ko saita `OMI_API_KEY` don tsallake
  shiga ta hanyar tattaunawa.
* **Hanyar sake gwadawa mai sauƙi.** Kurakurai na `429` da `5xx` ana sake gwada su ta atomatik
  tare da ɗan jinkiri (backoff) kafin a nuna su.

## Tabbatar da shaida (sau ɗaya kawai, ta mutum)

Mai amfani yana karɓar maɓallin API na developer daga manhajar gidan yanar gizon Omi
(`https://app.omi.me` → Developer → API Keys) sannan ya zaɓi ɗaya daga cikin waɗannan:

```bash
omi auth login                          # manna ta hanyar tattaunawa; maɓallin baya shiga tarihin shell
# ko
export OMI_API_KEY=omi_dev_...          # na ɗan lokaci, ya dace da container
```

## Abubuwa biyar da Agent suka fi yi akai-akai

### 1. Karanta tunani (memories)

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Ƙirƙiri tunani

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Karanta tattaunawa

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Karanta buɗaɗɗun abubuwan aiki

```bash
omi action-item list --json --open
```

### 5. Alamar an kammala abu na aiki

```bash
omi action-item complete --json a1b2c3d4
```

## Desktop API na gida (Local Desktop API)

Lokacin da Omi Desktop ya kunna API ɗin sa na gida, agent na iya tambayar tarihin allon na'urar,
taƙaitawa, bayanan SQL da ayyuka ba tare da amfani da developer API na gajimare ba:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# ko don zama na ɗan lokaci:
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

Kammala ko share ayyuka kawai lokacin da mai amfani ya buƙaci hakan a sarari:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` yana rubuta hoton allo zuwa diski kuma
yana ci gaba da fitar da JSON zuwa stdout don rubutun shirye-shirye. Lambar ID na hoton allo
yawanci yana fitowa ne daga `local search-screen` ko tambayar SQL akan teburin `screenshots`.
Idan Desktop ya dawo da gazawa mai tsari kamar `screenshot_pending`, `screenshot_file_missing`
ko `screenshot_chunk_corrupted`, tsarin JSON yana riƙe filayen `reason`, `hint` da `screenshot_id`
akan stderr domin agent su sake gwadawa da tsohon ID ko kuma su ba da rahoton ainihin matsalar.
Tabbatar da sakamako mai nasara tare da `file PATH` kafin tura su zuwa kayan aikin gani.

## Misali mai aiki: Python agent loop

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Yana kiran omi CLI a yanayin JSON, yana tayar da kuskure akan lambobin fita marasa nasara."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI yana fitar da tsarin kurakurai zuwa stderr a yanayin JSON:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Karanta duk buɗaɗɗun abubuwan aiki kuma yi alamar an kammala waɗanda suka wuce kwanaki 30.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Sarrafa iyakar ƙimar buƙata (Rate Limits)

Tunani: 120/awa. Tattaunawa: 25/awa. Ƙirƙirar rukuni: 15/awa.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # an wuce ƙimar buƙata
    err = json.loads(result.stderr)
    # err["detail"] yana kama da: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Nasihu masu amfani

* Yi amfani da `--profile <name>` idan agent ɗinka yana sarrafa asusun Omi da yawa.
  Kowane bayanin martaba yana da takaddun shaidar kansa da tushen API.
* Yi amfani da `--api-base http://localhost:8080` don gwajin uwar garke na gida.
* Yi amfani da `OMI_LOCAL_API_URL` da `OMI_LOCAL_TOKEN` don soke saitunan Desktop API na gida na gudu ɗaya.
* Yi amfani da `--verbose` don gyara kuskure (debugging) — yana rubuta `METHOD path → status (Ns)`
  zuwa stderr ba tare da shafar stdout ba, don haka tsarin JSON ya kasance mai inganci.
* Don tura abun ciki zuwa tattaunawa, yi amfani da `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
