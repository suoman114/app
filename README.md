# LTE-R VCS

사내 Bitbucket과 연동해 LTE-R 사이트별 패키지 저장소를 clone / pull /
push 하고, 메인 화면에서 사이트를 추가·수정·삭제하며 관리하는 로컬
웹앱입니다.

개발 배경과 아키텍처, Claude Code 오케스트레이션 구성은
[CLAUDE.md](./CLAUDE.md)를 참고하세요.

## 실행 방법

```
pip install -r requirements.txt

# 실제 사용(사이트 clone/pull/push 등)
uvicorn server.main:app --host 0.0.0.0 --port 8000

# LTE-R VCS 코드 자체를 수정하며 확인할 때만 --reload 사용
uvicorn server.main:app --reload --reload-dir server
```

> **주의**: `--reload`를 쓸 때는 반드시 `--reload-dir server`를 같이
> 붙이세요. 그냥 `--reload`만 쓰면 clone/pull한 사이트 파일들이 있는
> `data/` 폴더까지 통째로 감시해서, 저장소 안에 `.py` 파일이 생기거나
> 바뀔 때마다(clone/pull 도중 흔함) 서버가 재시작되며 진행 중이던
> 작업이 전부 끊깁니다. `--reload-dir server`는 감시 범위를 우리
> 코드(`server/`)로만 좁혀 이 문제를 막습니다.

브라우저에서 `http://localhost:8000` 접속 후:

1. "Bitbucket 인증 설정"에서 사내 Bitbucket 사용자명/App Password를 저장합니다.
2. "사이트 추가"에서 사이트 이름과 저장소 URL을 입력해 사이트를 등록합니다.
3. 사이트 목록에서 Clone / Pull / Push 버튼으로 동기화합니다.
4. Clone된 사이트는 "파일" 버튼으로 파일 탐색기를 열어 디렉터리를
   클릭해 들어가고, 파일을 클릭해 편집·저장하거나 현재 폴더에
   업로드할 수 있습니다. 저장/업로드 후에는 바로 Push할지 물어봅니다.
