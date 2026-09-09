# omi-cli Hızlı Başlangıç Kılavuzu (Turkish Quickstart)

Resmi Omi komut satırı arayüzü (`omi-cli`) için pratik başvuru kılavuzu.
Bu belge kurulum, kimlik doğrulama, veri yönetimi komutları ve betikler ile otonom ajanlar için otomasyon tekniklerini açıklar.

---

## Genel Bakış ve Çalıştırılabilir Dosya

* **PyPI Paket Adı:** `omi-cli`
* **Çalıştırılabilir Komut:** `omi`

Kurulum ve kullanım sırasında karışıklığı önlemek için:

```bash
# Paket adıyla kurulur:
pipx install omi-cli

# Kısa komut adıyla çalıştırılır:
omi --help
```

---

## Kurulum

Bağımlılık çakışmalarını önlemek ve CLI aracını yalıtılmış bir ortamda çalıştırmak için `pipx` kullanılması önerilir.

### Önerilen Yöntem (`pipx`)

```bash
pipx install omi-cli
```

En son sürüme güncellemek için:

```bash
pipx upgrade omi-cli
```

### Alternatif Yöntem (`pip`)

```bash
pip install --user omi-cli
```

Kurulumun başarılı olduğunu doğrulayın:

```bash
omi --version
```

---

## Kimlik Doğrulama

CLI üç ana kimlik doğrulama yöntemini destekler: etkileşimli tarayıcı girişi, doğrudan API anahtarı ve ortam değişkeni.

### 1. Tarayıcı ile Etkileşimli Giriş

Grafik arayüzü bulunan yerel geliştirme makineleri için uygundur:

```bash
omi auth login --browser
```

Bu komut tarayıcınızda kimlik doğrulama sayfasını açar ve belirteci güvenli bir şekilde yerel sisteminize kaydeder.

### 2. API Anahtarı ile Giriş (Gözetimsiz / Headless)

Uzak sunucular, SSH bağlantıları veya CI/CD iş akışları için uygundur:

```bash
omi auth login --api-key
```

CLI, Omi geliştirici panelinden oluşturduğunuz anahtarı girmenizi isteyecektir.

### 3. Ortam Değişkeni Kullanımı

Docker konteynerleri veya dosya depolaması olmayan otomasyonlar için:

```bash
export OMI_API_KEY="gizli-api-anahtariniz"
```

### Kimlik Doğrulama Durumunu Denetleme

* **Çevrimdışı denetim (yerel belirteç varlığı):**
  ```bash
  omi auth status
  ```
* **Çevrimiçi denetim (sunucu üzerinden canlı doğrulama):**
  ```bash
  omi auth whoami
  ```

Yerel oturumu kapatmak için:

```bash
omi auth logout
```

---

## Temel İş Akışları

### Hafızalar (`omi memory`)

Hafızalar, Omi tarafından yakalanan atomik bağlam parçalarını temsil eder.

```bash
# Son hafızaları listele
omi memory list --limit 10

# Manuel olarak yeni bir hafıza oluştur
omi memory create --text "Proje toplantısı Salı günü saat 10:00'da teknik ekiple yapılacak."

# Hafızalar arasında anlamsal arama yap
omi memory search "proje toplantısı"
```

### Konuşmalar (`omi conversation`)

Kayıt altına alınan konuşmaları ve ses dökümlerini yönetir.

```bash
# Konuşmaları listele
omi conversation list --limit 5

# Belirli bir konuşmanın detaylarını getir
omi conversation get conv_123456

# Konuşmanın tam dökümünü Markdown formatında dışa aktar
omi conversation export conv_123456 --format markdown > dokum.md
```

### Eylem Öğeleri ve Görevler (`omi action-item`)

Konuşmalardan otomatik çıkarılan görevleri takip eder.

```bash
# Bekleyen eylem öğelerini listele
omi action-item list --status pending

# Bir görevi tamamlandı olarak işaretle
omi action-item update act_789012 --completed
```

### Hedefler (`omi goal`)

Kişisel veya profesyonel uzun vadeli hedefleri yönetir.

```bash
# Aktif hedefleri listele
omi goal list

# Yeni bir hedef oluştur
omi goal create --title "Çok dilli dokümantasyonu tamamla" --horizon month

# Hedef ilerlemesini güncelle
omi goal update goal_345678 --progress 75
```

