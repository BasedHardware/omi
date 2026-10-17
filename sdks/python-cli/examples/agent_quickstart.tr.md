# omi-cli ajanlar için

> LLM destekli harness'lar için pratik rehber (Claude Code, Cursor, kendi botların).

## CLI neden ajan dostu

* **Kararlı JSON sözleşmesi.** `--json` stdout'a geçerli bir JSON belgesi ve *sadece* JSON yazar — ilerleme mesajı veya spinner yok. Hatalar stderr'a `{"error": "...", "detail": "..."}` olarak gider.
* **Kararlı çıkış kodları.** `0` ok / `1` kullanım / `2` auth / `3` sunucu / `4` rate limited / `5` bulunamadı. Ajanlar doğal dil hatalarını ayrıştırmadan bunlara göre dallanabilir.
* **Headless bağlamlarda etkileşimli istem yok.** Yıkıcı komutlara `--yes` (veya `-y`) verin; etkileşimli girişi atlamak için `--api-key` verin veya `OMI_API_KEY` ayarlayın.
* **Hoşgörülü yeniden deneme.** `429` ve `5xx` yüzeye çıkmadan önce geri çekilme ile yeniden denenir.

## Kimlik doğrulama (bir kez, insan tarafından)

Kullanıcı Omi web uygulamasından dev API key alır
(`https://app.omi.me` → Developer → API Keys) ve ya:

```bash
omi auth login                          # etkileşimli yapıştırma; key shell geçmişinde değil
# # veya
export OMI_API_KEY=omi_dev_...          # geçici, konteyner dostu
```

## Ajanların en çok yaptığı beş şey

### 1. Memories okuma

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Bir memory oluşturma

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Conversations okuma

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Açık action item'ları okuma

```bash
omi action-item list --json --open
```

### 5. Action item'ı tamamlandı işaretleme

```bash
omi action-item complete --json a1b2c3d4
```

## Yerel Desktop API

Omi Desktop yerel API'sini açtığında, ajanlar cihazdaki ekran geçmişini,
özetleri, SQL'i ve görevleri bulut dev API olmadan sorgulayabilir:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# # veya, geçici oturumlar için:
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

Görevleri yalnızca kullanıcı açıkça istediğinde tamamlayın veya silin:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` ekran görüntüsünü diske
yazar ve betikler için stdout'a JSON basmaya devam eder. Screenshot ID genellikle
`local search-screen` veya `screenshots` tablosuna SQL'den gelir. Desktop
`screenshot_pending`, `screenshot_file_missing` veya `screenshot_chunk_corrupted`
gibi yapılandırılmış bir hata döndürürse, JSON modu stderr'da `reason`, `hint` ve
`screenshot_id` alanlarını korur — böylece ajan eski bir ID deneyebilir veya tam
engeli bildirebilir. Başarılı çıktıları görüntü araçlarına vermeden önce `file
PATH` ile doğrulayın.

## Örnek: Python ajan döngüsü

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

# Tüm açık action item'ları oku ve 30 günden eski olanları tamamla.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Rate limit yönetimi

Memories: 120/saat. Conversations: 25/saat. Toplu oluşturma: 15/saat.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] şuna benzer: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## İpuçları

* Ajan birden fazla Omi hesabı yönetiyorsa `--profile <name>` kullanın. Her
  profilin kendi credential'ı ve API tabanı vardır.
* Yerel backend testleri için `--api-base http://localhost:8080` kullanın.
* Profil-yerel Desktop API ayarlarını tek bir çalıştırma için geçersiz kılmak
  üzere `OMI_LOCAL_API_URL` ve `OMI_LOCAL_TOKEN` kullanın.
* Hata ayıklamada `--verbose` kullanın — `METHOD path → status (Ns)` stderr'a
  loglar, stdout'u etkilemez, böylece JSON modu geçerli kalır.
* Conversation'a içerik pipelamak için `--text -` kullanın:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
