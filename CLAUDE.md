# LTE-R VCS — 패키지 관리 프로그램

사내 Bitbucket과 연동해 LTE-R 사이트별 패키지(소스/설정) 저장소를
clone / pull / push 하고, 메인 화면에서 사이트를 추가·수정·삭제하며
관리하는 로컬 웹앱입니다.

이 문서는 이 저장소에서 **Claude Code를 오케스트레이터로** 사용해
개발을 진행하기 위한 기준 문서입니다. 메인 세션(오케스트레이터)은
아래 서브에이전트(`.claude/agents/*.md`)에게 작업을 위임하고,
서브에이전트의 결과를 검증한 뒤 통합합니다.

## 1. 아키텍처

- **런타임**: 로컬에서 `uvicorn`으로 FastAPI 서버를 띄우고, 브라우저로
  `http://localhost:8000` 접속해 사용하는 로컬 웹앱.
- **백엔드**: Python 3.11+, FastAPI, SQLModel(SQLite), GitPython.
- **프론트엔드**: 서버 렌더링(Jinja2) + 최소한의 바닐라 JS(fetch 기반
  SPA-lite). 별도 빌드 도구 없이 `server/static`에서 직접 서빙.
- **데이터 저장**: `data/lte-r-vcs.db` (SQLite, gitignore 대상).
  사이트별 clone 작업공간은 `data/repos/<site-slug>/`.
- **Bitbucket 인증**: HTTP + App Password. 자격증명은 `git` 명령 실행
  시점에만 URL에 주입하고, **`.git/config`나 디스크에 평문으로
  영구 저장하지 않는다** (매 clone/pull/push 호출마다 인증 URL을
  즉석에서 구성해 GitPython에 전달). 이 정책은 절대 깨지 않는다.

## 2. 디렉터리 구조

```
CLAUDE.md
README.md
requirements.txt
.gitignore
.claude/agents/           # 서브에이전트 정의
server/
  main.py                 # FastAPI app, 라우터 등록, "/" 메인 화면
  config.py                # 경로/설정 상수
  db.py                    # SQLModel 엔진/세션
  models.py                # Site, BitbucketConfig 모델
  git_ops.py                # clone/pull/push 등 git 연동 로직
  routers/
    sites.py               # 사이트 CRUD + clone/pull/push API
    settings.py             # Bitbucket 인증 설정 API
  templates/               # Jinja2 템플릿 (메인 화면 등)
  static/css, static/js     # 스타일/클라이언트 스크립트
data/                      # 런타임 생성 (SQLite DB, clone 워크스페이스). gitignore.
```

## 3. 오케스트레이션 방식 (서브에이전트)

메인 세션은 기능 단위로 아래 에이전트에게 위임한다. 모든 에이전트는
"작업 시작 전 `token-guardian`에게 접근 방식을 확인" 원칙을 따른다
(사소한 1~2파일 수정까지 매번 확인할 필요는 없고, 여러 파일을 읽거나
서브에이전트를 새로 스폰해야 할지 애매할 때 확인한다).

| 에이전트 | 역할 | 주요 파일 |
|---|---|---|
| `token-guardian` | 토큰 사용을 통제하는 정책/검토 에이전트. 불필요한 전체 파일 읽기, 중복 서브에이전트 스폰, 과도한 컨텍스트 누적을 막고 더 좁은 접근 방식을 제안한다. | 없음 (읽기 전용 검토자) |
| `bitbucket-ops` | Bitbucket 연동(clone/pull/push), 자격증명 처리, git 관련 API | `server/git_ops.py`, `server/routers/sites.py`의 git 액션 부분 |
| `backend-dev` | FastAPI 라우터, 모델, DB 스키마, 사이트 CRUD 비즈니스 로직 | `server/main.py`, `server/models.py`, `server/db.py`, `server/routers/*.py` |
| `frontend-dev` | 메인 화면 UI(사이트 목록/추가/수정/삭제 폼), 정적 자산 | `server/templates/*.html`, `server/static/**` |

새 기능을 추가할 때는 이 표에 맞춰 담당 에이전트를 먼저 정하고,
여러 에이전트가 겹치는 작업(예: API 스키마 변경이 UI에도 영향)은
오케스트레이터가 순서를 정해 순차 위임한다.

### token-guardian 운용 원칙 (전체 세션 공통)

- 파일 전체를 읽기 전에 `Grep`/`Glob`으로 필요한 범위를 먼저 좁힌다.
- 큰 파일은 관련된 라인 범위만 `Read`의 offset/limit으로 읽는다.
- 이미 알고 있는 내용을 다시 조사하기 위해 서브에이전트를 재사용/스폰하지 않는다.
- 관련된 수정은 개별 Edit 호출로 흩뿌리지 않고 가능한 한 모아서 처리한다.
- 대화가 길어지면 진행 상황을 CLAUDE.md의 "진행 로그"(4절)에 요약해
  다음 세션/에이전트가 전체 히스토리를 다시 읽지 않아도 되게 한다.

## 4. 진행 로그 (요약, 최신순으로 추가)

- 2026-09-14: 초기 스캐폴딩 생성. FastAPI + SQLite + GitPython 스택,
  사이트 CRUD, Bitbucket 설정(App Password), clone/pull/push MVP 구현.
- 2026-09-14: 사이트별 git 상태 표시 추가 (`git_ops.status`). 원격에
  매번 fetch하지 않고 마지막 clone/pull/push 시점 기준 로컬 정보만
  사용 — dirty(미커밋 변경), ahead/behind, 마지막 커밋 메시지/시각을
  계산. push 후에는 로컬 `origin/<branch>` 추적 ref를 직접 갱신해
  ahead 카운트가 바로 0으로 반영되도록 함(명시적 URL로 push하면 git이
  추적 ref를 자동 갱신하지 않는 점 보완). 메인 화면에 상태 배지
  (변경사항 있음/Pull 필요/Push 필요/최신 상태)와 마지막 동기화 시각
  컬럼 추가.

## 5. 다음 기능 후보 (하나씩 검토 후 추가)

아직 구현하지 않은 항목. 사용자와 협의 후 우선순위를 정해 하나씩 추가한다.

- 브랜치 전환/다중 브랜치 지원
- 여러 사이트에 대한 일괄 pull/push
- 사이트 검색/필터/지역별 그룹핑
- 작업 이력(누가 언제 clone/pull/push 했는지) 로그
- SSH 키 인증 지원 추가
- App Password 저장 방식 강화(OS 키체인 연동 등)
- 인증/권한(다중 사용자, 로그인)

## 6. 로컬 실행

```
pip install -r requirements.txt
uvicorn server.main:app --reload
```

브라우저에서 `http://localhost:8000` 접속.
