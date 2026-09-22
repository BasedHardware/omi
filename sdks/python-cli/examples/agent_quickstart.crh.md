# Agentler içün omi-cli

> LLM esaslı sistemler (Claude Code, Cursor, şahsiy botlarıñız) içün ameliy qılavuz.

## Ne içün CLI agentler içün qolay

* **Sabit JSON añlaşması.** `--json` parametri standart çıqışqa (stdout) doğru bir JSON
  vesiqasını ve *tek* bir JSON vesiqasını çıqarır — iç bir ilerilev bildirüvi ya da aylanğan
  animatsiya yoqtır. Hatalar standart hata aqımına (stderr) `{"error": "...", "detail": "..."}`
  şeklinde yollanır.
* **Sabit çıqış kodları (exit codes).** `0` muvafaqiyetli / `1` qullanuv hatası / `2` autentifikatsiya /
  `3` server hatası / `4` sıqlıq sıñırı (rate limited) / `5` tapılmadı. Agentler tabiiy tildaki
  hatalarnı ayırmadan doğrudan bu kodlarğa esaslanıp qarar bere bilir.
* **Başsız (headless) kontekstlerde interaktiv soravlarnıñ olmaması.** Deñiştirici buyruqlarğa
  `--yes` (ya da `-y`) beriñiz; interaktiv kirişni keçmek içün `--api-key` beriñiz ya da
  `OMI_API_KEY` muhit deñişkenini tayin etiñiz.
* **Yımşaq keri boysunuv usulı.** `429` ve `5xx` hataları ekranda kösterilmezden evel artqan
  kütüv aralıqları (backoff) ile avtomatik olaraq yañıdan teşkere etilir.

## Autentifikatsiya (insan tarafından bir kere)

Qullanıcı Omi veb qullanmasından developer API açarını ala
(`https://app.omi.me` → Developer → API Keys) ve şulardan birini saylay:

```bash
omi auth login                          # interaktiv yapıştırma; açar qabuq tarihında qalmay
# ya da
export OMI_API_KEY=omi_dev_...          # vaqtınca, konteynerler içün qolay
```

## Agentler eñ çoq yapqan beş ameliyat

### 1. Hatıralarnı oquv

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Hatıra yaratuv

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Qonuşmalarnı oquv

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Açıq areket maddelerini oquv

```bash
omi action-item list --json --open
```

### 5. Areket maddesini tamamlandı dep işaretlev

```bash
omi action-item complete --json a1b2c3d4
```

## Yerli Desktop API

Omi Desktop öz yerli API-sini faalleştirgende, agentler bulut developer API-sini qullanmayıp
cihazdaki ekran tarihını, hulasalarnı, SQL malümatlarını ve vazifelerni sorap bile:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# ya da vaqtınca seanslar içün:
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

Vazifelerni tek qullanıcı açıq-aydın sorağanda tamamlañız ya da yoq etiñiz:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` skrinşotnı diskke yaza ve skriptler içün
stdout-qa JSON çıqaruvnı devam ettire. Skrinşot identifikatorı adetince `local search-screen`
ya da `screenshots` cedveli boyunca SQL soravından alınır. Eger Desktop `screenshot_pending`,
`screenshot_file_missing` ya da `screenshot_chunk_corrupted` kibi tertipli muvafaqiyetsizlik
qaytarsa, JSON tertibi stderr-de `reason`, `hint` ve `screenshot_id` saalarını saqlay,
böylece agentler evelki ID ile yañıdan deñep baqa ya da qasevetni tam bildire bilir.
Muvafaqiyetli neticelerni körüv aletlerine bermezden evel `file PATH` ile teşkeriñiz.

## Ameliy misal: Python agent aylanması

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """omi CLI-ni JSON tertibinde çağırır, muvafaqiyetsiz çıqış kodlarında istisna doğura."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI JSON tertibinde stderr-ge tertipli hatalarnı çıqarır:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Bütün açıq areket maddelerini oquñız ve 30 künden eski olğanlarnı tamamlandı dep işaretleñiz.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Sıqlıq sıñırlarını idare etüv

Hatıralar: 120/saat. Qonuşmalar: 25/saat. Toplu yaratuvlar: 15/saat.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # sıqlıq sıñırı aşıldı
    err = json.loads(result.stderr)
    # err["detail"] böyle körüne: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Faydalı tevsieler

* Eger agentiñiz bir qaç Omi esabını idare etse, `--profile <ad>` qullanıñız.
  Er profilniñ öz kiriş malümatı ve esas API adresi bar.
* Yerli arqa taraf (backend) sınavları içün `--api-base http://localhost:8080` qullanıñız.
* Bir işletim içün profilniñ yerli Desktop API sazlamalarını deñiştirmek maqsadınen
  `OMI_LOCAL_API_URL` ve `OMI_LOCAL_TOKEN` qullanıñız.
* Sazlama (debugging) içün `--verbose` qullanıñız — bu stdout-qa tesir etmeyip stderr-ge
  `METHOD path → status (Ns)` qeyd ete, böylece JSON tertibi bozulmay.
* Qonuşma içine münderice yollamaq içün `--text -` qullanıñız:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
