# omi-cli хурдан эхлүүлэх гарын авлага (Mongolian Quickstart)

> Omi-той терминалаас шууд ажиллахад зориулсан практик гарын авлага — хөгжүүлэгчид болон бие даасан AI агентуудад зориулав.

`omi-cli` — [Omi](https://omi.me) платформын хөгжүүлэгчийн API-д зориулсан албан ёсны командын мөрийн интерфейс (CLI) юм. Энэ нь системд хадгалагддаг дөрвөн үндсэн нөөцөд зохион байгуулалттай, агентуудад ээлтэй байдлаар хандах боломжийг олгодог: **дурсамжууд** (memories), **ярианууд** (conversations), **гүйцэтгэх ажлууд** (action items) болон **зорилтууд** (goals).

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Албан ёсны баримт бичиг:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Эх код:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Суулгах (Installation)

Багцын зөрчлөөс сэргийлэх, цэвэр орчин хадгалахын тулд `pipx` хэрэгслийг ашиглахыг зөвлөж байна:

```bash
# Зөвлөмж: pipx ашиглан тусгаарласан орчинд суулгах
pipx install omi-cli

# Стандарт pip ашиглан суулгах (жишээ нь виртуал орчинд)
pip install omi-cli
```

> **Чухал ялгаа: Багцын нэр ба командын нэр**
> * Суулгах багцын нэр — **`omi-cli`**.
> * Терминалаас ажиллуулах үндсэн командын нэр — **`omi`**.

Суулгацын хувилбарыг шалгах:

```bash
omi --version
```

---

## 2. Баталгаажуулалт (Authentication)

`omi-cli` нь хоёр үндсэн баталгаажуулалтын аргыг дэмждэг: **Вэб хөтчөөр дамжуулан OAuth** (хэрэглэгчдэд зориулсан) болон **Хөгжүүлэгчийн API түлхүүр** (автоматжуулалт болон AI агентуудад зориулсан).

### А арга: Вэб хөтчөөр нэвтрэх (Хэрэглэгчид)

Үндсэн нэвтрэх арга нь Google бүртгэлийг ашигладаг:

```bash
omi auth login
```

Apple бүртгэлээр нэвтрэх:

```bash
omi auth login --browser --provider apple
```

### Б арга: Хөгжүүлэгчийн API түлхүүр (Агентууд болон CI/CD системүүд)

Автомат скриптүүд, арын процесс болон бие даасан AI агентуудад Omi порталаас авсан API түлхүүрийг ашиглана (түлхүүр `omi_dev_` угтвартай эхэлнэ):

```bash
# Орчны хувьсагчаар дамжуулан тохируулах (зөвлөмж)
export OMI_API_KEY="omi_dev_таны_жинхэнэ_түлхүүр"

# Эсвэл түлхүүрийг кэшд хадгалах
omi auth login --api-key omi_dev_таны_жинхэнэ_түлхүүр
```

### Баталгаажуулалтын төлөвийг шалгах

```bash
# Офлайн шалгалт: локал кэшд итгэмжлэл хадгалагдсан эсэхийг шалгана
omi auth status

# Онлайн шалгалт: Omi сервер рүү хүсэлт илгээж, нэвтэрсэн хэрэглэгчийн мэдээллийг баталгаажуулна
omi auth whoami
```

Системээс гарах (кэш цэвэрлэх):

```bash
omi auth logout
```

---

## 3. Үндсэн командууд ба нөөцүүд (Core Commands & Resources)

Omi нь дөрвөн үндсэн нөөц дээр суурилдаг.

### 1. Дурсамжууд (Memories)

Дурсамжууд — Omi-ийн аудио болон ярианаас автоматаар ялган бүртгэсэн баримт, тэмдэглэлүүд.

```bash
# Бүх дурсамжийн жагсаалтыг харах
omi memory list

# Хамгийн сүүлийн 5 дурсамжийг авах
omi memory list --limit 5

# Хуудаслалт (дараагийн 10 бичлэгийг үзэх)
omi memory list --limit 10 --offset 10

# Тодорхой нэг дурсамжийн мэдээллийг харах
omi memory get <memory-id>

# Шинэ дурсамж үүсгэх
omi memory create "Үйлчлүүлэгчтэй шинэ төслийн талаар ярилцав"
```

### 2. Ярианууд (Conversations)

Omi-ийн аудио транскрипц болон харилцааны түүх.

```bash
# Яриануудын жагсаалтыг авах
omi conversation list

# Тодорхой ярианы бүтэн бичлэгийг үзэх
omi conversation get <conversation-id>
```

### 3. Гүйцэтгэх ажлууд (Action Items)

Ярианы явцад тодорхойлогдсон үүрэг, даалгаврууд.

```bash
# Бүх ажлуудын жагсаалт
omi action-item list

# Гүйцэтгээгүй (нээлттэй) ажлууд
omi action-item list --open

# Ажлын төлөвийг шинэчлэх (гүйцэтгэсэн болгох)
omi action-item update <item-id> --completed
```

### 4. Зорилтууд (Goals)

Урт хугацааны зорилтууд болон явцын хяналт.

```bash
# Бүх зорилтыг харах
omi goal list

# Шинэ зорилт нэмэх
omi goal create "Python CLI тестийг 100 хувьд хүргэх"
```

---

## 4. Машинаар боловсруулах: Глобал `--json` туг (JSON Output & Agent Pipeline)

AI агентууд болон бүрхүүл (shell) скриптүүдэд зориулж өгөгдлийг JSON хэлбэрээр боловсруулах боломжтой.

> **Чухал дүрэм: `--json` тугийн байрлал**
> `--json` туг нь **глобал параметр** бөгөөд үндсэн `omi` командын яг ард, дэд команд (subcommand)-ын өмнө байх ёстой:
>
> ```bash
> # Зөв:
> omi --json memory list
> omi --json conversation list --limit 5
>
> # Буруу (Click дэд командын параметр гэж үзэн алдаа заана):
> omi memory list --json
> ```

### `jq` хэрэгсэлтэй холбох жишээнүүд

```bash
# 1. Дурсамжийн ID, агуулга, үүсгэсэн огноог ялгаж авах
omi --json memory list | jq '.[] | {id: .id, content: .content, created_at: .created_at}'

# 2. Ярианы ID болон сэдвийг авах
omi --json conversation list | jq -r '.[] | "\(.id): \(.structured.title)"'

# 3. Гүйцэтгээгүй үлдсэн даалгавруудын тоог олох
omi --json action-item list | jq '[.[] | select(.completed == false)] | length'

# 4. Хамгийн сүүлийн дурсамжийн цэвэр агуулгыг унших
omi --json memory list --limit 1 | jq -r '.[0].content'
```

---

## 5. Гаралтын кодууд ба алдааг зохицуулах (Exit Codes)

`omi-cli` нь POSIX стандарт болон `omi_cli/errors.py` тодорхойлолтод бүрэн нийцсэн дараах гаралтын кодуудыг буцаана:

| Гаралтын код | Тогтмол (Constant) | Төлөв (Status) | Тайлбар ба учир шалтгаан |
| :---: | :--- | :--- | :--- |
| **`0`** | `EXIT_OK` | **Амжилттай (Success)** | Команд амжилттай биелсэн. |
| **`1`** | `EXIT_USAGE` | **Ашиглалтын алдаа (Usage Error)** | `omi-cli` дотоод шалгалтын алдаа (жишээ нь `--browser` ба `--api-key` зэрэг өгөх). Click синтаксийн алдаа **2** кодыг буцаана. |
| **`2`** | `EXIT_AUTH` | **Нэвтрэлтийн алдаа (Auth Error)** | API түлхүүр дутуу, буруу эсвэл хугацаа нь дууссан. Click параметрийн алдаа ч мөн адил. |
| **`3`** | `EXIT_SERVER` | **Сервер / Сүлжээ (Server / Network)** | HTTP 5xx хариу эсвэл Omi сервертэй холбогдож чадсангүй. |
| **`4`** | `EXIT_RATE_LIMITED` | **Хязгаарлалт (Rate Limited)** | HTTP 429 хариу. CLI `Retry-After` толгойг баримтлан автоматаар дахин оролдоно. |
| **`5`** | `EXIT_NOT_FOUND` | **Олдсонгүй (Not Found)** | HTTP 404 хариу. Заасан танигчаар (ID) өгөгдөл олдсонгүй. |

> **Нэвтрэх токен шинэчлэх:** `omi auth refresh` команд нь зөвхөн вэб хөтчийн (OAuth) сессэд зориулагдсан. Хөгжүүлэгчийн API түлхүүрийн хувьд энэ команд алдаа заана (гаралтын код 1), учир нь шинэчлэх токен байхгүй.

---

## 6. Скрипт ба автоматжуулалтын жишээнүүд (Scripting Examples)

### Bash скрипт (`sync_omi.sh`)

```bash
#!/usr/bin/env bash
set -euo pipefail

# Баталгаажуулалтыг серверээр шалгах
if ! omi auth whoami > /dev/null 2>&1; then
  echo "Алдаа: Omi-д нэвтрээгүй байна. 'omi auth login' командыг ажиллуулна уу." >&2
  exit 2
fi

echo "Omi-той мэдээлэл синк хийж байна..."

# Сүүлийн 5 дурсамжийг JSON хэлбэрээр хадгалах
omi --json memory list --limit 5 > /tmp/omi_recent_memories.json

count=$(jq 'length' /tmp/omi_recent_memories.json)
echo "Амжилттай татсан дурсамжийн тоо: $count"
```

### PowerShell скрипт (`Sync-Omi.ps1`)

```powershell
$ErrorActionPreference = "Stop"

# Баталгаажуулалтыг серверээр шалгах
omi auth whoami | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Error "Omi баталгаажуулалт амжилтгүй. 'omi auth login' ажиллуулна уу."
    exit 2
}

# Дурсамжийг JSON-оор татан авч боловсруулах (мөрүүдийг нэгтгэх)
$memoriesJson = (omi --json memory list --limit 5) -join "`n"
$memories = $memoriesJson | ConvertFrom-Json

Write-Host "Амжилттай татагдсан $($memories.Count) дурсамж байна."
$memories | ForEach-Object {
    Write-Host "- [$($_.created_at)] $($_.content)"
}
```

---

## 7. Локал Desktop API интеграци (Local Desktop API)

Хэрэв Omi Desktop програм таны төхөөрөмж дээр ажиллаж байгаа бол CLI локал сервертэй холбогдох боломжтой (үндсэн порт: `47778`):

```bash
# Локал серверийн хаягийг тохируулах
export OMI_LOCAL_API_URL="http://localhost:47778"
export OMI_LOCAL_TOKEN="таны_локал_аюулгүй_байдлын_токен"

# Локал серверийн төлөв шалгах
omi local status
```

---

## 8. Профайл ба тестийн орчин (Profiles & Staging)

Олон бүртгэл эсвэл тестийн орчин хооронд шилжих:

```bash
# Тусдаа профайлаар ажиллах (жишээ нь 'work')
omi --profile work memory list

# Staging API орчинд турших
omi --api-base https://api.staging.omi.me memory list
```

---

## 9. Аюулгүй байдлын зөвлөмж (Security Best Practices)

1. **Файлын эрхийг хязгаарлах:** Локал итгэмжлэлийн файлд зөвхөн таны хэрэглэгч хандах эрхтэй эсэхийг баталгаажуулаарай:
   ```bash
   chmod 700 ~/.omi
   [ -f ~/.omi/credentials.json ] && chmod 600 ~/.omi/credentials.json
   ```
2. **API түлхүүрийг хамгаалах:** `omi_dev_...` түлхүүрийг хэзээ ч олон нийтэд нээлттэй Git санд бүү байршуул. `.gitignore` файлд `.env` болон `*.token` бичиглэлүүдийг заавал нэмнэ.
3. **Хандалтыг цэвэрлэх:** Нийтийн болон хуваалцдаг серверүүд дээр ажиллаж дууссаны дараа орчны хувьсагчийг устгана:
   ```bash
   unset OMI_API_KEY
   omi auth logout
   ```
