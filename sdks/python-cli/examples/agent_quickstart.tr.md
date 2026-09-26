# Ajanlar için omi-cli

> LLM odaklı harness'lar (Claude Code, Cursor, kendi botlarınız) için pratik kılavuz.

## CLI neden ajan dostudur?

* **Kararlı JSON sözleşmesi.** `--json` bayrağı stdout'a geçerli bir JSON belgesi ve
  *yalnızca* bir JSON belgesi iletir — ilerleme mesajı yok, spinner yok. Hatalar stderr'e
  `{"error": "...", "detail": "..."}` biçiminde iletilir.
* **Kararlı çıkış kodları.** `0` başarılı / `1` kullanım hatası / `2` kimlik doğrulama hatası / `3` sunucu hatası / `4` hız
  sınırı aşıldı (rate limited) / `5` bulunamadı. Ajanlar doğal dil hata mesajlarını ayrıştırmak zorunda kalmadan bu kodlar üzerinden dallanabilir.
* **Headless ortamlarda etkileşimli istemler yoktur.** Yıkıcı komutlar için `--yes` (veya `-y`)
  geçirin; etkileşimli girişi atlamak için `--api-key` geçirin veya `OMI_API_KEY` ortam değişkenini tanımlayın.
* **Toleranslı yeniden deneme davranışı.** `429` ve `5xx` hataları görünür hale gelmeden önce
  üstel geri çekilme (exponential backoff) ile otomatik olarak yeniden denenir.

## Kimlik Doğrulama (İnsan tarafından tek seferlik)

Kullanıcı Omi web uygulamasından (`https://app.omi.me` → Developer → API Keys) bir geliştirici API anahtarı alır ve:

```bash
omi auth login                          # etkileşimli yapıştırma; anahtar kabuk geçmişinde kalmaz
# veya
export OMI_API_KEY=omi_dev_...          # geçici, konteyner dostu
```

## Ajanların en sık yaptığı beş işlem

### 1. Hafızaları okuma

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Hafıza oluşturma

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Konuşmaları okuma

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Açık eylem öğelerini okuma

```bash
omi action-item list --json --open
```

### 5. Bir eylem öğesini tamamlandı olarak işaretleme

```bash
omi action-item complete --json a1b2c3d4
```

## Yerel Desktop API

Omi Desktop yerel API'sini sunduğunda, ajanlar bulut geliştirici API'sini tüketmeden
cihaz içi ekran geçmişini, özetleri, SQL sorgularını ve görevleri sorgulayabilir:

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

`omi local screenshot SCREENSHOT_ID --output PATH` komutu ekran görüntüsünü diske
kaydeder ve betikler için stdout'a JSON çıktısı vermeye devam eder. Ekran görüntüsü kimliği genellikle
`local search-screen` veya `screenshots` tablosundaki bir SQL sorgusundan gelir. Desktop
`screenshot_pending`, `screenshot_file_missing` veya `screenshot_chunk_corrupted` gibi yapılandırılmış
bir hata döndürürse, JSON modu `reason`, `hint` ve `screenshot_id` alanlarını stderr'de korur; böylece
ajanlar daha eski bir kimliği yeniden deneyebilir veya engeli tam olarak bildirebilir. Çıktıları görüntü araçlarına
iletmeden önce `file PATH` ile doğrulayın.

## Uygulamalı örnek: Python ajan döngüsü

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """omi CLI'yi JSON modunda çalıştırır, sıfır olmayan çıkış kodlarında istisna fırlatır."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI, JSON modunda stderr'e yapılandırılmış hatalar yazdırır:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi {result.returncode} kodu ile çıktı: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Tüm açık eylem öğelerini oku ve 30 günden eski olanları tamamlandı olarak işaretle.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Hız sınırlarının yönetimi (Rate limits)

Hafızalar: 120/saat. Konuşmalar: 25/saat. Toplu oluşturma: 15/saat.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # hız sınırı aşıldı
    err = json.loads(result.stderr)
    # err["detail"] şu şekildedir: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## İpuçları

* Ajanınız birden fazla Omi hesabını yönetiyorsa `--profile <name>` kullanın. Her
  profilin kendi kimlik bilgileri ve API tabanı vardır.
* Yerel backend testleri için `--api-base http://localhost:8080` kullanın.
* Tek bir çalıştırma için profile özgü yerel Desktop API ayarlarını geçersiz kılmak üzere
  `OMI_LOCAL_API_URL` ve `OMI_LOCAL_TOKEN` kullanın.
* Hata ayıklama için `--verbose` kullanın — stdout'u etkilemeden stderr'e
  `METHOD path → status (Ns)` kaydeder, böylece JSON modu geçerli kalır.
* İçeriği bir konuşmaya doğrudan pipe ile aktarmak için `--text -` kullanın:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
