---
description: arc 파이프라인 운영 (Evidence → Work → Projection → Output)
---

arc MCP가 연결되면 이 워크플로우가 자동으로 활성화됩니다.
파이프라인 현황은 `get_pipeline_state` 도구로 언제든 확인할 수 있습니다.

---

## 자동 컨텍스트 규칙 (모든 MCP 클라이언트 공통)

다음 상황에서는 **사용자 요청 처리 전** 아래 Arc 도구를 자동 호출한다:

1. **업무 현황·진행 상태·파이프라인 관련 질문** (예: "뭐 하고 있어?", "이번 주 뭐 했어?", "상태 어때?")
   → `get_pipeline_state` 호출

2. **특정 도메인 기술 질문** (예: 배포, 인증, DB, 프론트 등)
   → `read_project_docs(mode="search", query=<사용자 질문>)` 호출 후 관련 섹션 확인

3. **work item 생성·수정·보고서 작성 요청**
   → `get_pipeline_state` + `list_work_items` 호출

4. **문서 업데이트 요청**
   → `read_project_docs(mode="toc")` 호출 후 해당 섹션 확인 → `update_project_docs(mode="section")`

5. **Notion URL 제공 + "연결", "등록", "참조", ".env 동기화" 등 요청**
   → notion MCP의 `notion-fetch(id=<URL>)`로 DB 제목 확인
   → `register_notion_db(url=<URL>, label=<제목>, description=<용도>)` 호출
   → 이후 `get_pipeline_state` 응답에 MAM 규칙으로 자동 포함됨

**원칙**: 섹션 ID나 문서 제목을 사용자에게 묻지 않는다. `mode="search"`로 의미 검색하거나 `toc`로 목록 확인 후 자동 선택한다.

---

## MAM 규칙 (MCP → Agent → MCP)

`get_pipeline_state` 응답에 `## MAM 규칙` 섹션이 있으면:
- notion MCP가 현재 세션에 로드되어 있는지 확인한다.
- 로드되어 있으면, 프로젝트 컨텍스트·환경변수·접속정보 조회 시 해당 Notion DB를 우선 참조한다.
- `.env` 동기화 요청 시: notion DB의 Key/Value 행을 조회 → `.env` 파일에 기록한다.

---

## 초기 스캔 (처음 Arc를 연결했을 때)

이 프로젝트를 Arc가 아직 분석하지 않은 경우 가장 먼저 실행하세요.

```
scan_workspace()                     — 프로젝트 파일을 읽어 구조 파악
                                       → AI가 자동으로 update_workspace_context 호출
```

스캔이 완료되면 이해관계자가 arc doc web에서 프로젝트 개요와 파이프라인 현황을 확인할 수 있습니다.

---

## 새 작업 시작 시

기능/버그픽스/인프라 작업을 시작할 때 work item을 등록합니다.

`create_work_item` 도구 호출:
```
title:     "<무슨 일인지 — 비즈니스 언어로>"
scope:     "<영향 도메인>"
milestone: "<목표 릴리즈 또는 스프린트>"
owner:     "<담당자>"
status:    in_progress
```

작업이 완료되면:
```
update_work_item(id: <ID>, status: done)
```

---

## PR 머지 후

```
1. ingest_evidence
   event_type: pr_merged
   title:  "<PR 제목>"
   ref:    "PR #<번호>"
   source: github
   author: "<작성자>"
   work_item_id: <연관 ID, 있으면 지정>

2. (work_item_id 모를 경우)
   list_work_items → link_evidence_to_work_item

3. (권장) project_work_item
   — PR의 기술 변화를 사용자/운영 관점 언어로 번역
   output_type: weekly_summary 또는 release_brief
```

---

## 배포 후

```
ingest_evidence
  event_type: deploy_succeeded
  title:  "<버전 또는 배포 설명>"
  ref:    "<deploy ID 또는 commit hash>"
  source: ci
  author: "<담당자>"
```

---

## 리스크 발생 시

```
ingest_evidence
  event_type: risk_raised
  title:  "<리스크 한 줄 설명>"
  ref:    "<alert ID 또는 incident ID>"
  source: ops
  author: "<담당자>"
  work_item_id: <연관 work item ID>

→ generate_risk_brief(work_item_id: <ID>)
```

---

## 주간 보고 생성

```
generate_weekly_summary(week_label: "YYYY-WNN")
```

projection이 없는 work item은 `project_work_item` 으로 번역 후 재생성합니다.

---

## 대표 요약 생성

```
generate_executive_update()
```

---

## 릴리즈 브리프 생성

```
generate_release_brief(version: "vX.Y.Z")
```

---

## 파이프라인 상태 점검

```
get_pipeline_state()           — 전체 현황 (Evidence / Work / Projection / Output Ready)
list_work_items()              — work item 목록 (status 필터 선택)
list_unlinked_evidences()      — 미연결 증거 목록 → link_evidence_to_work_item 으로 해소
```
