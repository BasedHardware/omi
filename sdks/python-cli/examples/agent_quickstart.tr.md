# Ajanlar için omi-cli

> LLM tabanlı çerçeveler (Claude Code, Cursor, kendi botlarınız) için pratik kılavuz.

## CLI Neden Ajan Dostudur?

* **Kararlı JSON Sözleşmesi.** `--json` parametresi stdout üzerine geçerli bir JSON belgesi
  ve *yalnızca* bir JSON belgesi yazar — ilerleme mesajları veya yükleme animasyonları yoktur.
  Hatalar stderr'e `{"error": "...", "detail": "..."}` biçiminde iletilir.
* **Kararlı Çıkış Kodları.** `0` başarılı / `1` kullanım hatası / `2` kimlik doğrulama /
  `3` sunucu hatası / `4` hız sınırı / `5` bulunamadı. Ajanlar doğal dil hata mesajlarını
  ayrıştırmaya gerek kalmadan bu kodlara göre dallanabilir.
* **Gözetimsiz (Headless) Ortamlarda Etkileşimli İstem Yoktur.** Yıkıcı komutlara `--yes` (veya `-y`)
  geçirin; etkileşimli girişi atlamak için `--api-key` belirtin veya `OMI_API_KEY` tanımlayın.
* **Toleranslı Yeniden Deneme Davranışı.** `429` ve `5xx` hataları kullanıcıya iletilmeden önce
  üssel geri çekilme (exponential backoff) ile otomatik olarak yeniden denenir.

## Kimlik Doğrulama (İnsan Tarafından Bir Kez Yapılır)

Kullanıcı Omi web uygulamasından bir geliştirici API anahtarı alır
(`https://app.omi.me` → Developer → API Keys) ve aşağıdakilerden birini uygular:

```bash
omi auth login                          # etkileşimli yapıştırma; anahtar kabuk geçmişine kaydedilmez
# veya
export OMI_API_KEY=omi_dev_...          # geçici, kapsayıcı dostu
```

## Ajanların En Çok Yaptığı 5 Şey

### 1. Hafızaları Okuma

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Hafıza Oluşturma

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Konuşmaları Okuma

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Açık Eylem Öğelerini Okuma

```bash
omi action-item list --json --open
```

### 5. Bir Eylem Öğesini Tamamlandı Olarak İşaretleme

```bash
omi action-item complete --json a1b2c3d4
```

## Yerel Masaüstü API'si

Omi Desktop yerel API'sini açtığında, ajanlar bulut geliştirici API'sini kullanmadan
cihaz içi ekran geçmişini, özetleri, SQL verilerini ve görevleri sorgulayabilir:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# veya geçici oturumlar için:
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

Görevleri yalnızca kullanıcı açıkça talep ettiğinde tamamlayın veya silin:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` komutu ekran görüntüsünü diske yazar ve
komut dosyaları için stdout'a JSON basmaya devam eder. Ekran görüntüsü kimliği genellikle
`local search-screen` çıktısından veya `screenshots` tablosuna yönelik SQL sorgusundan gelir. Masaüstü
`screenshot_pending`, `screenshot_file_missing` veya `screenshot_chunk_corrupted` gibi yapılandırılmış
bir hata döndürürse, JSON modu stderr üzerinde `reason`, `hint` ve `screenshot_id` alanlarını korur,
böylece ajanlar eski bir kimlikle yeniden deneyebilir veya engeli tam olarak bildirebilir.
Görsel araçlara aktarmadan önce başarılı çıktıları `file PATH` ile doğrulayın.

## Örnek Senaryo: Python Ajan Döngüsü

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

## Hız Sınırlarını Yönetme

Hafızalar: 120/saat. Konuşmalar: 25/saat. Toplu oluşturma: 15/saat.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## İpuçları

* Ajanınız birden fazla Omi hesabını yönetiyorsa `--profile <ad>` kullanın.
  Her profil kendi kimlik bilgisine ve API taban adresine sahiptir.
* Yerel arka uç testleri için `--api-base http://localhost:8080` kullanın.
* Tek bir çalıştırmada profilin yerel Masaüstü API ayarlarını geçersiz kılmak için
  `OMI_LOCAL_API_URL` ve `OMI_LOCAL_TOKEN` kullanın.
* Hata ayıklama için `--verbose` kullanın — stderr'e `METHOD path → status (Ns)` kaydeder
  ve stdout'u etkilemediği için JSON modu geçerli kalır.
* İçeriği bir konuşmaya yönlendirmek (pipe) için `--text -` kullanın:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
