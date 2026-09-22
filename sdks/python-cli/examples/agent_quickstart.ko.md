# AI 에이전트를 위한 omi-cli 가이드

> LLM 기반 환경(Claude Code, Cursor, 커스텀 봇)을 위한 실용적인 안내서입니다.

## CLI가 에이전트에 최적화된 이유

* **안정적인 JSON 인터페이스:** `--json` 플래그를 사용하면 stdout으로 유효한 JSON만 출력되며 상태 로그나 스피너가 섞이지 않습니다. 오류는 stderr로 `{"error": "...", "detail": "..."}` 형식으로 출력됩니다.
* **명확한 종료 코드:** `0` 정상 / `1` 사용 오류 / `2` 인증 실패 / `3` 서버 오류 / `4` 요청 속도 제한 초과 / `5` 항목 없음. 에이전트는 복잡한 문자열 파싱 없이 종료 코드로 직접 분기할 수 있습니다.
* **헤드리스 환경에서 대화형 프롬프트 없음:** 변경 또는 삭제 명령에는 `--yes`(또는 `-y`)를 전달하고, `--api-key` 또는 `OMI_API_KEY` 환경 변수를 사용하여 대화형 웹 로그인을 건너뛸 수 있습니다.
* **자동 재시도 메커니즘:** `429` 및 `5xx` 응답에 대해 지수 백오프를 통해 자동으로 재시도한 후 오류를 반환합니다.

## 인증 (사용자 1회 설정)

사용자가 Omi 웹 애플리케이션(`https://app.omi.me` → Developer → API Keys)에서 개발자 API 키를 발급받은 후 다음 중 하나를 실행합니다:

```bash
omi auth login                          # 대화형 붙여넣기 (셸 기록에 키가 남지 않음)
# 또는
export OMI_API_KEY=omi_dev_...          # 컨테이너 및 CI/CD 환경용
```

## 에이전트가 가장 자주 사용하는 5가지 작업

### 1. 메모리 읽기

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. 메모리 생성

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. 대화 목록 읽기

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. 미해결 할 일 목록(Action items) 읽기

```bash
omi action-item list --json --open
```

### 5. 할 일 항목 완료 처리

```bash
omi action-item complete --json a1b2c3d4
```

## 로컬 데스크톱 API (Local Desktop API)

Omi Desktop이 로컬 API를 활성화하면 에이전트는 클라우드 dev API를 거치지 않고 장치의 화면 기록, 요약, SQL 및 작업을 로컬에서 직접 쿼리할 수 있습니다:

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

작업을 완료하거나 삭제할 때는 사용자가 명시적으로 요청한 경우에만 실행하십시오:

사용자가 명시적으로 요청한 경우에만 작업을 완료하거나 삭제하십시오:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` 명령은 스크린샷을 디스크에 저장하고 스크립트를 위해 stdout에 JSON을 출력합니다. 스크린샷 ID는 일반적으로 `local search-screen` 또는 `screenshots` 테이블의 SQL 쿼리에서 가져옵니다. Desktop 앱에서 `screenshot_pending`, `screenshot_file_missing` 또는 `screenshot_chunk_corrupted`와 같은 구조화된 오류를 반환하는 경우, JSON 모드는 stderr에 `reason`, `hint` 및 `screenshot_id` 필드를 유지하므로 에이전트가 이전 ID로 재시도하거나 정확한 문제를 보고할 수 있습니다. 비전 도구에 전달하기 전에 `file PATH`로 출력을 검증하십시오.

## 실전 예제: Python 에이전트 루프

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Invoke the omi CLI in JSON mode, raising on non-success exit codes."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # The CLI prints structured errors to stderr in JSON mode:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Read all open action items and mark anything older than 30 days complete.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## 속도 제한 처리 (Handling rate limits)

기억: 120회/시간. 대화: 25회/시간. 일괄 생성: 15회/시간.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## 유용한 팁 (Tips)

* 에이전트가 여러 Omi 계정을 다루는 경우 `--profile <이름>`을 사용하십시오. 각 프로필은 고유한 자격 증명과 API 기본 URL을 가집니다.
* 로컬 백엔드 테스트에는 `--api-base http://localhost:8080`을 사용하십시오.
* 단일 실행을 위해 프로필의 로컬 Desktop API 설정을 재정의하려면 `OMI_LOCAL_API_URL` 및 `OMI_LOCAL_TOKEN`을 사용하십시오.
* 디버깅에는 `--verbose`를 사용하십시오. stdout에 영향을 주지 않고 stderr에 `METHOD path → status (Ns)`를 로깅하므로 JSON 모드가 유효하게 유지됩니다.
* 파이프를 통해 대화에 콘텐츠를 전달하려면 `--text -`를 사용하십시오:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
