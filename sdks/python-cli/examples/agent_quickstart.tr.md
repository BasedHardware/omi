# Ajanlar için omi-cli

> LLM odaklı ortamlar için pratik rehber (Claude Code, Cursor, kendi botlarınız).

## CLI neden ajan dostudur

* **Kararlı JSON sözleşmesi.** `--json` bayrağı stdout üzerine geçerli bir JSON belgesi ve *yalnızca* bir JSON belgesi çıktısı verir — ilerleme mesajı yok, yükleme animasyonu yok. Hatalar stderr üzerine `{"error": "...", "detail": "..."}` formatında iletilir.
* **Kararlı çıkış kodları.** `0` başarılı / `1` kullanım hatası / `2` kimlik doğrulama hatası / `3` sunucu hatası / `4` istek sınırı aşıldı / `5` bulunamadı. Ajanlar doğal dil hatalarını ayrıştırmak zorunda kalmadan bu kodlara göre dallanma yapabilir.
* **Headless modda etkileşimli istem yok.** Yıkıcı komutlar için `--yes` (veya `-y`) iletin; etkileşimli girişi atlamak için `--api-key` iletin veya `OMI_API_KEY` değişkenini ayarlayın.
* **Esnek yeniden deneme davranışı.** `429` ve `5xx` hataları, hata bildirilmeden önce üssel geri çekilme ile otomatik olarak yeniden denenir.

## Kimlik Doğrulama (tek seferlik, insan tarafından yapılır)

Kullanıcı Omi web uygulamasından (`https://app.omi.me` → Developer → API Keys) geliştirici API anahtarı alır ve şunlardan birini çalıştırır:

```bash
omi auth login                          # etkileşimli yapıştırma; anahtar kabuk geçmişine kaydedilmez
# veya
export OMI_API_KEY=omi_dev_...          # geçici, konteyner dostu
```

## Ajanların en çok yaptığı beş işlem

### 1. Anıları okuma (memories)

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Anı oluşturma

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Konuşmaları okuma

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Açık görevleri okuma (action items)

```bash
omi action-item list --json --open
```

### 5. Bir görevi tamamlandı olarak işaretleme

```bash
omi action-item complete --json a1b2c3d4
```

## Yerel Masaüstü API (Local Desktop API)

Omi Desktop yerel API'sini açtığında, ajanlar bulut API'sini kullanmadan cihazdaki ekran geçmişini, özetleri, SQL'i ve görevleri sorgulayabilir:

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

Görevleri yalnızca kullanıcı açıkça istediğinde tamamlayın veya silin:

```bash
omi --json local task complete task_1
```
