# 에이전트를 위한 omi-cli

> LLM 기반 하네스(Claude Code, Cursor, 자체 봇 등)를 위한 실전 가이드.

## CLI가 에이전트에 적합한 이유

* **안정적인 JSON 계약(Contract).** `--json`은 stdout으로 유효한 JSON 문서만을 출력합니다. 진행 상태 메시지나 로딩 스피너는 일체 포함되지 않습니다. 에러는 stderr로 `{"error": "...", "detail": "..."}` 형식으로 출력됩니다.
* **안정적인 종료 코드(Exit Codes).** `0` 정상 / `1` 사용법 오류 / `2` 인증 실패 / `3` 서버 에러 / `4` 요청 속도 제한(Rate limited) / `5` 찾을 수 없음(Not found). 에이전트는 자연어 오류 메시지를 파싱할 필요 없이 이 종료 코드를 기반으로 즉시 분기 처리할 수 있습니다.
* **헤드리스(Headless) 환경에서 대화형 프롬프트 없음.** 파괴적인 명령어에는 `--yes`(또는 `-y`)를 전달하세요. `--api-key`를 전달하거나 `OMI_API_KEY` 환경 변수를 설정하여 대화형 로그인을 건너뛸 수 있습니다.
* **유연한 재시도 동작.** `429` 및 `5xx` 에러는 표면화되기 전에 지수 백오프(Exponential backoff)를 통해 자동으로 재시도됩니다.

## 인증 (사람이 최초 1회 수행)

사용자는 Omi 웹 앱(`https://app.omi.me` → Developer → API Keys)에서 개발자 API 키를 발급받은 후 다음 중 하나를 선택합니다:

```bash
omi auth login                          # 대화형 붙여넣기; 셸 기록에 키가 남지 않음
# 또는
export OMI_API_KEY=omi_dev_...          # 임시 세션용, 컨테이너 친화적
```

## 에이전트가 가장 자주 수행하는 5가지 작업

### 1. 기억 읽기

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. 기억 생성하기

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. 대화 읽기

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. 미완료 할 일 읽기

```bash
omi action-item list --json --open
```

### 5. 할 일을 완료로 표시하기

```bash
omi action-item complete --json a1b2c3d4
```

## 로컬 데스크톱 API

Omi Desktop이 로컬 API를 노출할 때, 에이전트는 클라우드 개발자 API를 사용하지 않고도 기기 내 화면 기록, 리캡, SQL, 작업을 직접 쿼리할 수 있습니다:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# 또는 임시 세션의 경우:
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

사용자가 명시적으로 요청한 경우에만 작업을 완료하거나 삭제하세요:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH`는 스크린샷을 디스크에 저장하고 스크립트를 위해 stdout에 JSON을 출력합니다. 스크린샷 ID는 일반적으로 `local search-screen` 또는 `screenshots` 테이블에 대한 SQL 쿼리를 통해 가져옵니다. Desktop이 `screenshot_pending`, `screenshot_file_missing`, `screenshot_chunk_corrupted`와 같은 구조화된 실패를 반환하면, JSON 모드는 stderr에 `reason`, `hint`, `screenshot_id` 필드를 유지하므로 에이전트가 이전 ID로 재시도하거나 정확한 장애 원인을 보고할 수 있습니다. 비전 도구에 전달하기 전에 `file PATH`로 출력 파일을 검증하세요.

## 실전 예제: Python 에이전트 루프

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """JSON 모드로 omi CLI를 호출하며, 종료 코드가 성공이 아닌 경우 예외를 발생시킵니다."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI는 JSON 모드에서 stderr로 구조화된 에러를 출력합니다:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# 모든 미완료 할 일을 읽고 30일보다 오래된 항목을 완료로 표시합니다.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## 속도 제한 처리

기억: 120회/시간. 대화: 25회/시간. 일괄 생성: 15회/시간.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # 속도 제한 도달
    err = json.loads(result.stderr)
    # err["detail"] 예시: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## 유용한 팁

* 에이전트가 여러 Omi 계정을 관리해야 하는 경우 `--profile <name>`을 사용하세요. 각 프로필은 자체 인증 정보와 API 베이스를 가집니다.
* 로컬 백엔드 테스트에는 `--api-base http://localhost:8080`을 사용하세요.
* 한 번의 실행 동안 프로필의 로컬 Desktop API 설정을 재정의하려면 `OMI_LOCAL_API_URL` 및 `OMI_LOCAL_TOKEN`을 사용하세요.
* 디버깅 시 `--verbose`를 사용하세요. 이는 stdout에 영향을 주지 않고 `METHOD path → status (Ns)`를 stderr에 로깅하므로 JSON 모드가 유효하게 유지됩니다.
* 대화에 파이프를 통해 콘텐츠를 전달하려면 `--text -`를 사용하세요:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
