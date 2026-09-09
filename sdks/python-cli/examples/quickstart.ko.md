# omi-cli 한국어 퀵스타트 가이드 (Quickstart Guide)

> 터미널에서 Omi와 직접 상호작용하기 위한 실전 가이드 — 개발자 및 자율형 AI 에이전트를 위해 설계되었습니다.

`omi-cli`는 [Omi](https://omi.me) 개발자 API를 제어하기 위한 공식 명령줄 인터페이스(CLI)입니다. Omi가 관리하는 4대 핵심 리소스인 기억(Memories), 대화(Conversations), 액션 아이템(Action Items), 목표(Goals)를 스크립트와 파이프라인으로 쉽게 자동화할 수 있습니다.

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **공식 문서:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **소스 코드:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. 설치 (Installation)

권장되는 설치 방식은 격리된 환경에서 독립적으로 실행하는 `pipx`를 사용하는 것입니다:

```bash
# 권장: pipx를 통한 격리 설치
pipx install omi-cli

# 또는 pip를 통한 일반 설치
pip install omi-cli
```

> **중요: 패키지명과 명령어명의 차이**
> * PyPI에 등록된 패키지 이름은 **`omi-cli`**입니다 (`omi` 패키지는 다른 무관한 패키지입니다).
> * 설치 후 터미널에서 실행하는 명령어는 **`omi`**입니다.

설치 후 버전 및 도움말을 확인합니다:

```bash
omi --version
omi --help
```

---

## 2. 인증 (Authentication)

`omi-cli`는 두 가지 인증 방식을 지원합니다:

| 인증 방식 | 주요 용도 | 명령어 예시 |
| :--- | :--- | :--- |
| **개발자 API 키 (`omi_dev_*`)** | CI/CD, 자동화 스크립트, AI 에이전트 | `omi auth login --api-key ...` 또는 `OMI_API_KEY` |
| **브라우저 OAuth (Google/Apple)** | 개발자 로컬 노트북 / PC | `omi auth login --browser` |

### 대화형 로그인
옵션 없이 실행하면 방식을 선택하는 프롬프트가 표시됩니다:

```bash
omi auth login
# 1) Browser — 웹 브라우저에서 Google 또는 Apple 계정으로 로그인
# 2) API key — app.omi.me에서 발급받은 개발자 API 키 붙여넣기
```

### 브라우저 직접 로그인
```bash
omi auth login --browser
```

### 개발자 API 키 사용
[app.omi.me](https://app.omi.me)의 **Developer → API Keys**에서 키를 발급받아 설정합니다:

```bash
# CLI를 통해 로컬 설정에 저장
omi auth login --api-key omi_dev_...

# 또는 환경 변수로 설정 (컨테이너 및 CI/CD에 최적)
export OMI_API_KEY="omi_dev_..."
```

### 인증 상태 확인
* `omi auth status`: 로컬에 저장된 프로필, 마스킹된 토큰 및 만료 시간을 확인합니다 (오프라인 작동).
* `omi auth whoami`: Omi 서버에 실제 검증 요청을 보내 키의 유효성을 확인합니다 (네트워크 연결 필요).

```bash
omi auth status
omi auth whoami
```

로그아웃 시:
```bash
omi auth logout
```

---

## 3. 핵심 리소스 명령어

### 기억 (Memories)
시스템이 사용자에 대해 학습한 사실, 지식, 컨텍스트 관리:

```bash
# 저장된 기억 목록 조회
omi memory list

# 새로운 기억 생성
omi memory create "백엔드 구현시 Python과 TypeScript를 선호함" --category work

# 특정 기억 상세 조회
omi memory get <MEMORY_ID>
```

### 대화 (Conversations)
Omi 디바이스 또는 앱에서 녹음되고 전사된 대화 기록:

```bash
# 최근 대화 5개 조회
omi conversation list --limit 5

# 대화의 전체 스크립트를 포함하여 상세 조회
omi conversation get <CONVERSATION_ID> --include-transcript
```

### 액션 아이템 (Action Items)
대화에서 자동 추출된 할 일 및 후속 조치 과제:

```bash
# 미완료된 액션 아이템 목록 조회
omi action-item list --open

# 액션 아이템을 완료 처리
omi action-item complete <ACTION_ITEM_ID>
```

### 목표 (Goals)
진척 도를 추적하는 정량적/정성적 목표 관리:

```bash
# 활성 목표 목록 조회
omi goal list

# 새로운 수치형 목표 생성
omi goal create "매일 2L 물 마시기" --type numeric --target 2 --unit liters
```

---

## 4. 자동화 및 JSON 출력 (`--json`)

`omi-cli`는 스크립트 자동화와 파이프라인을 위해 완벽한 JSON 출력을 지원합니다. `--json` 플래그는 **하위 명령어 앞에 위치해야 하는 글로벌 옵션**입니다:

```bash
# 기억 목록을 JSON으로 가져와 jq로 필요한 필드만 추출
omi --json memory list | jq '.[] | {id, content, category}'

# 최근 대화 제목 목록 추출
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# 열려있는 액션 아이템만 JSON으로 조회
omi --json action-item list --open | jq '.'
```

> **옵션 위치 주의사항:**
> `--json` 플래그는 반드시 하위 리소스 명령어 앞에 있어야 합니다:
> * 올바른 예: `omi --json memory list`
> * 잘못된 예: `omi memory list --json`

---

## 5. 종료 코드 (Exit Codes)

CI/CD 파이프라인과 스크립트에서 안정적인 예외 처리를 위해 정의된 표준 종료 코드:

| 종료 코드 | 의미 | 설명 |
| :---: | :--- | :--- |
| `0` | **성공 (Success)** | 명령어가 정상적으로 실행됨. |
| `1` | **사용법 오류 (Usage Error)** | 잘못된 인자, 필수 플래그 누락, 구문 오류. |
| `2` | **인증 오류 (Auth Error)** | 미로그인, 유효하지 않은 API 키 또는 만료된 토큰. |
| `3` | **서버/네트워크 오류 (Server Error)** | HTTP 5xx 응답, 타임아웃, 네트워크 연결 실패. |
| `4` | **요청 제한 (Rate Limited)** | HTTP 429 Too Many Requests — 재시도 로직 필요. |
| `5` | **리소스 없음 (Not Found)** | HTTP 404 Not Found — 요청한 ID를 찾을 수 없음. |

---

## 6. 쉘(Shell)별 실행 예시

### Bash / Zsh (Linux / macOS)
```bash
# API 키 설정
export OMI_API_KEY="omi_dev_your_actual_key_here"

# 명령어 실행 및 종료 코드 검증
omi --json memory list --limit 10
if [ $? -ne 0 ]; then
    echo "기억 목록 조회 실패" >&2
fi
```

### PowerShell (Windows)
```powershell
# PowerShell 환경 변수 설정
$env:OMI_API_KEY = "omi_dev_your_actual_key_here"

# JSON 결과를 PowerShell 객체로 변환하여 필드 선택
$memories = omi --json memory list | ConvertFrom-Json
$memories | Select-Object id, content, category

# $LASTEXITCODE를 통한 오류 처리
if ($LASTEXITCODE -ne 0) {
    Write-Error "Omi CLI 실행 실패: 코드 $LASTEXITCODE"
}
```

---

## 7. 로컬 Desktop API 연동

Omi Desktop 앱이 로컬 컴퓨터에서 실행 중일 때, 클라우드를 거치지 않고 로컬 네트워크를 통해 직접 화면 기록 및 DB를 조회할 수 있습니다:

```bash
# 로컬 API 연결 정보 구성
omi local configure --url http://127.0.0.1:47778 --token YOUR_DESKTOP_TOKEN

# 로컬 연결 상태 확인
omi --json local status

# 로컬 화면 타임라인 검색
omi --json local search-screen "프로젝트 보고서" --days 7 --app Safari
```

---

## 8. 프로필 관리 (Profiles)

개인 계정과 업무 계정, 또는 테스트 환경과 운영 환경을 전환하면서 사용할 때는 `--profile` 옵션을 사용합니다. 설정은 `~/.omi/config.toml`에 저장됩니다:

```bash
# 개인 프로필로 로그인
omi --profile personal auth login

# 업무 프로필로 로그인
omi --profile work auth login

# 특정 프로필 컨텍스트에서 명령어 실행
omi --profile work memory list
```

---

## 9. 보안 권장 사항

* **API 키 Git 커밋 금지:** 개발자 API 키를 소스 코드 리포지토리에 포함하지 마십시오. 환경 변수나 `.gitignore`에 등록된 설정 파일을 활용하십시오.
* **터미널 히스토리 보호:** 명령줄에 키를 직접 노출하는 대신 환경 변수(`OMI_API_KEY`)나 대화형 프롬프트를 사용하십시오.
* **즉각 폐기:** 키가 외부에 노출된 것으로 의심되면 [app.omi.me](https://app.omi.me)에서 즉시 키를 삭제 및 재발급하십시오.
