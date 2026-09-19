# Ajanlar için omi-cli

> LLM odaklı harness'lar (Claude Code, Cursor, kendi botlarınız) için pratik rehber.

## CLI neden ajan dostudur

* **Kararlı JSON sözleşmesi.** `--json` stdout'a geçerli bir JSON belgesi ve *yalnızca* bir JSON belgesi basar — ilerleme çubukları veya yükleme animasyonları (spinner) yoktur. Hatalar stderr'e `{"error": "...", "detail": "..."}` olarak iletilir.
* **Kararlı çıkış kodları.** `0` başarılı / `1` kullanım hatası / `2` kimlik doğrulama / `3` sunucu hatası / `4` hız sınırına ulaşıldı (rate limited) / `5` bulunamadı. Ajanlar, doğal dildeki hataları ayrıştırmak zorunda kalmadan bu kodlara göre dallanabilir.
* **Gözetimsiz (headless) ortamlarda etkileşimli istem yoktur.** Yıkıcı komutlar için `--yes` (veya `-y`) parametresini verin; etkileşimli girişi atlamak için `--api-key` iletin veya `OMI_API_KEY` ortam değişkenini tanımlayın.
* **Esnek yeniden deneme davranışı.** `429` ve `5xx` hataları istemciye yansıtılmadan önce üstel geri çekilme (exponential backoff) ile otomatik olarak yeniden denenir.

## Kimlik Doğrulama (İnsan tarafından tek seferlik)

Kullanıcı Omi web uygulamasından (`https://app.omi.me` → Developer → API Keys) bir geliştirici API anahtarı alır ve şunlardan birini yapar:

```bash
omi auth login                          # etkileşimli yapıştırma; anahtar kabuk geçmişine kaydedilmez
# veya
export OMI_API_KEY=omi_dev_...          # geçici, konteyner dostu
```

## Ajanların en sık yaptığı 5 işlem

### 1. Bellekleri okuma

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Bellek oluşturma

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

## Yerel Masaüstü API'si

Omi Desktop yerel API'sini sunduğunda, ajanlar bulut geliştirici API'sini kullanmadan cihazdaki ekran geçmişini, özetleri, SQL sorgularını ve görevleri sorgulayabilir:

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

`omi local screenshot SCREENSHOT_ID --output PATH` ekran görüntüsünü diske yazar ve betikler için stdout'a JSON çıktısı verir. Ekran görüntüsü kimliği genellikle `local search-screen` komutundan veya `screenshots` tablosuna yapılan SQL sorgusundan alınır. Desktop `screenshot_pending`, `screenshot_file_missing` veya `screenshot_chunk_corrupted` gibi yapılandırılmış bir hata dönerse, JSON modu stderr üzerinde `reason`, `hint` ve `screenshot_id` alanlarını korur; böylece ajanlar daha eski bir ID ile yeniden deneyebilir veya tam engeli bildirebilir. Görsel araçlara aktarmadan önce başarılı çıktıları `file PATH` ile doğrulayın.

## Örnek çalışma: Python ajan döngüsü

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """JSON modunda omi CLI'yı çağırır, sıfır olmayan çıkış kodlarında istisna fırlatır."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI, JSON modunda stderr'e yapılandırılmış hatalar basar:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Tüm açık eylem öğelerini okuyun ve 30 günden eski olanları tamamlandı olarak işaretleyin.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Hız sınırlarını yönetme

Bellekler: 120/saat. Konuşmalar: 25/saat. Toplu oluşturma: 15/saat.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # hız sınırına ulaşıldı
    err = json.loads(result.stderr)
    # err["detail"] şuna benzer: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## İpuçları

* Ajanınız birden fazla Omi hesabını yönetiyorsa `--profile <name>` kullanın. Her profilin kendi kimlik bilgileri ve API tabanı vardır.
* Yerel arka uç testi için `--api-base http://localhost:8080` kullanın.
* Tek bir çalıştırma için profile özgü yerel Desktop API ayarlarını geçersiz kılmak için `OMI_LOCAL_API_URL` ve `OMI_LOCAL_TOKEN` kullanın.
* Hata ayıklama için `--verbose` kullanın — bu, stdout'u etkilemeden stderr'e `METHOD path → status (Ns)` kaydeder, böylece JSON modu geçerli kalır.
* İçeriği bir konuşmaya boru (pipe) ile aktarmak için `--text -` kullanın:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
