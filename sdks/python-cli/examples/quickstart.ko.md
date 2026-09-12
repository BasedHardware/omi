# omi-cli 빠른 시작 가이드 (한국어)

> 터미널에서 Omi와 상호 작용하는 실용적인 가이드입니다. 사람과 AI 에이전트 모두에게 적합합니다.

`omi-cli`는 [Omi](https://omi.me)의 개발자 API와 상호 작용하기 위한 공식 커맨드라인 인터페이스입니다. Omi의 네 가지 핵심 리소스 — **메모리, 대화, 액션 아이템, 목표** — 를 효율적이고 스크립트 가능한 방식으로 처리합니다.

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **공식 문서:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **소스 코드:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. 설치

권장되는 설치 방법은 의존성 격리를 위해 `pipx`를 사용하는 것입니다.

```bash
# 권장: pipx로 설치
pipx install omi-cli

# 또는 pip 사용
pip install omi-cli
```

> **중요: 패키지 이름과 명령어 이름의 차이**
> - 설치되는 Python 패키지 이름은 **`omi-cli`** 입니다 (단독 `omi` 패키지는 관련 없는 다른 패키지입니다).
> - 설치 후 터미널에서 실행되는 명령어 이름은 **`omi`** 입니다.

설치 후 버전과 도움말을 확인하세요.

```bash
omi --version
omi --help
```

---

## 2. 인증 (Authentication)

`omi-cli`는 두 가지 인증 방식을 지원합니다.

| 방식 | 권장 용도 | 명령어 예시 |
| :--- | :--- | :--- |
| **개발자 API 키 (`omi_dev_*`)** | CI/CD, 자동 스크립트, AI 에이전트 | `omi auth login --api-key ...` 또는 환경 변수 |
| **브라우저 OAuth (Google/Apple)** | 개발자 PC / 노트북 | `omi auth login --browser` |

### 대화형 로그인
옵션 없이 실행하면 브라우저 로그인과 API 키 입력 중 선택하라는 메시지가 표시됩니다.

```bash
omi auth login
# 1) Browser — Google 또는 Apple 계정으로 로그인 (사람용)
# 2) API key — app.omi.me에서 받은 개발자 키를 붙여넣기 (에이전트/CI용)
```

### 브라우저로 직접 로그인
```bash
omi auth login --browser
```

### API 키 사용
[app.omi.me](https://app.omi.me)의 **Developer → API Keys**에서 개발자 키를 받은 다음 설정하세요.

```bash
# 명령어로 설정
omi auth login --api-key omi_dev_...

# 또는 환경 변수로 설정 (CI/CD 또는 컨테이너에 이상적)
export OMI_API_KEY=omi_dev_...
```

### 인증 상태 확인
* `omi auth status`: 로컬 인증 프로필, 마스킹된 토큰, 만료일 표시 (오프라인 작동).
* `omi auth whoami`: Omi 서버에 실제 인증 요청을 보냄 (네트워크 연결 필요).

```bash
omi auth status
omi auth whoami
```

로그아웃:
```bash
omi auth logout
```

---

## 3. 기본 사용법

Omi의 네 가지 핵심 리소스를 나열하고 관리할 수 있습니다.

### 메모리 (Memories)
시스템이 학습한 사실과 지식을 관리합니다.

```bash
# 모든 메모리 나열
omi memory list

# 새 메모리 생성
omi memory create "사용자가 다크 모드를 선호함" --category lifestyle

# 특정 메모리의 세부 정보 표시
omi memory get <MEMORY_ID>
```

### 대화 (Conversations)
웨어러블 기기 또는 앱에서 캡처된 오디오 또는 텍스트 대화 기록.

```bash
# 최근 5개의 대화 가져오기
omi conversation list --limit 5

# 대화 세부 정보 및 전사 표시
omi conversation get <CONVERSATION_ID> --include-transcript
```

### 액션 아이템 (Action Items)
대화에서 자동으로 추출된 작업 또는 팔로업 항목.

```bash
# 미해결 액션 아이템만 나열
omi action-item list --open

# 액션 아이템을 완료로 표시
omi action-item complete <ACTION_ITEM_ID>
```

### 목표 (Goals)
진행률이 추적되는 목표를 관리합니다.

```bash
# 모든 목표 나열
omi goal list
```

---

## 4. 스크립트 처리 및 JSON 출력 (`--json`)

`omi-cli`는 JSON 출력을 기본적으로 지원합니다. `jq` 또는 Python 스크립트와 함께 사용할 때 **전역 옵션** `--json`은 하위 명령어 앞에 위치해야 합니다.

```bash
# JSON으로 메모리 목록을 가져와 ID와 내용 추출
omi --json memory list | jq '.[] | {id, content, category}'

# 최근 5개 대화의 제목 가져오기
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# 미해결 액션 아이템 나열
omi --json action-item list --open | jq '.[] | {id, title, due_at}'

# 목표 나열
omi --json goal list | jq '.[] | {id, title, progress: .progress_percent}'
```

---

## 5. 세션 진단

이 두 명령어를 함께 사용하여 빠르게 문제를 해결하세요.

```bash
# 1) 먼저 로컬 설정 확인
omi auth status

# 2) Omi 서버로 확인
omi auth whoami

# 3) 필요한 경우 로그인 다시 시작
omi auth login
```

---

## 6. 모범 사례

* **스크립트에서 `--json` 사용:** 자유 텍스트 파싱을 피하고 항상 구조화된 JSON 출력에 의존하세요.
* **`pipx`로 환경 격리:** 다른 Python 패키지와의 의존성 충돌을 방지합니다.
* **API 키 공유 금지:** `omi_dev_*` 키는 전체 계정 접근 권한을 부여합니다 — 비밀 관리자 또는 환경 변수에 보관하세요.
* **공유 기기에서 로그아웃:** 공유 머신에서 세션 후 `omi auth logout`을 사용하세요.

---

## 7. 문제 해결

| 증상 | 가능한 원인 | 해결 방법 |
| :--- | :--- | :--- |
| `command not found: omi` | PATH에 pipx bin 디렉터리가 없음 | `pipx ensurepath` 실행 후 터미널 재시작 |
| `401 Unauthorized` | API 키가 잘못되었거나 만료됨 | app.omi.me에서 새 키 생성 및 업데이트 |
| `connection refused` | Omi 서버에 대한 네트워크 접근 없음 | 인터넷 연결 및 프록시 설정 확인 |
| 설정 파일에 대한 `permission denied` | 설정 디렉터리에 쓸 수 없음 | `~/.config/omi` 권한 확인 |

---

## 8. 빠른 링크

* 소스 저장소: [github.com/BasedHardware/omi](https://github.com/BasedHardware/omi)
* 전체 문서: [docs.omi.me](https://docs.omi.me)
* 이슈 및 지원: [github.com/BasedHardware/omi/issues](https://github.com/BasedHardware/omi/issues)
* Discord 커뮤니티: Omi 홈페이지를 통한 초대