# AiCy — AI 버튜버 프로젝트

LLM 두뇌 + Live2D 아바타로 유튜브 라이브 채팅에 자동 반응해 방송하는 AI 버튜버.
**0~3단계 완료: 실제 YouTube Live 송출 검증됨 (2026-07-07).**

- 기획서: `docs/기획서.md` (로드맵·아키텍처·페르소나)
- **다음 할 일**: `docs/로드맵-실행계획.md` ← 세션 시작 시 이것부터 볼 것
- TTS 연구: `docs/TTS-연구지도.md`

## 실행 (Windows, PowerShell)

```powershell
# 터미널 1 — 프론트(아바타) 정적 서버
python serve.py --no-browser

# 터미널 2 — 백엔드 (반드시 .venv311! 전역 파이썬엔 chatterbox 없음)
.venv311\Scripts\python -m backend
```

- 컨트롤용 브라우저: `http://localhost:8080/frontend/?mute=1`
- OBS 브라우저 소스: `http://localhost:8080/frontend/?broadcast=1&chat=1`
- URL 옵션: `?model=haru` `?bg=transparent` `?hide=PartId` `?mute=1` `?chat=1`
- 백엔드 콘솔 명령: `/yt <videoId>` `/yt off` `/reset` `/quit`
- 새 방송마다 video ID 갱신: `.env`의 `AICY_YT_VIDEO_ID` 또는 콘솔 `/yt`

## 환경 주의 (함정 목록)

- **실행·검증은 PowerShell로.** (Claude Code의 Bash 툴은 샌드박스라 python 없음/루프백 차단)
- 파이썬이 여럿: 전역 3.11(모듈 부족)·구 3.8. **백엔드는 `.venv311\Scripts\python` 고정** — 아니면 preflight 가드가 시작을 막음.
- 대용량 캐시는 전부 `2606\.cache\`(HF 모델·pip). C: 드라이브 여유 없음 — C:에 큰 것 받지 말 것.
- 한국어 콘솔(cp949): 스크립트 실행 전 `$env:PYTHONIOENCODING="utf-8"`.
- PowerShell 5.1: `&&` 없음, 커밋 메시지는 `@'...'@` 히어스트링(내부에 큰따옴표 금지 — 인자 깨짐).
- 프론트 수정 후: 브라우저 Ctrl+Shift+R, **OBS는 소스 속성 "캐시 새로고침"** (완고하면 URL에 `&v=N`).
- chatterbox 첫 응답은 모델 로드 ~30초. 브라우저 일반 탭은 페이지당 1클릭(오디오 잠금) — OBS 소스는 불필요.
- `.env`는 git 제외(키 보관: OPENAI_KEY, YOUTUBE_API_KEY 등). `frontend/models/`(xl 모델)는 라이선스 미확정이라 로컬 전용.

## 아키텍처 & 핵심 파일

```
YouTube 채팅 → backend/chat_source.py → orchestrator.py(파이프라인)
  → brain.py(gpt-4o+persona.py) → safety.py → tts.py(chatterbox 클로닝)
  → WebSocket(:8765) → frontend/js/app.js(Live2D 립싱크) → OBS → YouTube Live
```

- `backend/tts.py` — 백엔드 6종(chatterbox/chatterbox_turbo/edge/sapi/gtts/elevenlabs), 교체는 `.env`
- 감정태그: LLM이 `[happy]` 선두 출력 → `persona.extract_emotion()` → WS `emotion` 필드 (표정 매핑은 미구현)
- 문장 분할 파이프라이닝: chatterbox일 때 자동 (체감 지연 = 첫 문장)
- 목소리 정체성 = `AICY_CB_REF_AUDIO` 참조 클립 (현재 `audio/aicy-voice-ref-combined.wav`)
- xl 모델 토끼 장식 = Part32 (기본 숨김). 파츠 도구: 콘솔 `aicyParts/aicyHide/aicySweepParts/aicyParam`

## 컨벤션

- 커밋 메시지 한국어, 기능 단위로 커밋 후 push (main 직커밋).
- 변경은 스모크 테스트로 실측 검증 후 커밋 (임시 `_smoke_*.py` 만들고 실행 후 삭제하는 패턴).
- 방송 품질 관련 결정(페르소나 톤·목소리·UI)은 사용자 취향 확인 우선.
