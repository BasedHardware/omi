# omi-cli ajanlar için

> LLM güdümlü harness'lar (Claude Code, Cursor, kendi bot'ların) için pratik bir rehber.

## CLI neden ajan dostu

* **Kararlı JSON sözleşmesi.** `--json`, stdout'a geçerli bir JSON belgesi yazar ve
  *yalnızca* bir JSON belgesi yazar — ilerleme mesajı yok, spinner yok. Hatalar
  stderr'e `{"error": "...", "detail": "..."}` olarak gider.
* **Kararlı çıkış kodları.** `0` ok / `1` kullanım / `2` auth / `3` server / `4`
  rate limited / `5` bulunamadı. Ajanlar doğal dil hatalarını ayrıştırmadan
  bunlara göre dallanabilir.
* **Headless bağlamlarda etkileşimli istem yok.** Yıkıcı komutlara `--yes` (veya `-y`)
  geçirin; etkileşimli girişi atlamak için `--api-key` geçirin veya `OMI_API_KEY` ayarlayın.
* **Yapışkan yeniden deneme davranışı.** `429` ve `5xx`, yüzeye çıkmadan önce
  backoff ile yeniden denenir.

## Auth (bir kez, insan tarafından)

Kullanıcı Omi web uygulamasından bir geliştirici API anahtarı alır
(`https://app.omi.me` → Developer → API Keys) ve şunlardan birini yapar:

```bash
omi auth login                          # interactive paste; key not in shell history
# or
export OMI_API_KEY=omi_dev_...          # ephemeral, container-friendly
```

## Ajanların en sık yaptığı beş şey

### 1. Anıları oku

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Bir anı oluştur

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Konuşmaları oku

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Açık action item'ları oku

```bash
omi action-item list --json --open
```

### 5. Bir action item'ı tamamla

```bash
omi action-item complete --json a1b2c3d4
```

## Yerel Desktop API

Omi Desktop yerel API'sini açtığında, ajanlar bulut dev API'sini kullanmadan
cihaz ekran geçmişini, recap'leri, SQL ve görevleri sorgulayabilir:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# or, for ephemeral sessions:
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

Görevleri yalnızca kullanıcı açıkça istediğinde tamamla veya sil:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` ekran görüntüsünü diske yazar
ve betikler için stdout'a JSON yazmaya devam eder. Ekran görüntüsü kimliği genellikle
`local search-screen` veya `screenshots` tablosu üzerinden SQL'den gelir. Desktop
`screenshot_pending`, `screenshot_file_missing` veya `screenshot_chunk_corrupted`
gibi yapılandırılmış bir hata döndürürse JSON modu `reason`, `hint` ve
`screenshot_id` alanlarını stderr'de korur; böylece ajanlar daha eski bir kimlikle
yeniden deneyebilir veya tam engeli bildirebilir. Başarılı çıktıları vision
araçlarına vermeden önce `file PATH` ile doğrulayın.

## Uygulamalı örnek: Python agent döngüsü

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

## Rate limit yönetimi

Anılar: 120/saat. Konuşmalar: 25/saat. Toplu oluşturma: 15/saat.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## İpuçları

* Ajanınız birden fazla Omi hesabı yürütüyorsa `--profile <ad>` kullanın. Her
  profilin kendi kimlik bilgileri ve API base'i vardır.
* Yerel backend testi için `--api-base http://localhost:8080` kullanın.
* Tek seferlik çalıştırmada profil yerel Desktop API ayarlarını geçersiz kılmak için
  `OMI_LOCAL_API_URL` ve `OMI_LOCAL_TOKEN` kullanın.
* Hata ayıklama için `--verbose` kullanın — stdout'u etkilemeden stderr'e
  `METHOD path → status (Ns)` yazar; böylece JSON modu geçerli kalır.
* İçeriği bir konuşmaya aktarmak için `--text -` kullanın:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
