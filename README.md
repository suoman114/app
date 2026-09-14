# LTE-R VCS

사내 Bitbucket과 연동해 LTE-R 사이트별 패키지 저장소를 clone / pull /
push 하고, 메인 화면에서 사이트를 추가·수정·삭제하며 관리하는 로컬
웹앱입니다.

개발 배경과 아키텍처, Claude Code 오케스트레이션 구성은
[CLAUDE.md](./CLAUDE.md)를 참고하세요.

## 실행 방법

```
pip install -r requirements.txt
uvicorn server.main:app --reload
```

브라우저에서 `http://localhost:8000` 접속 후:

1. "Bitbucket 인증 설정"에서 사내 Bitbucket 사용자명/App Password를 저장합니다.
2. "사이트 추가"에서 사이트 이름과 저장소 URL을 입력해 사이트를 등록합니다.
3. 사이트 목록에서 Clone / Pull / Push 버튼으로 동기화합니다.
