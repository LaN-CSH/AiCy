# AiCy 백엔드 (Stage 1 MVP)

콘솔로 질문 → LLM(AiCy 페르소나) → TTS → **WebSocket으로 프론트(아바타)에 오디오 전송** → 아바타가 자기 목소리로 답하며 입을 움직임. (방송 없음)

기획서 5번 아키텍처의 Python Orchestrator 구현체.

## 구조

| 파일 | 역할 |
|---|---|
| `config.py` | 모든 설정값(언어·모델·음성·포트)을 `.env`로 분리 (기획서 3번 원칙) |
| `persona.py` | AiCy 시스템 프롬프트 (⚠️ 임시값 — 기획서 6번 확정 시 여기만 수정) |
| `brain.py` | OpenAI 호출 + 세션 대화기록 |
| `tts.py` | 텍스트 → mp3. `elevenlabs`(기본) / `gtts`(키 없이 테스트) |
| `safety.py` | 안전필터 훅(현재 passthrough) + 출력 정제 |
| `orchestrator.py` | WebSocket 서버 + 입력→답변→음성 파이프라인 |

## 실행

```bash
# 1) 의존성 설치
pip install -r backend/requirements.txt

# 2) 설정 — .env.example 을 복사해서 .env 로 만들고 키 입력
#    (API 키가 없으면 .env 에서 AICY_TTS_BACKEND=gtts 로 무료 테스트)
cp .env.example .env

# 3) 프론트(아바타) 서버 — 별도 터미널
python serve.py            # http://localhost:8080/frontend/

# 4) 백엔드 Orchestrator
python -m backend
```

브라우저가 열리면 상태바의 **Backend** 가 `connected` 로 바뀐다.
백엔드 콘솔에 질문을 입력하면 아바타가 답하며 립싱크한다.

> 브라우저는 사용자 제스처 전까지 오디오를 막으므로, 첫 소리가 안 나면
> 페이지를 한 번 클릭하면 된다(자동 resume 처리됨).

### 콘솔 명령
- `/reset` — 대화기록 초기화
- `/quit` — 종료

## TTS 백엔드 (.env `AICY_TTS_BACKEND`)

| 값 | 품질 | 속도 | 필요한 것 |
|---|---|---|---|
| `edge` | 뉴럴(좋음) | 빠름 | 인터넷 (무료·무키) |
| `chatterbox` | 뉴럴(더 좋음, 클로닝·감정조절) | 답변당 ~4-8초 | GPU + **`.venv311\Scripts\python -m backend`로 실행** (첫 응답 전 모델 로드 ~30초) |
| `sapi` | 구식 | 빠름 | 없음 (완전 오프라인) |
| `gtts`/`elevenlabs` | 중간/좋음 | 보통 | 인터넷 / API 키 |

## 다음 단계 (기획서 로드맵)
- **2단계**: `orchestrator.pipeline()` 에 콘솔 대신 YouTube `ChatSource` 연결
- 감정태그 → 표정 이벤트(`emotion` 필드는 이미 프로토콜에 예약됨)
