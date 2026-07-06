# 3단계 — OBS 송출 가이드

> 목표: 로컬 브라우저에서 돌던 AiCy를 **OBS 브라우저 소스**로 캡처해
> 실제 YouTube Live로 송출. (기획서 로드맵 3단계)

## 준비 (한 번만)

| 항목 | 상태 |
|---|---|
| OBS Studio | 설치됨 (`C:\Program Files\obs-studio`) |
| AiCy 백엔드/프론트 | 1·2단계 완료 |
| YouTube 라이브 활성화 | 완료 (2단계에서) |

## 실행 순서

### 1. AiCy 켜기 (평소대로)
```powershell
# 터미널 1
python serve.py
# 터미널 2
.venv311\Scripts\python -m backend
```
> serve.py 가 여는 일반 브라우저 창은 **닫아도 됨** — OBS가 자체 렌더링한다.

### 2. OBS 브라우저 소스 추가
1. OBS → 소스 목록 **+** → **브라우저(Browser)**
2. 설정:
   - **URL**: `http://localhost:8080/frontend/?broadcast=1`
     - `?broadcast=1` = 컨트롤 UI 없이 아바타+자막만 (방송용 클린 뷰)
     - 배경 투명 합성을 원하면: `?broadcast=1&bg=transparent`
   - **너비/높이**: 1920 × 1080 (캔버스 해상도와 동일하게)
   - ✅ **"OBS를 통해 오디오 제어(Control audio via OBS)"** 체크 ← 중요!
     AiCy 목소리가 OBS 오디오 믹서로 직접 들어온다 (스피커 녹음 불필요,
     브라우저 클릭 잠금도 없음)
3. 확인 → 오디오 믹서에 브라우저 소스 게이지가 뜨는지 확인
   (유튜브 채팅으로 말 걸어보면 게이지가 움직여야 함)

### 3. YouTube 연결
1. OBS → 설정 → **방송(Stream)** → 서비스: **YouTube - RTMPS**
2. **계정 연결**(추천) 또는 스트림 키 방식:
   - 스트림 키: [YouTube Studio 라이브 대시보드](https://studio.youtube.com/channel/UC/livestreaming) → 스트림 키 복사
3. 설정 → 출력: 비디오 비트레이트 4500~6000 Kbps(1080p), 오디오 160 Kbps

### 4. 송출
1. YouTube Studio에서 라이브 시작(스트리밍 소프트웨어 모드, 일부공개 추천)
2. OBS → **방송 시작**
3. YouTube 미리보기에서 AiCy가 보이고 들리는지 확인
4. 채팅에 말 걸기 → AiCy가 답하면 **3단계 완료** 🎉

## 완성 후 데이터 흐름
```
시청자 채팅 → YouTube API → 백엔드(LLM→TTS) → WebSocket
   → OBS 브라우저 소스(아바타 렌더+음성) → RTMPS → YouTube Live → 시청자
```

## 트러블슈팅
- **OBS에 소리 안 들어옴**: 브라우저 소스 속성에서 "OBS를 통해 오디오 제어" 체크 확인
- **아바타 안 뜸**: serve.py(8080)와 백엔드(8765)가 켜져 있는지, 브라우저 소스
  우클릭 → "상호작용"으로 페이지 상태 확인
- **화면 멈춤**: 브라우저 소스 속성 → "표시되지 않을 때 소스 종료" 체크 해제
- **송출 지연(latency)**: YouTube 기본 지연이 수 초~수십 초. 채팅→답변 체감을
  줄이려면 라이브 설정에서 "초저지연(Ultra low latency)" 선택
