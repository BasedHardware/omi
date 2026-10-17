# omi-cli 빠른 시작

이 가이드는 기본 명령어를 한국어로 설명합니다. 명령어 이름과 프로그램 메시지는
영어로 유지됩니다. 아래 예시 명령어는 메모리, 대화, 작업 항목, 목표를 변경하지
않습니다.

## 프로그램 설치

요구 사항: Python 3.10 이상과 Omi 계정.

`pipx`가 설치되어 있다면:

```sh
pipx install omi-cli
omi --help
```

또는 활성화된 Python 가상 환경에 설치할 수 있습니다:

```sh
python -m pip install omi-cli
omi --help
```

터미널에서 `omi`를 찾지 못하면 가상 환경이 활성화되어 있는지 확인하거나,
`pipx`가 실행 파일을 설치한 디렉터리가 `PATH`에 있는지 확인하세요.

## 계정 연결

대화형 안내를 실행합니다:

```sh
omi auth login
```

브라우저 로그인을 선택하거나 Omi 개발자 API 키를 붙여넣습니다. 대화형 입력은
키를 화면에 표시하지 않습니다. 터미널 기록에 남는 명령어에는 키를 직접
입력하지 마세요.

브라우저를 바로 사용하려면:

```sh
omi auth login --browser
```

인증 결과는 로컬 콜백 주소를 사용하므로 터미널과 같은 컴퓨터에서 로그인하세요.
화면의 안내를 따르세요.

로그인 후 설정과 API 접근을 확인합니다:

```sh
omi auth status
omi auth whoami
```

`status`는 로컬 상태를 보여주고 비밀 값을 가려 주지만, 서버에서의 유효성은
확인하지 않습니다. `whoami`는 인증된 요청을 보냅니다. 성공하면 이름을
표시하지 않아도 자격 증명이 정상 동작하는 것입니다.

설정은 기본적으로 `~/.omi/config.toml`에 저장됩니다. 이 파일에는 자격 증명이
포함될 수 있으므로 공유하지 마세요.

## 데이터 읽기

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

빈 목록은 필터에 맞는 항목이 없다는 뜻일 수 있습니다. 각 명령어의 옵션은
도움말에서 확인하세요:

```sh
omi memory list --help
omi action-item list --help
```

## JSON 출력과 페이지 탐색

전역 `--json` 옵션은 명령어 그룹 **앞**에 둡니다:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

첫 번째 명령은 처음 25개 메모리를, 두 번째는 다음 25개를 요청합니다. 한
페이지는 전체 백업이 아닙니다. JSON 출력은 전체 ID를 유지하고, 표 형식은
표시용으로 ID를 줄일 수 있습니다.

한 페이지를 파일로 저장하려면:

```sh
omi --json memory list --limit 25 --offset 0 > memory-page-1.json
```

리다이렉션은 로컬 파일을 만들거나 덮어씁니다. 내용을 사용하기 전에 명령이
성공적으로 끝났는지 확인하세요. 오류는 표준 오류로 출력되며, 빈 파일이
데이터가 없음을 증명하지는 않습니다. 내보낸 파일에는 개인 정보가 포함될 수
있으니 비공개로 보관하세요.

## 프로필 사용

상태는 `~/.omi/config.toml`에 저장됩니다(`$OMI_CONFIG`로 변경 가능). 각
프로필은 자체 인증 방법과 API 주소를 가집니다. `--profile`로 전환합니다:

```sh
omi config profile use work
omi auth login
omi --profile personal memory list
```

자주 쓰는 설정 명령:

```sh
omi config show
omi config path
omi config profile list
```

## 종료 코드

이 종료 코드는 안정적이며 스크립트나 에이전트에서 활용할 수 있습니다:

| 코드 | 의미 | 예시 상황 |
| ---: | --- | --- |
| 0 | 성공 | 명령이 완료됨 |
| 1 | 사용법 오류 | 잘못된 플래그, 누락된 인자, 검증 실패 |
| 2 | 인증 오류 | 자격 증명 없음, 토큰 만료, 권한 부족 |
| 3 | 서버 오류 | 서버 5xx 또는 연결 실패 |
| 4 | 속도 제한 | 서버가 HTTP 429 반환 |
| 5 | 찾을 수 없음 | 서버가 HTTP 404 반환 |

## 로그아웃

```sh
omi auth logout
```

로컬에 저장된 자격 증명을 제거합니다. 서버에서 키를 폐기하려면 계정의 개발자
키 관리를 사용하세요.

추가 명령어와 옵션은 [영문 메인 README](../README.md)와 `omi --help`를
참고하세요.
