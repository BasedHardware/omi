# Агентуудад зориулсан omi-cli

> LLM-д суурилсан харнес (Claude Code, Cursor, таны өөрийн ботууд) -д зориулсан практик гарын авлага.

## CLI яагаад агентуудад ээлтэй вэ

* **Тогтвортой JSON гэрээ.** `--json` нь stdout руу зөвхөн нэг хүчинтэй JSON баримт
  илгээдэг — *зөвхөн* JSON баримт — ямар ч явцын мэдэгдэл, спиннер байхгүй. Алдаанууд
  stderr руу `{"error": "...", "detail": "..."}` хэлбэрээр явдаг.
* **Тогтвортой exit код.** `0` амжилттай / `1` хэрэглээ / `2` баталгаажуулалт /
  `3` сервер / `4` хурдны хязгаар / `5` олдоогүй. Агентууд байгалийн хэлний
  алдаануудыг задлан шинжлэхгүйгээр эдгээр код дээр салбарлаж болно.
* **Headless орчинд интерактив промпт байхгүй.** Хор хөнөөлтэй командуудад
  `--yes` (эсвэл `-y`) дамжуулна; интерактив нэвтрэлтийг алгасахын тулд `--api-key`
  дамжуулах эсвэл `OMI_API_KEY` тохируулна уу.
* **Уучлах сэтгэлгээтэй дахин оролдлого.** `429` болон `5xx` нь илрэхээс өмнө
  backoff-тойгоор дахин оролдогддог.

## Баталгаажуулалт (нэг удаа, хүнээр)

Хэрэглэгч Omi вэб аппаас (`https://app.omi.me` → Developer → API Keys) dev API
түлхүүр авч, дараах хоёрын аль нэгийг хийнэ:

```bash
omi auth login                          # интерактив буулгалт; түлхүүр shell түүхэд үлдэхгүй
# эсвэл
export OMI_API_KEY=omi_dev_...          # түр зуурын, контейнерт ээлтэй
```

## Агентуудын хамгийн их хийдэг таван зүйл

### 1. Дурсамжуудыг унших

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Дурсамж үүсгэх

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Яриа унших

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Нээлттэй үйлдэл даалгавруудыг унших

```bash
omi action-item list --json --open
```

### 5. Үйлдэл даалгаврыг дууссан гэж тэмдэглэх

```bash
omi action-item complete --json a1b2c3d4
```

## Локал Desktop API

Omi Desktop өөрийн локал API-г нээх үед агентууд үүлэн dev API ашиглахгүйгээр
төхөөрөмж дээрх дэлгэцийн түүх, тойм, SQL болон даалгавруудыг асууж болно:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# эсвэл, түр зуурын сессүүдэд:
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

Зөвхөн хэрэглэгч тодорхой хүсэх үед даалгаврыг дуусгах эсвэл устгах:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` нь дэлгэцийн зургийг диск руу
бичиж, скриптүүдэд зориулж stdout руу JSON хэвлэсээр байна. Дэлгэцийн зургийн ID нь
ихэвчлэн `local search-screen` эсвэл `screenshots` хүснэгт дээрх SQL-ээс гардаг.
Хэрэв Desktop `screenshot_pending`, `screenshot_file_missing` эсвэл
`screenshot_chunk_corrupted` гэх мэт бүтэцтэй алдаа буцаавал JSON горим нь stderr
дээр `reason`, `hint`, `screenshot_id` талбаруудыг хадгалдаг тул агентууд хуучин ID-г
дахин оролдох эсвэл яг саадыг мэдээлэх боломжтой. Амжилттай гаралтыг vision
хэрэгслүүдэд дамжуулахаас өмнө `file PATH` ашиглан баталгаажуулна уу.

## Ажилласан жишээ: Python агентын цикл

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """omi CLI-г JSON горимд дуудаж, амжилтгүй exit код дээр алдаа гаргана."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI нь JSON горимд бүтэцтэй алдааг stderr руу хэвлэдэг:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Бүх нээлттэй үйлдэл даалгавруудыг уншиж, 30 хоногоос хуучин бүхнийг дууссан гэж тэмдэглэнэ.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Хурдны хязгаарыг зохицуулах

Дурсамж: 120/цаг. Яриа: 25/цаг. Бөөн үүсгэлт: 15/цаг.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # хурдны хязгаар
    err = json.loads(result.stderr)
    # err["detail"] иймэрхүү харагдана: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Зөвлөмжүүд

* Хэрэв таны агент олон Omi бүртгэл удирддаг бол `--profile <name>` ашиглана уу.
  Профайл бүр өөрийн итгэмжлэл болон API баазтай.
* Локал backend тестлэхэд `--api-base http://localhost:8080` ашиглана уу.
* Нэг удаагийн ажиллагаанд профайлын локал Desktop API тохиргоог дарж бичихийн
  тулд `OMI_LOCAL_API_URL` болон `OMI_LOCAL_TOKEN` ашиглана уу.
* Дебаг хийхэд `--verbose` ашиглана уу — энэ нь stdout-д нөлөөлөхгүйгээр stderr руу
  `METHOD path → status (Ns)` бүртгэдэг тул JSON горим хүчинтэй хэвээр байна.
* Яриа руу контент дамжуулахын тулд `--text -` ашиглана уу:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
