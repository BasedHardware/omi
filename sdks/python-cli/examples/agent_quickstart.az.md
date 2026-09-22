# Agentlər üçün omi-cli

> LLM əsaslı sistemlər (Claude Code, Cursor, şəxsi botlarınız) üçün praktiki bələdçi.

## Niyə CLI agentlər üçün əlverişlidir

* **Sabit JSON protokolu.** `--json` parametri standart çıxışa (stdout) etibarlı bir
  JSON sənədi və *yalnız* JSON sənədi göndərir — heç bir tərəqqi bildirişi və ya yüklənmə
  animasiyası yoxdur. Xətalar standart xəta axınına (stderr) `{"error": "...", "detail": "..."}`
  formatında ötürülür.
* **Sabit çıxış kodları (exit codes).** `0` uğurlu / `1` istifadə xətası / `2` autentifikasiya /
  `3` server / `4` sorğu limiti (rate limit) / `5` tapılmadı. Agentlər təbii dil xətalarını
  təhlil etmədən birbaşa bu kodlara əsasən qərarlar verə bilər.
* **Başsız (headless) mühitlərdə interaktiv sorğuların olmaması.** Dağıdıcı əmrlərə
  `--yes` (və ya `-y`) ötürün; interaktiv girişi keçmək üçün `--api-key` ötürün və ya
  `OMI_API_KEY` mühit dəyişənini təyin edin.
* **Yumşaq təkrar cəhd davranışı.** `429` və `5xx` xətaları ekrana çıxarılmazdan əvvəl
  tədrici gözləmə (backoff) ilə avtomatik yenidən cəhd edilir.

## Autentifikasiya (insan tərəfindən bir dəfə)

İstifadəçi Omi veb tətbiqindən tərtibatçı API açarını əldə edir
(`https://app.omi.me` → Developer → API Keys) və aşağıdakılardan birini seçir:

```bash
omi auth login                          # interaktiv yapışdırma; açar terminal tarixçəsinə düşmür
# və ya
export OMI_API_KEY=omi_dev_...          # birdəfəlik, konteynerlər üçün əlverişli
```

## Agentlərin ən çox yerinə yetirdiyi beş əməliyyat

### 1. Xatirələri oxumaq

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Xatirə yaratmaq

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Söhbətləri oxumaq

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Açıq tapşırıqları oxumaq

```bash
omi action-item list --json --open
```

### 5. Tapşırığı tamamlanmış kimi qeyd etmək

```bash
omi action-item complete --json a1b2c3d4
```

## Yerli Desktop API

Omi Desktop öz yerli API-sini aktivləşdirdikdə, agentlər bulud tərtibatçı API-sindən
istifadə etmədən cihazdakı ekran tarixçəsini, icmalları, SQL sorğularını və tapşırıqları
sorğulaya bilər:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# və ya müvəqqəti sessiyalar üçün:
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

Tapşırıqları yalnız istifadəçi açıq şəkildə tələb etdikdə tamamlayın və ya silin:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` skrinşotu diskə yazır və skriptlər
üçün stdout-a JSON çıxarmağa davam edir. Skrinşot identifikatoru adətən `local search-screen`
və ya `screenshots` cədvəli üzrə SQL sorğusundan əldə edilir. Əgər Desktop `screenshot_pending`,
`screenshot_file_missing` və ya `screenshot_chunk_corrupted` kimi strukturlaşdırılmış
uğursuzluq qaytararsa, JSON rejimi stderr-də `reason`, `hint` və `screenshot_id` sahələrini
saxlayır ki, agentlər daha əvvəlki ID ilə yenidən cəhd edə və ya maneəni dəqiq bildirə bilsin.
Uğurlu çıxışları vizual alətlərə ötürməzdən əvvəl `file PATH` vasitəsilə yoxlayın.

## Praktiki nümunə: Python agent dövrü

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """omi CLI-ni JSON rejimində çağırır, uğursuzluq kodlarında xəta qaldırır."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI JSON rejimində stderr-ə strukturlaşdırılmış xətalar çıxarır:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Bütün açıq tapşırıqları oxuyun və 30 gündən köhnə olanları tamamlanmış qeyd edin.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Sorğu limitlərinin idarə edilməsi

Xatirələr: 120/saat. Söhbətlər: 25/saat. Toplu yaratmalar: 15/saat.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # sorğu limiti aşıldı
    err = json.loads(result.stderr)
    # err["detail"] belə görünür: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Məsləhətlər

* Əgər agentiniz bir neçə Omi hesabı ilə işləyirsə, `--profile <ad>` parametrindən
  istifadə edin. Hər profilin öz giriş məlumatı və baza API ünvanı var.
* Yerli backend testləri üçün `--api-base http://localhost:8080` istifadə edin.
* Bir icra üçün profilin yerli Desktop API parametrlərini əvəzləmək məqsədilə
  `OMI_LOCAL_API_URL` və `OMI_LOCAL_TOKEN` istifadə edin.
* Sazlama (debugging) üçün `--verbose` istifadə edin — bu parametr stdout-a təsir
  etmədən `METHOD path → status (Ns)` məlumatını stderr-ə qeyd edir, beləliklə JSON rejimi pozulmur.
* Məzmunu söhbətə ötürmək üçün `--text -` istifadə edin:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
