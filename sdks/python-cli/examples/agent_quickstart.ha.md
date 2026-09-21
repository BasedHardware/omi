# omi-cli don wakilai (Hausa)

> Jagora mai amfani ga tsarin da LLM ke jagoranta (Claude Code, Cursor, da bots dinka).

## Dalilin da ya sa CLI ke da saukin amfani ga wakilai (Why the CLI is agent-friendly)

* **Tabbataccen kwangilar JSON (Stable JSON contract).** `--json` yana fitar da ingantaccen takaddar JSON zuwa stdout kuma *kawai* takaddar JSON — babu sakonnin ci gaba, babu spinners. Kurakurai suna zuwa stderr a matsayin `{"error": "...", "detail": "..."}`.
* **Tabbatattun lambobin fita (Stable exit codes).** `0` lafiya / `1` kuskuren amfani / `2` tabbatarwa / `3` kuskuren sabar / `4` an iyakance sauri / `5` ba a samu ba. Wakilai za su iya rarrabuwa akan wadannan ba tare da fassara kurakuran harshen halitta ba.
* **Babu tambayoyi a yanayin da babu allo (No interactive prompts in headless contexts).** Shigar da `--yes` (ko `-y`) don umarni masu hallakarwa; shigar da `--api-key` ko saita `OMI_API_KEY` don tsallake shiga ta tambayoyi.
* **Sake gwadawa cikin sauki (Forgiving retry behavior).** Ana sake gwada kuskuren `429` da `5xx` tare da backoff kafin nunawa.

## Tabbatarwa (sau daya, daga mutum)

Mai amfani yana samun maɓallin dev API daga manhajar gidan yanar gizon Omi (`https://app.omi.me` → Developer → API Keys) kuma ko dai:

```bash
omi auth login                          # liƙa ta hanyar tambaya; mabuɗin baya zama a tarihin shell
# ko
export OMI_API_KEY=omi_dev_...          # na dan lokaci, ya dace da akwati (container)
```

## Abubuwa biyar da wakilai suka fi yi akai-akai

### 1. Karanta abubuwan tunawa (Read memories)

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Kirkiri abin tunawa (Create a memory)

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Karanta tattaunawa (Read conversations)

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Karanta ayyukan da ke bude (Read open action items)

```bash
omi action-item list --json --open
```

### 5. Sanya alamar an gama aiki (Mark an action item done)

```bash
omi action-item complete --json a1b2c3d4
```

## Desktop API na gida (Local Desktop API)

Lokacin da Omi Desktop ke bayar da API na gida, wakilai na iya tambayar tarihin allon na'ura, taƙaitawa, SQL, da ayyuka ba tare da amfani da gajimaren dev API ba:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# ko, don zaman dan lokaci:
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

Kawai kammala ko share ayyuka lokacin da mai amfani ya nema a fili:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` yana rubuta hoton allo zuwa diski kuma yana buga JSON zuwa stdout don rubutun. Idan Desktop ya dawo da gazawa mai tsari (kamar `screenshot_pending`, `screenshot_file_missing`, ko `screenshot_chunk_corrupted`), yanayin JSON yana adana `reason`, `hint`, da filayen `screenshot_id` akan stderr.

## Misali mai aiki: Python agent loop

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Kira omi CLI a yanayin JSON, yana daga kuskure akan lambar fita da ba ta yi nasara ba."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Karanta duk buɗaɗɗen abubuwan aiki kuma sanya alamar waɗanda suka haura kwanaki 30 a matsayin cikakku.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Sarrafa iyakar sauri (Handling rate limits)

Abubuwan tunawa: 120/awa. Tattaunawa: 25/awa. Kirkirar rukuni: 15/awa.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Shawarwari (Tips)

* Yi amfani da `--profile <name>` idan wakilinka yana sarrafa asusun Omi da yawa.
* Yi amfani da `--api-base http://localhost:8080` don gwajin backend na gida.
* Yi amfani da `OMI_LOCAL_API_URL` da `OMI_LOCAL_TOKEN` don soke saitunan API na Desktop.
* Yi amfani da `--verbose` don gano kurakurai — yana yin rikodin zuwa stderr ba tare da shafar stdout ba.
* Don tura abun ciki zuwa tattaunawa, yi amfani da `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
