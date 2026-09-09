# omi-cli Hızlı Başlangıç Kılavuzu (Turkish Quickstart)

> Terminalinizden Omi ile doğrudan etkileşim kurmak için pratik kılavuz — geliştiriciler ve otonom AI ajanları için tasarlanmıştır.

`omi-cli`, [Omi](https://omi.me) geliştirici API'si için resmi komut satırı arayüzüdür. Sistemin temel 4 kaynağını yapılandırılmış ve otomatikleştirilebilir şekilde yönetmenizi sağlar: hafızalar (memories), konuşmalar (conversations), eylem öğeleri (action items) ve hedefler (goals).

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Resmi Dokümantasyon:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Kaynak Kodu:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Kurulum

Sistem bağımlılık çakışmalarını önlemek ve CLI aracını yalıtılmış bir ortamda çalıştırmak için `pipx` kullanılması önerilir:

```bash
# Önerilen: pipx ile yalıtılmış kurulum
pipx install omi-cli

# Alternatif standart pip kurulumu
pip install omi-cli
```

> **Dikkat: Paket Adı vs. Komut Adı**
> * PyPI üzerindeki paket adı **`omi-cli`**dir (`omi` adı ilişkisiz başka bir pakete aittir).
> * Terminalde çalıştırdığınız komut ise doğrudan **`omi`**dir.

Kurulumun başarılı olduğunu sürüm ve yardım menüsüyle doğrulayın:

```bash
omi --version
omi --help
```

---

## 2. Kimlik Doğrulama (Authentication)

`omi-cli` iki ana kimlik doğrulama yöntemini destekler:

| Yöntem | Kullanım Alanı | Örnek Komut |
| :--- | :--- | :--- |
| **Geliştirici API Anahtarı (`omi_dev_*`)** | Otomasyonlar, CI/CD, headless sunucular, AI ajanları | `omi auth login --api-key ...` veya `OMI_API_KEY` |
| **Tarayıcı OAuth (Google/Apple)** | Yerel iş istasyonları ve geliştiriciler | `omi auth login --browser` (Google) / `--provider apple` |

### Etkileşimli Giriş
Herhangi bir seçenek belirtilmeden çalıştırıldığında yöntem seçimi sunulur:

```bash
omi auth login
# 1) Browser — Tarayıcı üzerinden Google girişi (Apple hesabı için `--provider apple` kullanın)
# 2) API key — app.omi.me üzerinden oluşturulan API anahtarını yapıştırın
```

### Tarayıcı ile Doğrudan Giriş
```bash
# Varsayılan Google girişi
omi auth login --browser

# Alternatif Apple hesabı girişi
omi auth login --browser --provider apple
```

### Geliştirici API Anahtarı Kullanımı
Anahtarınızı [app.omi.me](https://app.omi.me) panelinde **Developer → API Keys** bölümünden oluşturun:

```bash
# Yerel profile kalıcı olarak kaydet (kabuk geçmişini korumak için etkileşimli yapıştırın)
omi auth login --api-key

# Veya ortam değişkeni olarak tanımlayın (konteynerler ve CI/CD için en iyisi)
# Not: Etkin yerel profilde kayıtlı anahtar varsa, önce `omi auth logout` çalıştırın.
export OMI_API_KEY="omi_dev_your_actual_key_here"
```

### Kimlik Doğrulama Durumunu Denetleme
* `omi auth status`: Etkin yerel profili ve maskelenmiş kimlik bilgisini gösterir; sona erme tarihi yalnızca OAuth profilleri için listelenir (çevrimdışı çalışır).
* `omi auth whoami`: Kimliğin canlı sunucu doğrulaması için Omi API'sine istek gönderir (ağ bağlantısı gerektirir).

```bash
omi auth status
omi auth whoami
```

Oturumu kapatma:
```bash
omi auth logout
# Ortamda OMI_API_KEY tanımlıysa, oturumdan da kaldırın (Bash/Zsh: `unset OMI_API_KEY`).
```

---

## 3. Temel Komutlar

### Hafızalar (Memories)
Omi tarafından kaydedilen atomik bağlam bilgileri:

```bash
# Kayıtlı hafızaları listele
omi memory list

# Yeni hafıza oluştur
omi memory create "Python örnekleri içeren teknik ve özlü yanıtları tercih eder" --category work

# Belirli bir hafızanın detayını getir
omi memory get <MEMORY_ID>
```

### Konuşmalar (Conversations)
Omi cihazları tarafından kaydedilen ses dökümleri ve diyalog geçmişi:

```bash
# En son 5 konuşmayı listele
omi conversation list --limit 5

# Konuşma detayını ve tam metin dökümünü getir
omi conversation get <CONVERSATION_ID> --include-transcript
```

### Görevler ve Eylem Öğeleri (Action Items)
Diyaloglardan otomatik olarak çıkarılan görevler:

```bash
# Açık görevleri listele
omi action-item list --open

# Bir görevi tamamla
omi action-item complete <ACTION_ITEM_ID>
```

### Hedefler (Goals)
İlerleme metrikleri ve uzun vadeli hedefler:

```bash
# Aktif hedefleri listele
omi goal list

# Yeni sayısal hedef oluştur
omi goal create "Günde 2L su iç" --type numeric --target 2 --unit liters
```

---

## 4. Yapılandırılmış Otomasyon ve JSON Çıktısı (`--json`)

`omi-cli` otomasyon hatları için birinci sınıf destek sunar. Genel `--json` bayrağı eklendiğinde çıktılar geçerli JSON formatında döndürülür:

```bash
# Hafızaları JSON olarak listele ve jq ile alanları ayıkla
omi --json memory list | jq '.[] | {id, content, category}'

# Son konuşma başlıklarını ayıkla
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# Açık eylem öğelerini ham JSON olarak görüntüle
omi --json action-item list --open | jq '.'
```

> **Önemli Sözdizimi Kuralı:**
> `--json` bayrağı **genel bir seçenek**tir ve alt komuttan **önce** gelmelidir:
> * Doğru: `omi --json memory list`
> * Yanlış: `omi memory list --json`

---

## 5. Çıkış Kodları (Exit Codes)

Kabuk betikleri ve CI/CD iş akışlarında güvenilir hata denetimi:

| Çıkış Kodu | Anlam | Açıklama |
| :---: | :--- | :--- |
| `0` | **Başarılı (Success)** | İşlem hatasız tamamlandı. |
| `1` | **Kullanım Hatası (Doğrulama Hatası)** | Geçersiz veri değerleri veya uygulama doğrulama hatası; Click ayrıştırıcı sözdizimi hataları kod `2` döndürür. |
| `2` | **Kimlik Doğrulama / CLI Sözdizimi Hatası** | Kimlik doğrulanmamış, süresi dolmuş belirteç veya bilinmeyen Click seçenekleri. |
| `3` | **Sunucu / Ağ Hatası (Server Error)** | HTTP 5xx yanıtı, zaman aşımı veya sunucuya erişilemiyor. |
| `4` | **İstek Hızı Sınırı (Rate Limited)** | HTTP 429 yanıtı — hız sınırı nedeniyle istek engellendi. |
| `5` | **Bulunamadı (Not Found)** | HTTP 404 yanıtı — istenen kaynak mevcut değil. |

---

## 6. Kabuk Ortamlarına Göre Örnekler

### Bash / Zsh (Linux / macOS)
```bash
# Oturumda API anahtarını tanımla
export OMI_API_KEY="omi_dev_your_actual_key_here"

# Komutu çalıştır ve çıkış kodunu denetle
omi --json memory list --limit 10
if [ $? -ne 0 ]; then
    echo "Kullanıcı hafızaları sorgulanırken hata oluştu." >&2
fi
```

### PowerShell (Windows)
```powershell
# PowerShell ortam değişkeni tanımla
$env:OMI_API_KEY = "omi_dev_your_actual_key_here"

# JSON çıktısını doğrudan PowerShell nesnesine dönüştür
$memories = omi --json memory list | ConvertFrom-Json
$memories | Select-Object id, content, category

# $LASTEXITCODE ile hata denetimi
if ($LASTEXITCODE -ne 0) {
    Write-Error "Omi komutu $LASTEXITCODE koduyla başarısız oldu."
}
```

---

## 7. Yerel Masaüstü API Entegrasyonu

Omi Desktop uygulaması bilgisayarınızda çalışırken buluta gitmeden yerel ekran ve bağlam geçmişini sorgulayabilirsiniz:

```bash
# Yerel uç noktayı yapılandır (belirteci korumak için ortam değişkeni kullanın)
export OMI_LOCAL_API_URL="http://127.0.0.1:47778"
read -r -s -p "Desktop token: " OMI_LOCAL_TOKEN; echo
export OMI_LOCAL_TOKEN

# Yerel bağlantı durumunu doğrula
omi --json local status

# Son görsel zaman tünelinde arama yap
omi --json local search-screen "Çeyrek raporu" --days 7 --app Safari
```

---

## 8. Çoklu Profil Yönetimi (Profiles)

Kişisel ve iş hesapları veya test ortamları arasında geçiş yapmak için `--profile` seçeneğini kullanın. Ayarlar `~/.omi/config.toml` dosyasında tutulur:

```bash
# Kişisel profil oluştur ve giriş yap
omi --profile personal auth login

# İş profili oluştur ve giriş yap
omi --profile work auth login

# Belirli bir profille komut çalıştır
omi --profile work memory list

# Özel test uç noktasıyla profil çalıştır
omi --profile staging --api-base https://api-staging.omi.me memory list
```

---

## 9. Güvenlik ve En İyi Uygulamalar

* **Git Deposuna Anahtar Göndermeyin:** API anahtarlarınızı genel depolara asla kaydetmeyin; gizli anahtar yöneticilerini veya `.gitignore` kapsamındaki `.env` dosyalarını kullanın.
* **Kabuk Geçmişi:** Paylaşılan makinelerde anahtarları doğrudan komut satırı argümanı olarak geçirmeyin; etkileşimli girişi veya `OMI_API_KEY` ortam değişkenini tercih edin.
* **Klasör İzinleri:** Unix sistemlerinde `~/.omi/` yapılandırma dizini izinlerini kısıtlayın (`chmod 700 ~/.omi`).
