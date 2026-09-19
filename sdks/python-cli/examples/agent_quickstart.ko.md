# 에이전트를 위한 omi-cli

> LLM 기반 하네스(Claude Code, Cursor, 자체 봇)를 위한 실용적인 가이드.

## CLI가 에이전트 친화적인 이유

* **안정적인 JSON 계약.** `--json`은 stdout으로 오직 유효한 JSON 문서만을 출력합니다.
  진행률 표시나 스피너는 전혀 없습니다. 오류는 stderr로
  `{"error": "...", "detail": "..."}` 형식으로 전송됩니다.
* **안정적인 종료 코드.** `0` 성공 / `1` 사용법 오류 / `2` 인증 실패 / `3` 서버 오류 /
  `4` 속도 제한 / `5` 찾을 수 없음. 에이전트는 자연어 오류를 구문 분석하지 않고도
  종료 코드를 기반으로 직접 분기할 수 있습니다.
* **헤드리스 환경에서 대화형 프롬프트 없음.** 파괴적인 명령에는 `--yes`(또는 `-y`)를 전달하세요.
  대화형 로그인을 건너뛰려면 `--api-key`를 전달하거나 `OMI_API_KEY`를 설정하세요.
* **관대한 재시도 동작.** `429` 및 `5xx` 오류는 사용자에게 노출되기 전에
  지수 백오프와 함께 자동으로 재시도됩니다.

## 인증 (인간 사용자의 1회 설정)

사용자는 Omi 웹 앱(`https://app.omi.me` → Developer → API Keys)에서
개발자 API 키를 발급받은 후 다음 중 하나를 실행합니다:

```bash
omi auth login                          # 대화형 붙여넣기; 키가 셸 기록에 남지 않음
# 또는
export OMI_API_KEY=omi_dev_...          # 일회성, 컨테이너 친화적
```

## 에이전트가 가장 많이 수행하는 5가지 작업

### 1. 기억 읽기

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. 기억 생성하기

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. 대화 목록 읽기

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. 진행 중인 할 일 항목 읽기

```bash
omi action-item list --json --open
```

### 5. 할 일 항목 완료 표시하기

```bash
omi action-item complete --json a1b2c3d4
```

## 로컬 데스크톱 API

Omi 데스크톱이 로컬 API를 노출하면, 에이전트는 클라우드 개발자 API 없이도
기기 내 화면 기록, 요약, SQL 및 작업을 쿼리할 수 있습니다:

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

사용자가 명확하게 요청한 경우에만 작업을 완료하거나 삭제하세요:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH`는 스크린샷을 디스크에 기록하고
스크립트를 위해 stdout에 계속 JSON을 출력합니다. 스크린샷 ID는 일반적으로
`local search-screen` 또는 `screenshots` 테이블에 대한 SQL 쿼리에서 가져옵니다.
데스크톱에서 `screenshot_pending`, `screenshot_file_missing`, `screenshot_chunk_corrupted`와 같은
구조화된 오류를 반환하는 경우, JSON 모드는 stderr에 `reason`, `hint`, `screenshot_id` 필드를 유지하므로
에이전트가 이전 ID로 재시도하거나 정확한 차단 요인을 보고할 수 있습니다.
시각 도구로 전달하기 전에 `file PATH`로 유효성을 검증하세요.

## 실제 예제: Python 에이전트 루프

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

## 속도 제한 처리

기억: 시간당 120회. 대화: 시간당 25회. 일괄 생성: 시간당 15회.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## 팁

* 에이전트가 여러 Omi 계정을 관리하는 경우 `--profile <name>`을 사용하세요.
  각 프로필에는 고유한 자격 증명과 API 기본 경로가 있습니다.
* 로컬 백엔드 테스트에는 `--api-base http://localhost:8080`을 사용하세요.
* 단일 실행에 대해 프로필 로컬 데스크톱 API 설정을 재정의하려면 `OMI_LOCAL_API_URL` 및 `OMI_LOCAL_TOKEN`을 사용하세요.
* 디버깅 시 `--verbose`를 사용하세요 — stdout에 영향을 주지 않고 stderr에 `METHOD path → status (Ns)`를 기록하므로 JSON 모드가 유효하게 유지됩니다.
* 대화에 콘텐츠를 파이프로 전달하려면 `--text -`를 사용하세요:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
