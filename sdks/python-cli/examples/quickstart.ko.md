# omi-cli 시작하기

이 가이드는 한국어로 기본 CLI 명령어 사용법을 설명합니다. 명령어 이름과 프로그램 메시지는 영어로 유지됩니다. 여기에 소개된 조회 예제는 기억(memory), 대화(conversation), 작업 항목(action-item), 목표(goal)를 수정하거나 삭제하지 않습니다.

## 프로그램 설치

요구 사항: Python 3.10 이상 및 Omi 계정.

`pipx`가 설치되어 있는 경우:

```sh
pipx install omi-cli
omi --help
```

또는 활성화된 Python 가상 환경 내에서 설치할 수 있습니다:

```sh
python -m pip install omi-cli
omi --help
```

터미널에서 `omi` 명령어를 찾을 수 없는 경우, 가상 환경이 활성화되어 있는지 확인하거나 `pipx` 바이너리 설치 경로가 `PATH` 환경 변수에 포함되어 있는지 확인하세요.

## 계정 연결

대화형 로그인 마법사를 실행합니다:

```sh
omi auth login
```

웹 브라우저를 통한 로그인 또는 Omi 개발자 API 키를 직접 입력하는 옵션을 선택할 수 있습니다. 대화형 입력은 보안을 위해 API 키를 화면에 표시하지 않습니다. 터미널 기록에 키가 남지 않도록 명령줄 인수로 직접 입력하지 마세요.

브라우저로 바로 로그인하려면:

```sh
omi auth login --browser
```

터미널과 동일한 컴퓨터의 브라우저에서 로그인하세요. 인증 응답은 로컬 루프백 주소를 사용합니다. 화면의 지침을 따르세요.

로그인 후 설정 및 API 연결 상태를 확인합니다:

```sh
omi auth status
omi auth whoami
```

`status`는 로컬 설정 파일 상태를 표시합니다. `whoami`는 서버에 인증된 요청을 전송하여 자격 증명이 유효한지 확인합니다.

기본적으로 설정은 `~/.omi/config.toml`에 저장됩니다. 자격 증명이 포함되어 있으므로 이 파일을 공유하지 마세요.

## 데이터 조회

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

결과 목록이 비어 있는 경우 조건에 일치하는 데이터가 없는 상태일 수 있습니다. 각 하위 명령어의 도움말을 통해 필터 옵션을 확인할 수 있습니다:

```sh
omi memory list --help
omi action-item list --help
```

## JSON 출력 및 페이지네이션

전역 `--json` 플래그는 반드시 명령어 그룹 **앞**에 배치해야 합니다:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

첫 번째 명령은 처음 25개의 기억을 가져오고, 두 번째 명령은 다음 25개를 가져옵니다. 단일 페이지 요청은 전체 계정 백업이 아닙니다. JSON 출력은 전체 고유 식별자(UUID)를 보존합니다.

결과를 JSON 파일로 저장하려면:

```sh
omi --json memory list --limit 25 --offset 0 > memories-page-1.json
```

파일 내용을 사용하기 전에 명령이 오류 없이 완료되었는지 확인하세요. 내보낸 파일에는 개인 정보가 포함될 수 있으므로 안전하게 보관하세요.

## 로그아웃

```sh
omi auth logout
```

이 명령어는 로컬에 저장된 자격 증명을 삭제합니다. 서버에서 API 키를 완전히 취소하려면 웹 대시보드의 개발자 키 관리 기능을 사용하세요.

자세한 옵션과 고급 기능은 [기본 영문 문서](../README.md) 및 `omi --help`를 참조하세요.
