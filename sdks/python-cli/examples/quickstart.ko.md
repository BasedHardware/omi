# omi-cli — 한국어 퀵스타트 가이드

> 터미널에서 Omi 를 다루는 실용 가이드. 사람과 AI 에이전트 모두가 사용할 수 있습니다.

`omi-cli` 는 [Omi](https://omi.me) 개발자 API 의 공식 커맨드라인 클라이언트입니다.
Omi 의 네 가지 핵심 리소스 — 메모리, 대화, 액션 아이템, 목표 — 에 빠르고 스크립트 가능한 방식으로 접근할 수 있습니다.

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **공식 문서:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **소스 코드:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. 설치

`pipx` 설치를 권장합니다. 도구가 독립된 환경에 설치되어
의존성이 현재 프로젝트와 충돌하지 않습니다.

```bash
# 권장: pipx 로 설치
pipx install omi-cli

# 또는 pip 으로
pip install omi-cli
```

> **중요: 패키지 이름과 명령어 이름이 다릅니다.**
> * 설치하는 패키지는 **`omi-cli`** 입니다 (`omi` 라는 별도 패키지는 관련 없는 다른 프로젝트입니다).
> * 설치 후 실행하는 명령어는 **`omi`** 입니다.

정상 동작을 확인합니다:

```bash
omi --version
omi --help
```

---

## 2. 인증

`omi-cli` 는 두 가지 로그인 방법을 지원합니다.

| 방법 | 적합한 용도 | 명령어 |
| :--- | :--- | :--- |
| **개발자 키 (`omi_dev_*`)** | CI/CD, 스크립트, AI 에이전트 | `omi auth login --api-key ...` 또는 환경 변수 |
| **브라우저 로그인 (Google/Apple)** | 본인 PC 작업 | `omi auth login --browser` |

### 대화형 로그인

옵션 없이 실행하면 어떤 방법을 쓸지 물어봅니다.

```bash
omi auth login
# 1) Browser — Google 또는 Apple로 로그인 (사람용)
# 2) API key — app.omi.me에서 발급받은 개발자 키 붙여넣기 (에이전트·CI용)
```

키를 선택하면 입력이 가려져 터미널 기록에 키가 남지 않습니다.

### 브라우저로 바로 로그인

```bash
omi auth login --browser
```

### 개발자 키로 로그인

키는 [app.omi.me](https://app.omi.me) 의 **Developer → API Keys** 에서 발급받습니다.

```bash
# 키를 설정에 저장
omi auth login --api-key omi_dev_...

# 또는 환경 변수로 전달 — CI/CD와 컨테이너에 적합
export OMI_API_KEY=omi_dev_...
```

`OMI_API_KEY` 환경 변수는 활성 프로필에 저장된 키가 없을 때 사용되므로,
컨테이너에서는 디스크에 아무것도 쓸 필요가 없습니다. 프로필에 이미 키가
저장되어 있다면 그 키가 환경 변수보다 우선합니다.

### 접근 확인

두 명령어는 서로 다른 질문에 답하므로 혼동하지 마세요:

* `omi auth status` — **로컬에** 저장된 것: 프로필, 가려진 키, 만료일. 네트워크 불필요.
* `omi auth whoami` — **Omi 서버에** 요청: 키가 실제로 받아들여지는지 확인. 네트워크 필요.

```bash
omi auth status    # 로컬 확인, 오프라인 가능
omi auth whoami    # 서버 확인
```

만료 임박 토큰을 재로그인 없이 갱신 — 이 명령어는 **브라우저/OAuth 세션에만** 해당합니다.
API 키(`omi_dev_*`)로 인증된 프로필에서는 `omi auth refresh`가 사용법 오류(코드 1)로
실패합니다 — 갱신할 토큰이 없기 때문입니다. 필요하면 Omi 웹앱에서 키를 교체하세요:

```bash
omi auth refresh
```

로그아웃:

```bash
omi auth logout
```

---

## 3. 기본 명령어

### 메모리 (memories)

시스템이 당신에 대해 기억한 사실과 지식입니다.

```bash
# 메모리 목록
omi memory list

# 새로 만들기
omi memory create "사용자는 다크 모드를 선호함" --category lifestyle

# 하나 자세히 보기
omi memory get <MEMORY_ID>
```

### 대화 (conversations)

디바이스나 앱에서 온 음성·텍스트 기록입니다.

```bash
# 최근 대화 5개
omi conversation list --limit 5

# 전사 포함 전체 대화
omi conversation get <CONVERSATION_ID> --include-transcript
```

### 액션 아이템 (action items)

Omi 가 대화에서 추론한 할 일입니다.

```bash
# 미완료만 보기
omi action-item list --open

# 완료로 표시
omi action-item complete <ACTION_ITEM_ID>
```

### 목표 (goals)

```bash
# 목표 목록
omi goal list

# 진행 값 기록 (목표와 값 두 인수 모두 필요)
omi goal progress <GOAL_ID> 25

# 변경 이력
omi goal history <GOAL_ID>
```

---

## 자연어로 질문하기 (`ask`)

별도의 최상위 명령어입니다. 자연어 질문을 받아 당신의 대화에서 답을 찾아 만듭니다.

```bash
omi ask "이사에 대해 무엇을 결정했지?"
omi --json ask "이번 주에 끝내기로 한 액션 아이템이 뭐지?"
```

---

## 4. JSON 과 스크립트 (`--json`)

`omi-cli` 는 기계가 읽을 수 있는 JSON 을 출력할 수 있습니다. `--json` 옵션은
**전역** 이므로 서브커맨드 **앞에** 위치해야 합니다.

```bash
# 메모리: id, 내용, 카테고리 추출
omi --json memory list | jq '.[] | {id, content, category}'

# 최근 대화 제목
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# 미완료 액션 아이템
omi --json action-item list --open | jq '.'
```

> **흔한 실수.** `--json` 은 서브커맨드 앞에 옵니다, 뒤가 아니라.
> * 올바름: `omi --json memory list`
> * 틀림: `omi memory list --json`

`--json` 모드에서는 사람용 진행 메시지와 스피너가 사라지고,
stdout 에는 유효한 JSON 문서 하나만 출력됩니다. 오류는
`{"error": "...", "detail": "..."}` 형태로 stderr 에 갑니다.

---

## 5. 종료 코드

스크립트에서 분기할 수 있는 안정된 종료 코드입니다.

| 코드 | 의미 |
| :--- | :--- |
| `0` | 성공 |
| `1` | 사용법 오류 (잘못된 플래그, 필수 인수 누락) |
| `2` | 인증 실패 — 로그인 필요 |
| `3` | 서버/네트워크 오류 |
| `4` | 속도 제한 — 잠시 후 재시도 |
| `5` | 리소스를 찾을 수 없음 |

```bash
if ! omi memory get "$MEMO_ID" --json > /tmp/m.json; then
  code=$?
  case $code in
    2) omi auth login --browser ;;
    5) echo "해당 메모리 없음" ;;
    *) echo "오류 $code" ;;
  esac
fi
```

---

## 6. 프로필과 설정

여러 계정이나 환경이 있으면 프로필로 분리하세요.
설정은 `~/.omi/config.toml` 에 저장됩니다.

```bash
# 개인 프로필로 로그인
omi --profile personal auth login

# 회사 프로필로 로그인
omi --profile work auth login

# 특정 프로필로 명령 실행
omi --profile work memory list
```

사용되는 프로필은 다음 순서로 결정됩니다: `--profile` 옵션(또는 `-p`)이
최우선, 다음으로 `OMI_PROFILE` 환경 변수, 다음으로 `~/.omi/config.toml` 의
활성 프로필, 마지막으로 `default` 프로필이 폴백입니다.

설정 자체를 보고 바꾸기:

```bash
# 현재 설정 보기
omi config show

# 설정 파일 위치
omi config path

# 값 변경
omi config set api_base https://api.omi.me
```

---

## 7. 다음 단계

* [`agent_quickstart.md`](./agent_quickstart.md) — `omi-cli` 를 AI 에이전트에 연결하는 방법.
* [`shell_examples.sh`](./shell_examples.sh) — 바로 쓸 수 있는 셸 예제.
* [Omi 문서](https://docs.omi.me/doc/developer/cli/introduction) — 전체 명령어 레퍼런스.
