# omi-cli Sürətli Başlanğıc Təlimatı (Azerbaijani Quickstart)

> Omi ilə birbaşa terminaldan işləmək üçün praktiki təlimat — tərtibatçılar və muxtar süni intellekt (AI) agentləri üçün nəzərdə tutulmuşdur.

`omi-cli` [Omi](https://omi.me) platformasının tərtibatçı API-si üçün rəsmi əmr satırı interfeysidir (CLI). O, dörd əsas resursa strukturlaşdırılmış və AI agentləri üçün optimallaşdırılmış çıxış təmin edir: **xatirələr** (memories), **söhbətlər** (conversations), **fəaliyyət bəndləri** (action items) və **hədəflər** (goals).

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Rəsmi sənədləşmə:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Mənbə kodu:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Quraşdırma (Installation)

Paket ziddiyyətlərinin qarşısını almaq və təmiz mühit saxlamaq üçün `pipx` alətindən istifadə tövsiyə olunur:

```bash
# Tövsiyə olunan üsul: pipx vasitəsilə təcrid olunmuş quraşdırma
pipx install omi-cli

# Standart pip vasitəsilə alternativ quraşdırma (məsələn, virtual mühitdə)
pip install omi-cli
```

> **Vacib fərq: Paket adı vs. Əmr adı**
> * Quraşdırma zamanı paketin adı **`omi-cli`**-dir.
> * Terminalda icra edilən əmr isə **`omi`**-dir.

Quraşdırmanın düzgünlüyünü yoxlayın:

```bash
omi --version
```

---

## 2. Autentifikasiya (Authentication)

`omi-cli` iki əsas autentifikasiya metodunu dəstəkləyir: **Brauzer vasitəsilə OAuth** (interaktiv istifadəçilər üçün) və **Tərtibatçı API açarı** (avtomatlaşdırma və AI agentləri üçün).

### Metod A: Brauzer vasitəsilə giriş (İstifadəçilər)

Standart giriş metodu Google hesabından istifadə edir:

```bash
omi auth login
```

Və ya Apple ID vasitəsilə daxil olun:

```bash
omi auth login --provider apple
```

Bu əmr kimliyi təsdiqləmək üçün veb-brauzer pəncərəsini açır və giriş tokenini `~/.omi/config.toml` konfiqurasiya faylında saxlayır.

### Metod B: Tərtibatçı API açarı (Skriptlər və Agentlər)

Fon xidmətləri, CI/CD prosesləri və ya muxtar agentlər üçün tərtibatçı API açarından (`omi_dev_*`) istifadə edin:

```bash
# Variant 1: Mühit dəyişəninin (Environment Variable) təyin edilməsi (serverlər üçün ən yaxşı təcrübə)
export OMI_API_KEY="omi_dev_your_key_here"

# Variant 2: Daxil olmaq və açarı lokal konfiqurasiyada saxlamaq
omi auth login --api-key "omi_dev_your_key_here"
```

### Autentifikasiya statusunun yoxlanılması

Statusu yoxlamaq üçün iki əmr mövcuddur:

```bash
# Şəbəkə sorğusu olmadan lokal yoxlama (konfiqurasiyanı və ya mühit dəyişənlərini oxuyur)
omi auth status

# Serverdə aktiv yoxlama (sessiyanın etibarlılığını yoxlayır və profil məlumatlarını gətirir)
omi auth whoami
```

### Sistemdən çıxış (Logout)

Saxlanılan giriş məlumatlarını lokal sistemdən silmək üçün:

```bash
omi auth logout
```

---

## 3. Xatirələrin idarə edilməsi (Memories)

Xatirələr Omi-nin sizin haqqınızda yadda saxladığı fərdi qeydləri və kontekstual faktları təmsil edir.

```bash
# Ən son xatirələrin siyahısı (standart olaraq 25 qeyd)
omi memory list

# Göstərilən xatirələrin sayını məhdudlaşdırmaq
omi memory list --limit 10

# Səhifələmə (ilkin qeydləri ötürmək)
omi memory list --limit 10 --offset 20

# Konkret xatirənin təfərrüatlarına ID ilə baxmaq
omi memory get <memory-id>

# Əl ilə yeni xatirə yaratmaq
omi memory create "Komandanın ən sevimli proqramlaşdırma dili Python-dur."
```

---

## 4. Söhbətlər, fəaliyyət bəndləri və hədəflər

### Söhbətlər (Conversations)

```bash
# Son söhbətlərin siyahısı
omi conversation list

# Konkret söhbətin təfərrüatlarına və transkriptinə baxmaq
omi conversation get <conversation-id>
```

### Fəaliyyət bəndləri (Action Items)

Söhbət zamanı aşkarlanan və ya əl ilə əlavə edilən tapşırıqlar:

```bash
# Hazırda açıq olan tapşırıqların siyahısı
omi action-item list

# Yeni fəaliyyət bəndinin yaradılması
omi action-item create "Görüşdən əvvəl kod icmalı hesabatını hazırlamaq."
```

### Hədəflər (Goals)

İzlədiyiniz uzunmüddətli hədəflər və tərəqqi göstəriciləri:

```bash
# Bütün aktiv hədəflərin siyahısı
omi goal list

# Yeni hədəf əlavə etmək
omi goal create "Rübün sonuna qədər Omi CLI inteqrasiyasını tamamlamaq."
```

---

## 5. JSON formatı və boru kəməri inteqrasiyası (jq)

Avtomatlaşdırma skriptləri və AI agentləri ilə inteqrasiya üçün qlobal `--json` bayrağından istifadə edin.

> **Vacib qayda:** `--json` bayrağı mütləq alt əmrdən **əvvəl** göstərilməlidir (before the subcommand):

```bash
# Düzgündür:
omi --json memory list

# Səhvdir (Click təhlilçisi xətasına səbəb olacaq):
omi memory list --json
```

### `jq` aləti ilə filtrləmə nümunələri:

```bash
# Yalnız xatirələrin ID-lərini əldə etmək
omi --json memory list | jq -r '.[].id'

# Xatirələrin məzmununu ayrı-ayrı mətn sətirləri kimi çıxarmaq
omi --json memory list | jq -r '.[].content'

# Söhbətin ID və başlığını yığcam formatda göstərmək
omi --json conversation list | jq -r '.[] | "\(.id): \(.structured.title)"'

# Açıq fəaliyyət bəndlərinin ümumi sayını hesablamaq
omi --json action-item list | jq 'length'
```

---

## 6. Çıxış kodları və xətaların idarə edilməsi

`omi-cli` `omi_cli/errors.py` faylında müəyyən edilmiş dəqiq çıxış kodlarını tətbiq edir:

| Kod | Sabit | Kateqoriya | Məna və tövsiyə olunan tədbir |
| :---: | :--- | :--- | :--- |
| **`0`** | `EXIT_OK` | Uğur | Əmr uğurla və tam şəkildə icra edildi. |
| **`1`** | `EXIT_USAGE` | Yanlış istifadə | `omi-cli` daxilində daxili doğrulama xətası (məsələn, eyni anda `--browser` və `--api-key` göstərilməsi). *Qeyd:* Click təhlilçisinin standart sintaksis xətaları **2** kodunu qaytarır. |
| **`2`** | `EXIT_AUTH` | Autentifikasiya | Yanlış API açarı, vaxtı keçmiş sessiya və ya çatışmayan token. Həmçinin Click təhlilçi xətaları. |
| **`3`** | `EXIT_SERVER` | Server / Şəbəkə xətası | HTTP 5xx cavabı və ya şəbəkə bağlantısının kəsilməsi. Serverdə məlumatın yazılmasına zəmanət verilmir. |
| **`4`** | `EXIT_RATE_LIMITED` | Sorğu limitinin aşılması | HTTP 429 cavabı. CLI avtomatik olaraq `Retry-After` başlığını nəzərə alaraq sorğunu yenidən cəhd edir. |
| **`5`** | `EXIT_NOT_FOUND` | Resurs tapılmadı | HTTP 404 cavabı. Göstərilən resurs və ya ID mövcud deyil. |

> **Giriş tokeninin yenilənməsi:** `omi auth refresh` əmri yalnız brauzer (OAuth) sessiyaları üçün nəzərdə tutulub. Tərtibatçı API açarlarından istifadə zamanı bu əmr xəta qaytarır (çıxış kodu 1), çünki yenilənəcək token yoxdur.

---

## 7. Avtomatlaşdırma skriptlərinin nümunələri

### Bash skripti: Xətaların emalı ilə xatirə yaratmaq

```bash
#!/usr/bin/env bash
set -euo pipefail

METN="Komandanın həftəlik sinxronizasiya görüşü bazar ertəsi saat 11:00-a təyin edildi."

echo "Yeni xatirə yaradılır..."
if CAVAB=$(omi --json memory create "$METN" 2>&1); then
  MEMORY_ID=$(echo "$CAVAB" | jq -r '.id // empty')
  echo "Uğurlu! Yeni xatirənin ID-si: $MEMORY_ID"
else
  STATUS=$?
  echo "Xatirə yaradılarkən xəta baş verdi (Çıxış kodu: $STATUS)"
  case $STATUS in
    2) echo "Autentifikasiya xətası: OMI_API_KEY dəyişənini yoxlayın və ya 'omi auth login' icra edin." ;;
    3) echo "Server və ya şəbəkə xətası. Bir az sonra yenidən cəhd edin." ;;
    4) echo "Sorğu limiti aşılmışdır." ;;
    *) echo "Xəta baş verdi: $CAVAB" ;;
  esac
  exit $STATUS
fi
```

### PowerShell skripti: Fəaliyyət bəndlərinin emalı

```powershell
$cavab = omi --json action-item list | ConvertFrom-Json

foreach ($bend in $cavab) {
    [PSCustomObject]@{
        Id        = $bend.id
        Mezmun    = $bend.description
        Yaradildi = $bend.created_at
    }
}
```

---

## 8. Qabaqcıl imkanlar

### Lokal Desktop API ilə əlaqə

Əgər kompüterinizdə Omi desktop tətbiqi işləyirsə, `omi-cli` buluda göndərilmədən birbaşa `47778` portu vasitəsilə `local` alt əmrləri üçün onunla əlaqə saxlaya bilər:

```bash
# Lokal API üçün mühit dəyişənlərinin təyin edilməsi
export OMI_LOCAL_API_URL="http://127.0.0.1:47778"
export OMI_LOCAL_TOKEN="your_local_security_token"

# Lokal xidmət statusunun yoxlanılması
omi local status
```

### Profillərin idarə edilməsi və sınaq mühiti (Staging)

`--profile` bayrağı bir neçə müstəqil konfiqurasiya ilə işləməyə imkan verir (məsələn, şəxsi, iş və ya sınaq mühiti). Parametrlər `~/.omi/config.toml` faylında saxlanılır:

```bash
# Fərqli profillərə daxil olmaq
omi --profile personal auth login
omi --profile work auth login

# Əmrləri konkret profil altında icra etmək
omi --profile work memory list

# Staging mühitində sınaqdan keçirmək
omi --profile staging --api-base https://api.staging.omi.me memory list
```

---

## 9. Təhlükəsizlik və ən yaxşı təcrübələr

* **Məxfi açarların qorunması:** Heç vaxt `omi_dev_*` açarlarını Git-in ictimai depolarında saxlamayın. Mühit dəyişənlərindən və ya təhlükəsiz sirr idarəetmə sistemlərindən (Secret Managers) istifadə edin.
* **Fayl icazələri (Unix):** Konfiqurasiya qovluğunu məhdudlaşdırıcı icazələrlə qoruyun:
  ```bash
  chmod 700 ~/.omi
  ```
* **Müvəqqəti sessiyaların təmizlənməsi:** Paylaşılan və ya müvəqqəti iş stansiyalarında işi bitirdikdən sonra sessiya məlumatlarını təmizləyin:
  ```bash
  unset OMI_API_KEY
  omi auth logout
  ```
