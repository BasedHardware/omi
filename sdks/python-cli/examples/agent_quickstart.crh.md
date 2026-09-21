# Agentler içün omi-cli (Crimean Tatar / Qırımtatarca)

> LLM esaslı sistemler (Claude Code, Cursor ve öz botlarıñız) içün ameliy qavuz.

## CLI ne içün agent-dostanesidir (Why the CLI is agent-friendly)

* **Sabit JSON añlaşması (Stable JSON contract).** `--json` çıqışı stdout-qa tek doğru bir JSON vesiqasını bere — ilerilev haberleri ve spinnerler yoq. Hatalar stderr-ge `{"error": "...", "detail": "..."}` şeklinde kete.
* **Sabit çıqış kodları (Stable exit codes).** `0` yahşı / `1` qullanuv hatası / `2` tasdıq / `3` server hatası / `4` sıqlıq sıñırlı / `5` tapılmadı. Agentler tabiiy til hatalarını tahlil etmeden bularğa esaslanıp qarar bere bilir.
* **Başsız kontekstlerde interaktiv soraşuvlar yoq (No interactive prompts in headless contexts).** Zararlı buyruqlar içün `--yes` (yaki `-y`) beriñiz; interaktiv kirişni keçmek içün `--api-key` beriñiz yaki `OMI_API_KEY` tayin etiñiz.
* **Afu etici kene sınaş tarzı (Forgiving retry behavior).** `429` ve `5xx` hataları ekranda körünmeden evel avtomatik tarzda kene sınaşuvlar ile idare etile.

## Tasdıq (insan tarafından, bir kere)

Qullanıcı Omi veb ilovasından (`https://app.omi.me` → Developer → API Keys) bir dev API açarını ala:

```bash
omi auth login                          # interaktiv yapıştırıv; açar qabıq keçmişinde qalmay
# yaki
export OMI_API_KEY=omi_dev_...          # vaqtınca, konteynerge uyğun
```

## Agentlerniñ eñ çoq yapqan beş işi

### 1. Hatıralarnı oquñız (Read memories)

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Hatıra meydanğa ketiriñiz (Create a memory)

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Laqırdılarnı oquñız (Read conversations)

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Açıq amel elementlerini oquñız (Read open action items)

```bash
omi action-item list --json --open
```

### 5. Amel elementini tamamlandı dep işaretleñiz (Mark an action item done)

```bash
omi action-item complete --json a1b2c3d4
```

## Yerli Desktop API (Local Desktop API)

Omi Desktop öz yerli API-sini qullanuvğa bergen vaqıtta, agentler bulut dev API-sini qullanmadan cihaz içi ekran keçmişini, qısqartmalarnı, SQL ve vazifelerni soray bilir:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# yaki, vaqtınca sessiyalar içün:
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

Vazifelerni tek qullanıcı açıq-aydın sorağan vaqıtta tamamlañız yaki yoq etiñiz:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` ekran kibi diskke saqlay ve skriptler içün stdout-qa JSON basıp çıqara. Desktop strukturalı bir hata qaytarsa (`screenshot_pending`, `screenshot_file_missing`, ya da `screenshot_chunk_corrupted`), JSON tarzı `reason`, `hint`, ve `screenshot_id` saalarını stderr üzerinde tuta.

## Ameliy misal: Python agent döngüsi (Worked example: Python agent loop)

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """omi CLI-ni JSON tarzında çağırıñız, muvafaqiyetsiz çıqış kodlarında istisna köteriñiz."""
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

# Bütün açıq amel elementlerini oquñız ve 30 künden eski şeylerni tamamlandı dep işaretleñiz.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Sıqlıq sıñırlarını idare etüv (Handling rate limits)

Hatıralar: 120/saat. Laqırdılar: 25/saat. Toplu yaratuvlar: 15/saat.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # sıqlıq sıñırlı
    err = json.loads(result.stderr)
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Faydalı tevsieler (Tips)

* Agentıñız bir qaç Omi esabını idare etse, `--profile <name>` qullanıñız.
* Yerli backend teşkerüvi içün `--api-base http://localhost:8080` qullanıñız.
* Desktop API sazlamalarını bir kere deñiştirmek içün `OMI_LOCAL_API_URL` ve `OMI_LOCAL_TOKEN` qullanıñız.
* Hatalarnı qıdırmaq içün `--verbose` qullanıñız — stdout-qa tesir etmeden stderr-ge yaza.
* Malümatnı laqırdığa iletmek içün `--text -` qullanıñız:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
