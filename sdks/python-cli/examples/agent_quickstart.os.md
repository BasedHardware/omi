# omi-cli агентсӥyet

> LLM-харнескулла (Claude Code, Cursor, дзуар услӥной ботта) практиконгуид.

## Почему CLI агент-дружестны

* **Стабильный JSON contract.** `--json` валидный JSON документ в stdout emitиryd,
  *только* JSON документ — прогресс-сообщениям, спиннеры дандар. Ошибти stderr-ны JSON-дом emitиryd:
  `{"error": "...", "detail": "..."}`.
* **Стабильные exit коды.** `0` досяг / `1` использование / `2` auth / `3` сервер / `4` rate
  ограничен / `5` не найдено. Agenty nyццы коды ветвлят без parsing естелличный язык ошибти.
* **Нет интерактивных промптов в headless контекстах.** Пас `--yes` (или `-y`) для
  разрушительных команд; пас `--api-key` или сет `OMI_API_KEY` для пропуск интерактив
  логин.
* **Forgiving retry поведение.** `429` и `5xx` retryы с backoff перед surfacing.

## Auth (одноразово, человеком)

Пользователь получает dev API key от Omi веб-приложения
(`https://app.omi.me` → Developer → API Keys) и либо:

```bash
omi auth login                          # интерактивный вставка; key не в shell history
# либo
export OMI_API_KEY=omi_dev_...          # эphemeral, container-дружестны
```

## Пять вещей, которые агенты делают чаще всего

### 1. Чтение воспоминаний

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Создание воспоминания

```bash
omi memory create --json "User предпочитает темный режим" --category lifestyle
```

### 3. Чтение разговоров

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Чтение открытых action items

```bash
omi action-item list --json --open
```

### 5. Отметить action item сделанным

```bash
omi action-item complete --json a1b2c3d4
```

## Локальный Desktop API

Когда Omi Desktop exposes свой локальный API, агенты могут запрашивать на-устройстве
screen history, recaps, SQL, и задачи без использования облачного dev API:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# либo, для эphemeral сессий:
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

Только complete или delete задачи когда пользователь явно просит:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` записывает скриншот на диск и все еще
выводит JSON в stdout для скриптов. Скриншот ID обычно приходит от `local search-screen`
или SQL над таблицей `screenshots`. Если Desktop возвращает структурированную ошибку такую как
`screenshot_pending`, `screenshot_file_missing`, или `screenshot_chunk_corrupted`, JSON режим
сохраняет поля `reason`, `hint`, и `screenshot_id` на stderr так что агенты могут повторить попытку
со старым ID или сообщить точную блокировку. Проверьте успешные выводы с `file PATH` перед передачей
в vision инструменты.

## Пример работы: Python агент loop

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Вызвать omi CLI в JSON режиме, вызывая ошибку при не-успешных exit кодах."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI выводит структурированные ошибки в stderr в JSON режиме:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Прочитать все открытые action items и отметить все старше 30 дней complete.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Обработка rate limits

Воспоминания: 120/hr. Разговоры: 25/hr. Batch creates: 15/hr.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] выглядит так: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Советы

* Используйте `--profile <name>` если ваш агент жонглирует несколькими Omi аккаунтами. У каждого
  profile свой собственный credential и API base.
* Используйте `--api-base http://localhost:8080` для локального backend тестирования.
* Используйте `OMI_LOCAL_API_URL` и `OMI_LOCAL_TOKEN` чтобы переопределить profile-настройки
  Desktop API для одного запуска.
* Используйте `--verbose` для отладки — он логирует `METHOD path → status (Ns)` в stderr
  без влияния на stdout, поэтому JSON mode остается валидным.
* Для подачи контента в разговор, используйте `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
