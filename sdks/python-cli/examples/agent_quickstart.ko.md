# 에이전트를 위한 omi-cli

> LLM 기반 환경(Claude Code, Cursor, 자체 개발 봇)을 위한 실용적인 가이드.

## CLI가 에이전트에 이상적인 이유

* **안정적인 JSON 인터페이스.** `--json` 플래그는 `stdout`으로 유효한 JSON 문서만
  출력합니다. 진행률 표시나 로딩 스피너가 전혀 섞이지 않습니다. 오류는
  `stderr`에 `{"error": "...", "detail": "..."}` 형식으로 출력됩니다.
* **명확한 종료 코드.** `0` 성공 / `1` 사용법 오류 / `2` 인증 실패 / `3` 서버 오류 / `4` 요청 한도
  초과(rate limit) / `5` 리소스 없음. 에이전트는 자연어 오류 메시지를 파싱할 필요 없이 종료 코드만으로 분기 처리할 수 있습니다.
* **비대화형(Headless) 환경 지원.** 파괴적인 명령에는 `--yes`(또는 `-y`)를 전달하고,
  대화형 로그인을 건너뛰려면 `--api-key`를 전달하거나 `OMI_API_KEY` 환경 변수를 설정하세요.
* **복원력 있는 재시도 동작.** `429` 및 `5xx` 오류는 사용자에게 노출되기 전에 지수 백오프(exponential backoff)를 통해
  자동으로 재시도됩니다.

## 인증 (사용자가 최초 1회 수행)

사용자는 Omi 웹 앱(`https://app.omi.me` → Developer → API Keys)에서 개발자 API 키를 발급받아
다음 중 한 가지 방법으로 설정합니다:

```bash
omi auth login                          # 대화형 붙여넣기 (셸 기록에 키가 남지 않음)
# 또는
export OMI_API_KEY=omi_dev_...          # 임시 설정 (컨테이너 환경에 권장)
```

## 에이전트의 5가지 주요 작업

### 1. 기억(Memories) 목록 조회

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. 새 기억 생성

```bash
omi memory create --json "사용자는 다크 모드를 선호합니다" --category lifestyle
```

### 3. 대화 목록 조회

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. 미완료 할 일(Action Items) 목록 조회

```bash
omi action-item list --json --open
```

### 5. 할 일 완료 처리

```bash
omi action-item complete --json a1b2c3d4
```

## 데스크톱 로컬 API

Omi Desktop이 로컬 API를 활성화한 경우, 에이전트는 클라우드 개발자 API를 거치지 않고도
기기 내 화면 기록, 요약, SQL 조회 및 작업을 쿼리할 수 있습니다:

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

작업 완료 또는 삭제는 사용자가 명시적으로 요청한 경우에만 수행해야 합니다:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` 명령은 스크린샷을 디스크에 저장하면서
스크립트 처리를 위해 `stdout`으로 JSON을 계속 출력합니다. 스크린샷 ID는 일반적으로
`local search-screen` 또는 `screenshots` 테이블에 대한 SQL 쿼리에서 가져옵니다. Desktop에서
`screenshot_pending`, `screenshot_file_missing`, `screenshot_chunk_corrupted`와 같은
구조화된 오류를 반환하면 JSON 모드는 `stderr`에 `reason`, `hint`, `screenshot_id` 필드를
유지하므로 에이전트가 이전 ID로 재시도하거나 정확한 실패 원인을 보고할 수 있습니다. 성공적으로 저장된 파일은
비전 모델 도구로 전달하기 전에 `file PATH`로 검증하세요.

## 실용 예제: Python 에이전트 루프

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """JSON 모드로 omi CLI를 호출하며, 0이 아닌 종료 코드 시 예외를 발생시킵니다."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI는 JSON 모드에서 stderr로 구조화된 오류를 출력합니다:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi가 코드 {result.returncode}로 종료되었습니다: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# 모든 미완료 할 일을 조회하고 30일 이상 지난 항목은 완료 처리합니다.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## 요청 한도(Rate Limits) 처리

기억: 120회/시간. 대화: 25회/시간. 일괄 생성: 15회/시간.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # 요청 한도 도달
    err = json.loads(result.stderr)
    # err["detail"] 형식: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## 유용한 팁

* 에이전트가 여러 Omi 계정을 관리하는 경우 `--profile <name>`을 사용하세요. 각
  프로필마다 고유한 자격 증명과 API 기본 경로를 유지합니다.
* 로컬 백엔드 테스트에는 `--api-base http://localhost:8080`을 사용하세요.
* 단일 실행에서 프로필의 데스크톱 로컬 API 설정을 재정의하려면 `OMI_LOCAL_API_URL` 및 `OMI_LOCAL_TOKEN`을 사용하세요.
* 디버깅 시 `--verbose`를 사용하세요: `stdout`을 오염시키지 않고 `stderr`에
  `METHOD path status (Ns)`를 기록하므로 유효한 JSON 스트림이 유지됩니다.
* 파이프를 통해 대화 내용을 생성하려면 `--text -`를 사용하세요:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
