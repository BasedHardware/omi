# omi-cli tezkor boshlash qo'llanmasi (Uzbek Quickstart)

> Omi bilan to'g'ridan-to'g'ri terminaldan ishlash uchun amaliy qo'llanma — dasturchilar va avtonom AI agentlari uchun yaratilgan.

`omi-cli` — [Omi](https://omi.me) platformasining dasturchilar API-si uchun rasmiy buyruqlar satri interfeysi (CLI). U tizimda saqlanadigan to'rtta asosiy resursga tuzilgan va agentlarga qulay kirishni ta'minlaydi: **xotiralar** (memories), **suhbatlar** (conversations), **harakat elementlari** (action items) va **maqsadlar** (goals).

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Rasmiy hujjatlar:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Boshlang'ich kod:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. O'rnatish (Installation)

Paketlar to'qnashuvining oldini olish va tizimda toza muhitni saqlash uchun `pipx` vositasidan foydalanish tavsiya etiladi:

```bash
# Tavsiya etilgan usul: pipx orqali izolyatsiyalangan o'rnatish
pipx install omi-cli

# Standart pip orqali muqobil o'rnatish (masalan, virtual muhitda)
pip install omi-cli
```

> **Muhim farq: Paket nomi va buyruq nomi**
> * O'rnatish vaqtidagi paket nomi — **`omi-cli`**.
> * Terminalda ishga tushiriladigan buyruq nomi — **`omi`**.

O'rnatish muvaffaqiyatli yakunlanganini tekshirish:

```bash
omi --version
```

---

## 2. Autentifikatsiya (Authentication)

`omi-cli` autentifikatsiyaning ikkita asosiy usulini qo'llab-quvvatlaydi: **Brauzer orqali OAuth** (interaktiv foydalanuvchilar uchun) va **Dasturchining API kaliti** (avtomatlashtirish va AI agentlari uchun).

### A usuli: Brauzer orqali kirish (Foydalanuvchilar uchun)

Standart kirish usuli Google hisobidan foydalanadi:

```bash
omi auth login
```

Apple hisob qaydnomasi orqali kirish:

```bash
omi auth login --browser --provider apple
```

### B usuli: Dasturchining API kaliti (Agentlar va CI/CD tizimlari uchun)

Avtomatlashtirilgan skriptlar, fon jarayonlari va AI agentlari uchun Omi portalidan olingan API kalitidan foydalaning (kalit `omi_dev_` prefiksi bilan boshlanadi):

```bash
# Muhit o'zgaruvchisi orqali (tavsiya etiladi)
export OMI_API_KEY="omi_dev_sizning_haqiqiy_kalitingiz"

# Yoki kalitni keshga saqlash orqali
omi auth login --api-key omi_dev_sizning_haqiqiy_kalitingiz
```

### Autentifikatsiya holatini tekshirish

```bash
# Oflayn tekshirish: mahalliy keshda hisob ma'lumotlari mavjudligini tekshiradi
omi auth status

# Onlayn tekshirish: Omi serveriga so'rov yuborib, joriy hisob ma'lumotlarini tasdiqlaydi
omi auth whoami
```

Tizimdan chiqish (keshni tozalash):

```bash
omi auth logout
```

---

## 3. Asosiy buyruqlar va resurslar (Core Commands & Resources)

Omi to'rtta asosiy resurs atrofida qurilgan.

### 1. Xotiralar (Memories)

Xotiralar — Omi tomonidan suhbatlar va yozuvlardan olingan faktlar va qaydlar.

```bash
# Barcha xotiralar ro'yxatini ko'rish
omi memory list

# Eng so'nggi 5 ta xotirani olish
omi memory list --limit 5

# Sahifalash (ikkinchi sahifadagi 10 ta yozuv)
omi memory list --limit 10 --offset 10

# Muayyan xotira tafsilotlarini ko'rish
omi memory get <memory-id>

# Yangi xotira kiritish
omi memory create "Mijoz bilan yangi loyiha rejasini muhokama qildik"
```

### 2. Suhbatlar (Conversations)

Omi audio transkripsiyalari va matnli muloqotlar tarixi.

```bash
# Suhbatlar ro'yxatini olish
omi conversation list

# Muayyan suhbatning to'liq yozuvini ko'rish
omi conversation get <conversation-id>
```

### 3. Harakat elementlari va topshiriqlar (Action Items)

Suhbatlar davomida aniqlangan vazifalar va harakatlar.

```bash
# Barcha vazifalar ro'yxati
omi action-item list

# Bajarilmagan (ochiq) vazifalar
omi action-item list --open

# Vazifa holatini yangilash (bajarildi deb belgilash)
omi action-item update <item-id> --completed
```

### 4. Maqsadlar (Goals)

Uzoq muddatli maqsadlar va ularning bajarilish jarayoni.

```bash
# Barcha maqsadlarni ko'rish
omi goal list

# Yangi maqsad qo'shish
omi goal create "Python CLI testlarini 100% ga yetkazish"
```

---

## 4. Mashina orqali qayta ishlash: Global `--json` bayrog'i (JSON Output & Agent Pipeline)

AI agentlari va bash skriptlari uchun ma'lumotlarni tahlil qilish oson bo'lishi lozim. Buning uchun `omi-cli` global `--json` bayrog'ini taqdim etadi.

> **Muhim qoida: `--json` bayrog'ining joylashuvi**
> `--json` bayrog'i **global parametr** hisoblanadi va u asosiy `omi` buyrug'idan so'ng, subbuyruqlardan oldin joylashtirilishi shart:
>
> ```bash
> # To'g'ri:
> omi --json memory list
> omi --json conversation list --limit 5
>
> # Noto'g'ri (Click uni subbuyruq parametri deb o'ylab xatolik berishi mumkin):
> omi memory list --json
> ```

### `jq` bilan integratsiya namunalari

```bash
# 1. Faqat xotiralar ID-si, matni va yaratilgan vaqtini ajratib olish
omi --json memory list | jq '.[] | {id: .id, content: .content, created_at: .created_at}'

# 2. Suhbatlar ID-si va sarlavhasini olish
omi --json conversation list | jq -r '.[] | "\(.id): \(.structured.title)"'

# 3. Bajarilishi kutilayotgan vazifalar sonini hisoblash
omi --json action-item list | jq '[.[] | select(.completed == false)] | length'

# 4. Eng so'nggi xotiraning mazmunini o'qish
omi --json memory list --limit 1 | jq -r '.[0].content'
```

---

## 5. Chiqish kodlari va xatolarni boshqarish (Exit Codes)

`omi-cli` POSIX standartlariga va `omi_cli/errors.py` spetsifikatsiyasiga to'liq muvofiq bo'lgan chiqish kodlarini qaytaradi:

| Chiqish kodi | Sabit | Holat | Tavsif va ma'nosi |
| :---: | :--- | :--- | :--- |
| **`0`** | `EXIT_OK` | **Success** | Buyruq muvaffaqiyatli bajarildi. |
| **`1`** | `EXIT_USAGE` | **Usage Error** | `omi-cli` ichki tekshiruvi xatosi (masalan, bir vaqtning o'zida `--browser` va `--api-key` ko'rsatilganda). *Eslatma:* Click tahlilchisining standart sintaksis xatolari **2** kodini qaytaradi. |
| **`2`** | `EXIT_AUTH` | **Auth Error** | API kaliti kiritilmagan, yaroqsiz yoki muddati o'tgan. Click parametrlari xatosi ham shu kodni qaytaradi. |
| **`3`** | `EXIT_SERVER` | **Server / Network** | HTTP 5xx javobi yoki Omi API serveriga ulanishdagi uzilish. |
| **`4`** | `EXIT_RATE_LIMITED` | **Rate Limited** | HTTP 429 javobi. CLI `Retry-After` sarlavhasiga rioya qilgan holda so'rovni qayta yuboradi. |
| **`5`** | `EXIT_NOT_FOUND` | **Not Found** | HTTP 404 javobi. So'ralgan identifikator (ID) bo'yicha obyekt topilmadi. |

> **Kirish tokenini yangilash:** `omi auth refresh` buyrug'i faqat brauzer (OAuth) sessiyalari uchundir. Dasturchi API kalitlari uchun bu buyruq xato qaytaradi (chiqish kodi 1), chunki yangilanadigan token mavjud emas.

---

## 6. Skriptlar va avtomatlashtirish namunalari (Scripting Examples)

### Bash skripti (`sync_omi.sh`)

```bash
#!/usr/bin/env bash
set -euo pipefail

# Autentifikatsiyani server orqali tekshirish
if ! omi auth whoami > /dev/null 2>&1; then
  echo "Xatolik: Omi hisobiga kirilmagan. 'omi auth login' buyrug'ini bajaring." >&2
  exit 2
fi

echo "Omi bilan ma'lumotlar sinxronizatsiyasi boshlanmoqda..."

# So'nggi 5 ta xotirani olish va JSON faylga saqlash
omi --json memory list --limit 5 > /tmp/omi_recent_memories.json

count=$(jq 'length' /tmp/omi_recent_memories.json)
echo "Yuklangan xotiralar soni: $count"
```

### PowerShell skripti (`Sync-Omi.ps1`)

```powershell
$ErrorActionPreference = "Stop"

# Autentifikatsiya holatini tekshirish
omi auth whoami | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Error "Omi autentifikatsiyadan o'tmagan. Iltimos, 'omi auth login' bajaring."
    exit 2
}

# Xotiralarni JSON formatida olish va qayta ishlash (qatorlarni birlashtirish)
$memoriesJson = (omi --json memory list --limit 5) -join "`n"
$memories = $memoriesJson | ConvertFrom-Json

Write-Host "Muvaffaqiyatli yuklandi $($memories.Count) ta xotira."
$memories | ForEach-Object {
    Write-Host "- [$($_.created_at)] $($_.content)"
}
```

---

## 7. Mahalliy Desktop API integratsiyasi (Local Desktop API)

Agar siz Omi Desktop ilovasidan foydalanayotgan bo'lsangiz, CLI mahalliy server orqali ham muloqot qila oladi (standart port: `47778`):

```bash
# Mahalliy manzilni sozlash
export OMI_LOCAL_API_URL="http://localhost:47778"
export OMI_LOCAL_TOKEN="sizning_mahalliy_xavfsizlik_tokeningiz"

# Mahalliy server holatini tekshirish
omi local status
```

---

## 8. Profillar va test muhitlari (Profiles & Staging)

Turli xil hisoblar yoki test muhitlari bilan ishlash:

```bash
# Alohida profil bilan ishlash (masalan, 'work')
omi --profile work memory list

# Staging API muhitida test o'tkazish
omi --api-base https://api.staging.omi.me memory list
```

---

## 9. Xavfsizlik bo'yicha tavsiyalar (Security Best Practices)

1. **Fayl ruxsatlarini cheklang:** Mahalliy hisob ma'lumotlari keshiga faqat sizning foydalanuvchingiz kirishiga ishonch hosil qiling:
   ```bash
   chmod 700 ~/.omi
   [ -f ~/.omi/config.toml ] && chmod 600 ~/.omi/config.toml
   ```
2. **API kalitlarini xavfsiz saqlang:** Hech qachon `omi_dev_...` kalitlarini ochiq kodli Git omborlariga yuklamang. `.gitignore` fayliga `.env` va `*.token` yozuvlarini qo'shing.
3. **Sessiyani tozalash:** Birgalikda foydalaniladigan mashinalarda ishlagandan so'ng muhit o'zgaruvchisini tozalang:
   ```bash
   unset OMI_API_KEY
   omi auth logout
   ```
