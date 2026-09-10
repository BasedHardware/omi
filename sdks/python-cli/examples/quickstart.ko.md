# omi-cli 빠른 시작 가이드 (Korean Quickstart)

> 터미널에서 Omi와 직접 상호작용하기 위한 실용 가이드 — 개발자와 자율 AI 에이전트 모두를 위해 설계되었습니다.

`omi-cli`는 [Omi](https://omi.me) 개발자 API를 위한 공식 명령줄 인터페이스입니다. 시스템의 핵심 4대 리소스인 메모리(memories), 대화(conversations), 작업 항목(action items), 목표(goals)를 정형화되고 자동화 가능한 방식으로 관리할 수 있습니다.

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **공식 문서:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **소스 코드:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. 설치

시스템 의존성 충돌을 방지하고 독립된 가상 환경에서 실행할 수 있도록 `pipx`를 통한 설치를 권장합니다.

```bash
# 권장: pipx를 통한 독립 설치
pipx install omi-cli

# 또는 표준 pip 설치
pip install omi-cli
```

> **주의: 패키지명 vs. 명령어 이름**
> * PyPI 패키지명은 **`omi-cli`**입니다 (`omi`라는 이름은 관련 없는 다른 패키지입니다).
> * 터미널에서 실행하는 명령어는 간단히 **`omi`**입니다.

설치가 정상적으로 완료되었는지 확인합니다:

```bash
omi --version
omi --help
```

---

## 2. 인증 (Authentication)

`omi-cli`는 두 가지 인증 방식을 지원합니다:

| 인증 방식 | 권장 사용 환경 | 예시 명령어 |
| :--- | :--- | :--- |
| **개발자 API 키 (`omi_dev_*`)** | 자동화, CI/CD, 헤드리스 서버, AI 에이전트 | `omi auth login --api-key ...` 또는 `OMI_API_KEY` |
| **브라우저 OAuth (Google/Apple)** | 로컬 데스크톱 및 개발자 워크스테이션 | `omi auth login --browser` (Google) / `--provider apple` |

### 대화형 로그인
옵션 없이 명령어를 실행하면 사용할 방식을 선택할 수 있습니다:

```bash
omi auth login
# 1) Browser — 웹 브라우저를 통한 Google 로그인 (Apple 계정은 `--provider apple` 사용)
# 2) API key — app.omi.me에서 생성한 개발자 API 키 입력
```

### 브라우저 직접 로그인
```bash
# 기본 Google 로그인
omi auth login --browser

# Apple 계정 로그인
omi auth login --browser --provider apple
```

### 개발자 API 키 사용
[app.omi.me](https://app.omi.me)의 **Developer → API Keys** 메뉴에서 키를 발급받습니다:

```bash
# 로컬 프로필에 영구 저장 (대화형 프롬프트로 붙여넣어 셸 히스토리 보호)
omi auth login --api-key

# 또는 환경 변수로 설정 (컨테이너 및 CI/CD 파이프라인에 최적)
# 참고: 활성 로컬 프로필에 이미 저장된 키가 있는 경우 `omi auth logout`을 먼저 실행하세요.
export OMI_API_KEY="omi_dev_your_actual_key_here"
```

### 인증 상태 확인
* `omi auth status`: 활성 로컬 프로필과 마스킹된 인증 정보를 표시합니다. 만료일은 OAuth 프로필에 대해서만 표시됩니다 (오프라인 작동).
* `omi auth whoami`: Omi 서버에 검증 요청을 보내 실시간 자격 증명의 유효성을 확인합니다 (네트워크 필요).

```bash
omi auth status
omi auth whoami
```

세션 종료:
```bash
omi auth logout
# OMI_API_KEY가 환경 변수로 설정되어 있다면 세션에서도 해제합니다 (Bash/Zsh: `unset OMI_API_KEY`).
```

---

## 3. 핵심 명령어

### 메모리 (Memories)
Omi가 기록한 원자 단위의 맥락 정보:

```bash
# 저장된 메모리 목록 조회
omi memory list

# 새 메모리 생성
omi memory create "파이썬 예제를 포함한 기술적이고 간결한 답변을 선호함" --category work

# 특정 메모리 상세 조회
omi memory get <MEMORY_ID>
```

### 대화 (Conversations)
Omi 디바이스를 통해 녹음된 대화 및 오디오 트랜스크립트:

```bash
# 최근 5개의 대화 목록 조회
omi conversation list --limit 5

# 대화 상세 정보 및 전체 텍스트 트랜스크립트 가져오기
omi conversation get <CONVERSATION_ID> --include-transcript
```

### 할 일 및 작업 항목 (Action Items)
대화에서 자동으로 추출된 실행 항목:

```bash
# 진행 중인 할 일 목록 조회
omi action-item list --open

# 작업 완료 처리
omi action-item complete <ACTION_ITEM_ID>
```

### 목표 (Goals)
진행률 지표 및 목표 추적:

```bash
# 활성 목표 목록 조회
omi goal list

# 새 정량적 목표 생성
omi goal create "매일 물 2리터 마시기" --type numeric --target 2 --unit liters
```

---

## 4. 구조화된 자동화 및 JSON 출력 (`--json`)

`omi-cli`는 자동화 파이프라인을 위해 최우선으로 설계되었습니다. 전역 플래그 `--json`을 지정하면 유효한 JSON 형식으로 결과가 출력됩니다:

```bash
# 메모리를 JSON으로 출력하고 jq로 필드 추출
omi --json memory list | jq '.[] | {id, content, category}'

# 최근 대화 제목 추출
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# 열려 있는 작업 항목 원시 데이터 확인
omi --json action-item list --open | jq '.'
```

> **중요 구문 규칙:**
> `--json`은 **전역 옵션**이므로 항상 하위 명령어 **앞에** 위치해야 합니다:
> * 올바른 예: `omi --json memory list`
> * 잘못된 예: `omi memory list --json`

---

## 5. 종료 코드 (Exit Codes)

셸 스크립트와 CI/CD 파이프라인의 안정적인 오류 처리를 위한 표준 종료 코드:

| 종료 코드 | 의미 | 설명 |
| :---: | :--- | :--- |
| `0` | **성공 (Success)** | 명령어가 정상적으로 실행됨. |
| `1` | **사용법 오류 (유효성 검사 오류)** | 잘못된 데이터 값 또는 애플리케이션 검증 실패; Click 파서 구문 오류(누락된 필수 플래그 등)는 코드 `2`를 반환합니다. |
| `2` | **인증 오류 / CLI 구문 오류** | 미인증 상태, 만료된 토큰 또는 잘못된 Click CLI 파서 구문 오류. |
| `3` | **서버/네트워크 오류 (Server Error)** | HTTP 5xx 응답, 연결 타임아웃 또는 서버 도달 불가. |
| `4` | **요청 빈도 제한 (Rate Limited)** | HTTP 429 Too Many Requests — 지연 후 재시도 필요. |
| `5` | **찾을 수 없음 (Not Found)** | HTTP 404 Not Found — 요청한 리소스가 존재하지 않음. |

---

## 6. 환경별 셸 스크립트 예제

### Bash / Zsh (Linux / macOS)
```bash
# 세션에 API 키 설정
export OMI_API_KEY="omi_dev_your_actual_key_here"

# 실행 후 종료 코드 검증
omi --json memory list --limit 10
if [ $? -ne 0 ]; then
    echo "사용자 메모리 조회 중 오류가 발생했습니다." >&2
fi
```

### PowerShell (Windows)
```powershell
# PowerShell 환경 변수 설정
$env:OMI_API_KEY = "omi_dev_your_actual_key_here"

# JSON 출력을 PowerShell 객체로 직접 변환
$memories = omi --json memory list | ConvertFrom-Json
$memories | Select-Object id, content, category

# $LASTEXITCODE를 통한 오류 검사
if ($LASTEXITCODE -ne 0) {
    Write-Error "Omi 명령어가 오류 코드 $LASTEXITCODE(으)로 실패했습니다."
}
```

---

## 7. 로컬 데스크톱 API 연동

Omi Desktop 애플리케이션이 머신에서 실행 중인 경우 클라우드 요청 없이 로컬 캡처 및 화면 기록을 조회할 수 있습니다:

```bash
# 로컬 엔드포인트 구성 (보안을 위해 환경 변수 사용 권장)
export OMI_LOCAL_API_URL="http://127.0.0.1:47778"
read -r -s -p "Desktop token: " OMI_LOCAL_TOKEN; echo
export OMI_LOCAL_TOKEN

# 로컬 연결 상태 확인
omi --json local status

# 최근 시각 타임라인 검색
omi --json local search-screen "분기 보고서" --days 7 --app Safari
```

---

## 8. 다중 프로필 관리 (Profiles)

개인 계정과 업무용 계정 또는 테스트 환경을 전환할 때 `--profile` 옵션을 사용합니다. 설정은 `~/.omi/config.toml`에 안전하게 저장됩니다:

```bash
# 개인 프로필 생성 및 로그인
omi --profile personal auth login

# 업무용 프로필 생성 및 로그인
omi --profile work auth login

# 특정 프로필로 명령어 실행
omi --profile work memory list
```

---

## 9. 보안 모범 사례

* **Git 저장소에 키 커밋 금지:** API 키는 버전 관리 시스템에 절대 커밋하지 마시고, 비밀 관리자나 `.gitignore` 처리된 `.env` 파일을 활용하세요.
* **셸 히스토리 보호:** 공유 환경에서는 커맨드라인 플래그로 직접 키를 전달하지 말고 대화형 입력이나 `OMI_API_KEY` 환경 변수를 사용하세요.
* **디렉터리 권한:** Unix 환경에서는 설정 디렉터리 `~/.omi/`의 권한을 엄격하게 제한하세요 (`chmod 700 ~/.omi`).