---

## Yapılandırılmış Otomasyon (`--json` & `jq`)

Tüm `omi` komutları küresel `--json` seçeneğini kabul eder. Bu sayede çıktılar betikler ve veri işleme araçları tarafından doğrudan ayrıştırılabilir.

### `jq` ile Veri Filtreleme ve Çıkarma

```bash
# Tüm hafıza metinlerini ayıkla
omi --json memory list --limit 20 | jq -r '.[].content'

# Tamamlanmamış eylem öğelerini filtrele
omi --json action-item list | jq '.[] | select(.completed == false) | {id: .id, description: .description}'
```

---

## Çıkış Kodları Tablosu (Exit Codes)

CLI, betiklerin hataları güvenilir şekilde yakalamasını sağlayan standart çıkış kodları üretir:

| Kod | Anlam | Tipik Neden |
| :---: | :--- | :--- |
| `0` | **Başarılı** | İşlem başarıyla tamamlandı. |
| `1` | **Genel Hata** | Yakalanmamış iç istisna veya beklenmeyen hata. |
| `2` | **Bağımsız Değişken Hatası** | Geçersiz parametre, eksik argüman veya sözdizimi hatası. |
| `3` | **Yetkilendirme Hatası** | Eksik, geçersiz veya süresi dolmuş kimlik belirteci. |
| `4` | **Bulunamadı** | İstenen kaynak (hafıza, konuşma, hedef) mevcut değil. |
| `5` | **Ağ Hatası** | Bağlantı kesintisi veya sunucu zaman aşımı. |

---

## Çapraz Platform Betikleri

### Bash / Zsh (Linux & macOS)

```bash
#!/usr/bin/env bash
set -euo pipefail

echo "Omi kimlik doğrulaması kontrol ediliyor..."
if ! omi auth status > /dev/null 2>&1; then
    echo "Hata: Kimlik doğrulaması gerekli. Lütfen 'omi auth login' çalıştırın." >&2
    exit 3
fi

echo "Yeni not kaydediliyor..."
omi memory create --text "Otomatik sistem denetimi başarıyla tamamlandı."
```

### PowerShell (Windows)

```powershell
Write-Host "Omi kimlik doğrulaması kontrol ediliyor..."
omi auth status
if ($LASTEXITCODE -ne 0) {
    Write-Error "Kimlik doğrulaması eksik. Lütfen 'omi auth login' çalıştırın."
    exit $LASTEXITCODE
}

Write-Host "Hedefler getiriliyor..."
omi --json goal list | ConvertFrom-Json | ForEach-Object {
    [PSCustomObject]@{
        Id = $_.id
        Baslik = $_.title
        Ilerleme = "$($_.progress)%"
    }
}
```

---

## Yerel Omi Desktop API Entegrasyonu

Omi Desktop uygulaması yerel ortamınızda çalışırken, CLI doğrudan masaüstü bağlam hizmetleriyle iletişim kurabilir:

```bash
# Yerel masaüstü bağlantı noktasını yapılandır
omi local configure --port 8000

# Yerel ekranda yakalanan metinleri ara
omi local search-screen "çeyrek raporu"
```

---

## Çoklu Ortam Profil Yönetimi

Farklı ortamları (örneğin kişisel, iş ve hazırlık ortamı) `--profile` bayrağı veya `~/.omi/config.toml` dosyası üzerinden yönetebilirsiniz:

```bash
# Belirli bir profili kullanarak komut çalıştır
omi --profile is memory list

# Özel API uç noktasıyla test profili kullan
omi --profile staging --api-url https://api-staging.omi.me memory list
```

---

## Güvenlik ve En İyi Uygulamalar

1. **Belirteç Gizliliği:** API anahtarlarınızı veya oturum belirteçlerinizi asla genel Git depolarına göndermeyin.
2. **Kabuk Geçmişi Güvenliği:** Paylaşılan sistemlerde `--api-key` bayrağını komut satırında doğrudan yazmak yerine etkileşimli giriş yöntemini veya `OMI_API_KEY` ortam değişkenini tercih edin.
3. **Erişim İzinleri:** Unix tabanlı üretim ortamlarında yapılandırma dizini `~/.omi/` için izinleri kısıtlayın (`chmod 700 ~/.omi`).
