# omi-cli 에이전트용

> LLM 기반 하네스를 위한 실용 가이드 (Claude Code, Cursor, 자체 봇).

## CLI가 에이전트 친화적인 이유

* **안정적인 JSON 계약.** `--json`은 stdout에 유효한 JSON 문서를, 그리고 *오직* JSON만 출력합니다 — 진행 메시지나 스피너가 없습니다. 오류는 stderr로 `{"error": "...", "detail": "..."}` 형식입니다.
* **안정적인 종료 코드.** `0` 성공 / `1` 사용법 / `2` 인증 / `3` 서버 / `4` rate limited / `5` 찾을 수 없음. 에이전트는 자연어 오류를 파싱하지 않고도 이들로 분기할 수 있습니다.
* **헤드리스 컨텍스트에서 인터랙티브 프롬프트 없음.** 파괴적 명령에는 `--yes`(또는 `-y`)를 넘기고, 인터랙티브 로그인을 건너뛰려면 `--api-key`를 넘기거나 `OMI_API_KEY`를 설정하세요.
* **관대한 재시도 동작.** `429`와 `5xx`는 표면화되기 전에 백오프로 재시도됩니다.

## 인증 (한 번, 사람이 수행)

사용자는 Omi 웹 앱에서 dev API key를 얻습니다
(`https://app.omi.me` → Developer → API Keys) 그리고:

```bash
omi auth login                          # 인터랙티브 붙여넣기; 셸 히스토리에 키 없음
# # 또는
export OMI_API_KEY=omi_dev_...          # 휘발성, 컨테이너 친화적
```

## 에이전트가 가장 많이 하는 다섯 가지

### 1. 메모리 읽기

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. 메모리 생성

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. 대화 읽기

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. 열린 작업 항목 읽기

```bash
omi action-item list --json --open
```

### 5. 작업 항목을 완료로 표시

```bash
omi action-item complete --json a1b2c3d4
```

## 로컬 Desktop API

Omi Desktop이 로컬 API를 노출하면 에이전트는 클라우드 dev API 없이
온디바이스 화면 기록, 요약, SQL, 작업을 조회할 수 있습니다:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# # 또는, 임시 세션의 경우:
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

사용자가 명확히 요청할 때만 작업을 완료 또는 삭제하세요:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH`는 스크린샷을 디스크에
쓰고 스크립트용으로 stdout에 JSON을 계속 출력합니다. 스크린샷 ID는 보통
`local search-screen` 또는 `screenshots` 테이블에 대한 SQL에서 옵니다. Desktop이
`screenshot_pending`, `screenshot_file_missing`, `screenshot_chunk_corrupted`
같은 구조화된 실패를 반환하면, JSON 모드는 stderr에 `reason`, `hint`,
`screenshot_id` 필드를 보존하므로 에이전트가 이전 ID를 재시도하거나 정확한
차단 요인을 보고할 수 있습니다. 성공적인 출력은 비전 도구에 넘기기 전에
`file PATH`로 검증하세요.

## 예제: Python 에이전트 루프

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

# 열린 작업 항목을 모두 읽고 30일이 지난 것은 완료로 표시.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## 속도 제한 처리

메모리: 시간당 120. 대화: 시간당 25. 일괄 생성: 시간당 15.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"]은 이런 형태입니다: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## 팁

* 에이전트가 여러 Omi 계정을 다룬다면 `--profile <name>`을 사용하세요. 각
  프로필은 자체 자격 증명과 API 베이스를 가집니다.
* 로컬 백엔드 테스트에는 `--api-base http://localhost:8080`을 사용하세요.
* `OMI_LOCAL_API_URL`과 `OMI_LOCAL_TOKEN`으로 한 번의 실행에 대해 프로필
  Desktop API 설정을 덮어쓸 수 있습니다.
* 디버깅에는 `--verbose`를 사용하세요 — `METHOD path → status (Ns)`를 stderr에
  로깅하고 stdout에는 영향이 없으므로 JSON 모드는 유효한 상태를 유지합니다.
* 대화에 콘텐츠를 파이프하려면 `--text -`를 사용하세요:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
