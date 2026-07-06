"""환경설정 — 기획서 3번 '언어/플랫폼을 설정값으로 분리' 원칙.

모든 교체 가능한 값(언어·모델·음성·TTS 백엔드)을 .env로 뺀다.
코드 수정 없이 설정만으로 한/영, 모델, 음성을 바꿀 수 있게 한다.
"""

import os

from dotenv import load_dotenv

load_dotenv()


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw else default


class Config:
    # --- WebSocket 서버 (백엔드 ↔ 프론트) ---
    WS_HOST = os.getenv("AICY_WS_HOST", "localhost")
    WS_PORT = _int("AICY_WS_PORT", 8765)

    # --- 언어 (ko | en) — 페르소나/ TTS 언어 선택에 사용 ---
    LANG = os.getenv("AICY_LANG", "ko")

    # --- 채팅 수집 (2단계: YouTube Live) ---
    YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
    # 라이브 video ID(주소 watch?v= 뒤 11자). 비우면 콘솔에서 /yt <id> 로 시작
    YT_VIDEO_ID = os.getenv("AICY_YT_VIDEO_ID", "")
    # 폴링 최소 간격(초) — API 쿼터 절약. 실제 간격은 API 권고값과 이 값 중 큰 쪽
    YT_POLL_MIN = float(os.getenv("AICY_YT_POLL_MIN", "5"))

    # --- 두뇌 (LLM) ---
    OPENAI_KEY = os.getenv("OPENAI_KEY")
    LLM_MODEL = os.getenv("AICY_LLM_MODEL", "gpt-4o")

    # --- 음성 (TTS): edge(무료 뉴럴·클라우드) | sapi(로컬·오프라인) | elevenlabs | gtts ---
    TTS_BACKEND = os.getenv("AICY_TTS_BACKEND", "elevenlabs")
    ELEVENLABS_KEY = os.getenv("ELEVENLABS")
    # 레거시 gtts_test.py 에서 쓰던 보이스 ID를 기본값으로 둔다.
    ELEVENLABS_VOICE_ID = os.getenv("AICY_VOICE_ID", "edaoIXGiOsk7Opf9lAsF")
    ELEVENLABS_MODEL = os.getenv("AICY_TTS_MODEL", "eleven_multilingual_v2")
    # Edge 뉴럴 음성: 빈값이면 LANG으로 자동(ko=SunHi, en=Aria)
    EDGE_VOICE = os.getenv("AICY_EDGE_VOICE", "")
    # Chatterbox(로컬 뉴럴, GPU 상주. .venv311 필요): 감정 과장(0~1)·CFG·참조음성(클로닝)
    CB_EXAGGERATION = float(os.getenv("AICY_CB_EXAGGERATION", "0.5"))
    CB_CFG = float(os.getenv("AICY_CB_CFG", "0.5"))
    CB_REF_AUDIO = os.getenv("AICY_CB_REF_AUDIO", "")
    # SAPI(Windows 로컬): 빈값이면 LANG으로 자동(ko=Heami, en=Zira)
    SAPI_VOICE = os.getenv("AICY_SAPI_VOICE", "")
    # 목소리 피치 배율(SAPI 후처리). 1.0=원음, 1.15~1.35=어리고 높은 톤(미소녀).
    # 길이(속도)는 보정되어 유지된다.
    VOICE_PITCH = float(os.getenv("AICY_VOICE_PITCH", "1.0"))
    # 문장 분할 파이프라이닝: auto(기본, 느린 백엔드=chatterbox만 켬) | 1 | 0
    # 답변을 문장 단위로 생성·전송해 체감 지연을 '첫 문장 생성 시간'으로 줄인다.
    TTS_SPLIT = os.getenv("AICY_TTS_SPLIT", "auto")
    # ffmpeg 경로: 빈값이면 PATH 및 C:/ffmpeg 자동 탐색
    FFMPEG = os.getenv("AICY_FFMPEG", "")

    def tts_lang(self) -> str:
        """gTTS 등에서 쓸 언어코드."""
        return "ko" if self.LANG == "ko" else "en"


config = Config()
